"""Google Drive: connect, disconnect, picker token and import into the knowledge library."""
import hmac
import secrets
from datetime import datetime, timezone

from flask import abort, current_app, flash, g, jsonify, redirect, request, session, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.integrations import google_drive as gd
from app.integrations.vault import encrypt_credentials
from app.knowledge.ingest import IngestError, ingest_document
from app.models import AuditLog, IntegrationConnection, KnowledgeRepository
from app.security import active_membership_required, roles_required

from . import knowledge_bp

STATE_KEY = "google_oauth_state"


def _connection(create=False):
    conn = IntegrationConnection.query.filter_by(tenant_id=g.active_tenant_id, provider=gd.PROVIDER).first()
    if conn is None and create:
        conn = IntegrationConnection(tenant_id=g.active_tenant_id, provider=gd.PROVIDER, display_name="Google Drive",
                                     status="not_connected", created_by_user_id=current_user.id)
        db.session.add(conn)
    return conn


def _audit(action, details=None):
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id, action=action,
                            target_type="integration", target_id=gd.PROVIDER, details_json=details or {}))


def drive_view_state():
    """What the Integrations page needs to show for Google Drive."""
    conn = _connection()
    connected = bool(conn and conn.status == "connected" and conn.credential_ciphertext)
    return {
        "configured": gd.is_configured(),
        "connected": connected,
        "status": conn.status if conn else "not_connected",
        "account": (conn.metadata_json or {}).get("account_email", "") if conn else "",
        "last_import": (conn.metadata_json or {}).get("last_import", "") if conn else "",
        "repositories": KnowledgeRepository.query.filter_by(tenant_id=g.active_tenant_id).order_by(KnowledgeRepository.name).all(),
    }


# Google Picker needs Google's script and frames on the Integrations page only.
PICKER_CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
              "script-src 'self' https://apis.google.com https://www.gstatic.com; "
              "frame-src https://docs.google.com https://drive.google.com https://accounts.google.com https://content.googleapis.com; "
              "connect-src 'self' https://www.googleapis.com https://content.googleapis.com; "
              "img-src 'self' data: https://*.googleusercontent.com https://*.gstatic.com https://*.google.com; "
              "font-src 'self' https://fonts.gstatic.com; frame-ancestors 'none'; base-uri 'self'; "
              "form-action 'self' https://accounts.google.com")

# "Connect Google Drive" posts to this app, which redirects to Google's sign-in page.
# Browsers apply form-action to that redirect, so Google's sign-in origin must be allowed
# on the Integrations page (and only there).
CONNECT_CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; "
               "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com")


@knowledge_bp.post("/integrations/google/connect")
@roles_required("owner", "admin")
def google_connect():
    if not gd.is_configured():
        flash("Google Drive isn't available yet: the platform owner needs to add the Google settings.", "error")
        return redirect(url_for("knowledge.integrations"))
    state = secrets.token_urlsafe(32)
    session[STATE_KEY] = {"state": state, "tenant": g.active_tenant_id, "user": current_user.id}
    return redirect(gd.authorization_url(state))


@knowledge_bp.get("/integrations/google/callback")
@login_required
@roles_required("owner", "admin")
def google_callback():
    saved = session.pop(STATE_KEY, None) or {}
    state = request.args.get("state", "")
    if not saved or not hmac.compare_digest(saved.get("state", ""), state) \
            or saved.get("tenant") != g.active_tenant_id or saved.get("user") != current_user.id:
        flash("That Google sign-in didn't match this session. Please try connecting again.", "error")
        return redirect(url_for("knowledge.integrations"))
    if request.args.get("error"):
        flash("Google Drive wasn't connected (permission was not given).", "info")
        return redirect(url_for("knowledge.integrations"))
    try:
        creds, email = gd.exchange_code(request.args.get("code", ""))
    except gd.DriveError as exc:
        flash(str(exc), "error")
        return redirect(url_for("knowledge.integrations"))
    conn = _connection(create=True)
    conn.credential_ciphertext = encrypt_credentials(creds)
    conn.status = "connected"
    conn.scopes_json = gd.SCOPES
    conn.metadata_json = {**(conn.metadata_json or {}), "account_email": email,
                          "connected_at": datetime.now(timezone.utc).isoformat()}
    _audit("integration.google_drive_connected", {"account_email": email})
    db.session.commit()
    flash("Google Drive connected. Use “Import from Google Drive” to add files to a knowledge folder.", "success")
    return redirect(url_for("knowledge.integrations"))


@knowledge_bp.post("/integrations/google/disconnect")
@roles_required("owner", "admin")
def google_disconnect():
    conn = _connection()
    if conn:
        gd.revoke(conn)
        conn.credential_ciphertext = ""
        conn.status = "not_connected"
        meta = dict(conn.metadata_json or {}); meta.pop("account_email", None)
        conn.metadata_json = meta
        _audit("integration.google_drive_disconnected")
        db.session.commit()
    flash("Google Drive disconnected. Files already imported stay in your knowledge library.", "success")
    return redirect(url_for("knowledge.integrations"))


@knowledge_bp.post("/integrations/google/picker-token")
@roles_required("owner", "admin", "manager")
def google_picker_token():
    conn = _connection()
    if not gd.is_configured() or not conn or conn.status != "connected":
        return jsonify(error="Google Drive isn't connected."), 409
    try:
        token, expires_at = gd.access_token(conn)
        db.session.commit()  # keep a refreshed token
    except gd.DriveError as exc:
        return jsonify(error=str(exc)), 502
    c = current_app.config
    return jsonify(access_token=token, expires_at=expires_at, api_key=c["GOOGLE_API_KEY"],
                   app_id=str(c["GOOGLE_APP_ID"]), mime_types=gd.PICKABLE_MIME_TYPES)


@knowledge_bp.post("/integrations/google/import")
@roles_required("owner", "admin", "manager")
def google_import():
    data = request.get_json(silent=True) or {}
    repo = KnowledgeRepository.query.filter_by(id=data.get("repository_id"), tenant_id=g.active_tenant_id).first() \
        if isinstance(data.get("repository_id"), int) else None
    if repo is None:
        return jsonify(error="Choose a knowledge folder first."), 400
    ids = [str(i) for i in (data.get("file_ids") or []) if isinstance(i, str)][: gd.MAX_FILES_PER_IMPORT + 1]
    if not ids:
        return jsonify(error="No files were picked."), 400
    if len(ids) > gd.MAX_FILES_PER_IMPORT:
        return jsonify(error=f"Pick up to {gd.MAX_FILES_PER_IMPORT} files at a time."), 400
    conn = _connection()
    if not conn or conn.status != "connected":
        return jsonify(error="Google Drive isn't connected."), 409
    try:
        token, _ = gd.access_token(conn)
    except gd.DriveError as exc:
        return jsonify(error=str(exc)), 502
    results = []
    for file_id in ids:
        name = "Picked file"
        try:
            name, blob = gd.download(token, file_id)
            ingest_document(g.active_tenant_id, repo, current_user.id, name, blob,
                            source="google_drive", source_ref=file_id)
            results.append({"name": name, "ok": True})
        except (gd.DriveError, IngestError) as exc:
            results.append({"name": name, "ok": False, "error": str(exc)})
    imported = sum(1 for r in results if r["ok"])
    conn = _connection()
    conn.metadata_json = {**(conn.metadata_json or {}), "last_import": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M")}
    _audit("integration.google_drive_import", {"repository_id": repo.id, "imported": imported, "failed": len(results) - imported})
    db.session.commit()
    return jsonify(imported=imported, results=results, repository=repo.name,
                   permissions_url=url_for("knowledge.permissions", repository_id=repo.id))
