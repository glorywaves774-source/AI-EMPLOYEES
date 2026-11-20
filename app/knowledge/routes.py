import hashlib
import uuid
from io import BytesIO
from flask import abort, current_app, flash, g, make_response, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import (AIEmployee, AIEmployeeKnowledgePermission, AuditLog, IntegrationConnection,
                        KnowledgeChunk, KnowledgeDocument, KnowledgeRepository)
from app.knowledge.services import extract_document_text, chunk_text, search_tenant_knowledge
from app.knowledge.storage import store_file, read_file, delete_file
from app.knowledge.ingest import IngestError, ingest_document
from app.security import active_membership_required, roles_required
from . import knowledge_bp

from app.knowledge.ingest import MAX_UPLOAD_BYTES  # noqa: E402

@knowledge_bp.get("/")
@login_required
@active_membership_required
def index():
    q = request.args.get("q", "").strip()[:120]
    repositories = KnowledgeRepository.query.filter_by(tenant_id=g.active_tenant_id).order_by(KnowledgeRepository.name).all()
    docs_query = KnowledgeDocument.query.filter_by(tenant_id=g.active_tenant_id).filter(KnowledgeDocument.status == "ready")
    if q:
        docs_query = docs_query.filter(KnowledgeDocument.original_filename.ilike(f"%{q}%"))
    documents = docs_query.order_by(KnowledgeDocument.created_at.desc()).limit(100).all()
    employees = AIEmployee.query.filter_by(tenant_id=g.active_tenant_id).order_by(AIEmployee.name).all()
    existing = {c.provider: c for c in IntegrationConnection.query.filter_by(tenant_id=g.active_tenant_id).all()}
    connections = [{"provider": p, "status": existing[p].status if p in existing else "not_connected"}
                   for p in ("google_drive", "email")]
    search_results = search_tenant_knowledge(g.active_tenant_id, q, limit=8) if q else []
    return render_template("knowledge/index.html", documents=documents, repositories=repositories,
                           employees=employees, q=q, connections=connections, search_results=search_results)

@knowledge_bp.post("/repositories")
@roles_required("owner", "admin", "manager")
def create_repository():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    if not name or len(name) > 120:
        flash("Enter a repository name of 1–120 characters.", "error")
        return redirect(url_for("knowledge.index"))
    repo = KnowledgeRepository(tenant_id=g.active_tenant_id, name=name, description=description[:600],
                               created_by_user_id=current_user.id)
    db.session.add(repo)
    try:
        db.session.flush()
        db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
            action="knowledge.repository_created", target_type="knowledge_repository", target_id=str(repo.id)))
        db.session.commit()
        flash("Knowledge repository created.", "success")
    except Exception:
        db.session.rollback()
        flash("That repository may already exist. Check its name and try again.", "error")
    return redirect(url_for("knowledge.index"))

@knowledge_bp.post("/upload")
@roles_required("owner", "admin", "manager")
def upload_document():
    upload = request.files.get("document")
    if not upload or not upload.filename:
        flash("Choose a document to upload.", "error")
        return redirect(url_for("knowledge.index"))
    data = upload.stream.read(MAX_UPLOAD_BYTES + 1)
    repository_id = request.form.get("repository_id", type=int)
    repo = KnowledgeRepository.query.filter_by(id=repository_id, tenant_id=g.active_tenant_id).first() if repository_id else None
    if repo is None:
        flash("Choose a valid knowledge repository before uploading.", "error")
        return redirect(url_for("knowledge.index"))
    try:
        ingest_document(g.active_tenant_id, repo, current_user.id, upload.filename, data)
    except IngestError as exc:
        flash(str(exc), "error")
        return redirect(url_for("knowledge.index"))
    flash("Document encrypted, stored and indexed. It is not available to AI employees until you grant repository access.", "success")
    return redirect(url_for("knowledge.permissions", repository_id=repo.id))

@knowledge_bp.get("/repositories/<int:repository_id>/permissions")
@roles_required("owner", "admin", "manager")
def permissions(repository_id):
    repo = KnowledgeRepository.query.filter_by(id=repository_id, tenant_id=g.active_tenant_id).first_or_404()
    employees = AIEmployee.query.filter_by(tenant_id=g.active_tenant_id).order_by(AIEmployee.name).all()
    permitted = {p.employee_id for p in AIEmployeeKnowledgePermission.query.filter_by(
        tenant_id=g.active_tenant_id, repository_id=repo.id).all()}
    return render_template("knowledge/permissions.html", repository=repo, employees=employees, permitted=permitted)

@knowledge_bp.post("/repositories/<int:repository_id>/permissions")
@roles_required("owner", "admin", "manager")
def update_permissions(repository_id):
    repo = KnowledgeRepository.query.filter_by(id=repository_id, tenant_id=g.active_tenant_id).first_or_404()
    selected = {int(x) for x in request.form.getlist("employee_ids") if x.isdigit()}
    valid = {e.id for e in AIEmployee.query.filter(AIEmployee.tenant_id == g.active_tenant_id,
             AIEmployee.id.in_(selected)).all()} if selected else set()
    existing = {p.employee_id: p for p in AIEmployeeKnowledgePermission.query.filter_by(
        tenant_id=g.active_tenant_id, repository_id=repo.id).all()}
    for employee_id in valid - set(existing):
        db.session.add(AIEmployeeKnowledgePermission(tenant_id=g.active_tenant_id,
            employee_id=employee_id, repository_id=repo.id, granted_by_user_id=current_user.id))
    for employee_id, permission in existing.items():
        if employee_id not in valid:
            db.session.delete(permission)
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="knowledge.repository_permissions_updated", target_type="knowledge_repository",
        target_id=str(repo.id), details_json={"permitted_employee_ids": sorted(valid)}))
    db.session.commit()
    flash("AI employee repository permissions updated.", "success")
    return redirect(url_for("knowledge.index"))

@knowledge_bp.post("/documents/<int:document_id>/archive")
@roles_required("owner", "admin")
def archive_document(document_id):
    doc = KnowledgeDocument.query.filter_by(id=document_id, tenant_id=g.active_tenant_id).first_or_404()
    doc.status = "archived"
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="knowledge.document_archived", target_type="knowledge_document", target_id=str(doc.id)))
    db.session.commit()
    flash("Document archived and excluded from AI retrieval.", "success")
    return redirect(url_for("knowledge.index"))

@knowledge_bp.post("/integrations/<provider>/request-setup")
@roles_required("owner", "admin")
def request_integration_setup(provider):
    if provider not in {"google_drive", "email"}:
        abort(404)
    connection = IntegrationConnection.query.filter_by(tenant_id=g.active_tenant_id, provider=provider).first()
    if connection is None:
        connection = IntegrationConnection(tenant_id=g.active_tenant_id, provider=provider,
            display_name="Google Drive" if provider == "google_drive" else "Business Email",
            status="setup_requested", created_by_user_id=current_user.id)
        db.session.add(connection)
    else:
        connection.status = "setup_requested"
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="integration.setup_requested", target_type="integration", target_id=provider))
    db.session.commit()
    flash("Setup request recorded. No external account has been connected.", "info")
    return redirect(url_for("knowledge.index"))


@knowledge_bp.get("/documents/<int:document_id>/download")
@login_required
@active_membership_required
def download_document(document_id):
    doc = KnowledgeDocument.query.filter_by(id=document_id, tenant_id=g.active_tenant_id, status="ready").first_or_404()
    try:
        raw = read_file(doc.storage_key)
    except Exception:
        current_app.logger.exception("Private document retrieval failed")
        abort(503)
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="knowledge.document_downloaded", target_type="knowledge_document", target_id=str(doc.id)))
    db.session.commit()
    return send_file(BytesIO(raw), as_attachment=True, download_name=doc.original_filename,
                     mimetype=doc.mime_type, max_age=0)

@knowledge_bp.post("/documents/<int:document_id>/delete")
@roles_required("owner", "admin")
def delete_document(document_id):
    doc = KnowledgeDocument.query.filter_by(id=document_id, tenant_id=g.active_tenant_id).first_or_404()
    key = doc.storage_key
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="knowledge.document_deleted", target_type="knowledge_document", target_id=str(doc.id),
        details_json={"filename": doc.original_filename, "sha256": doc.sha256}))
    db.session.delete(doc)
    db.session.commit()
    try:
        delete_file(key)
    except Exception:
        current_app.logger.exception("Encrypted document object cleanup failed after database deletion")
    flash("Document and indexed content deleted.", "success")
    return redirect(url_for("knowledge.index"))


@knowledge_bp.get("/integrations")
@login_required
@active_membership_required
def integrations():
    existing = {c.provider: c for c in IntegrationConnection.query.filter_by(tenant_id=g.active_tenant_id).all()}
    connections = [{"provider": p, "status": existing[p].status if p in existing else "not_connected",
                    "updated_at": existing[p].updated_at if p in existing else None}
                   for p in ("google_drive", "email")]
    from .google_routes import CONNECT_CSP, PICKER_CSP, drive_view_state
    drive = drive_view_state()
    response = make_response(render_template("knowledge/integrations.html", connections=connections, drive=drive))
    if drive["configured"]:
        # This page only: allow the redirect to Google sign-in, and the Picker once connected.
        response.headers["Content-Security-Policy"] = PICKER_CSP if drive["connected"] else CONNECT_CSP
    return response


@knowledge_bp.get("/search")
@login_required
@active_membership_required
def search():
    query = request.args.get("q", "").strip()[:120]
    return redirect(url_for("knowledge.index", q=query))
