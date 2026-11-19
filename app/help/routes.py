"""Kombian endpoint. Requires sign-in (workspace member or platform admin), CSRF and a rate limit."""
from flask import abort, current_app, g, jsonify, request, session
from flask_login import current_user

from app.extensions import db
from app.models import PlatformAdmin, TenantMembership

from . import help_bp
from .assistant import MAX_QUESTION, answer, suggestions


def current_help_role():
    """'platform_admin' on admin pages with a verified admin session, else the workspace role, else None."""
    if request.headers.get("X-Kombian-Context") == "platform" or (request.get_json(silent=True) or {}).get("context") == "platform":
        admin_id = session.get("platform_admin_id")
        admin = db.session.get(PlatformAdmin, admin_id) if admin_id else None
        return "platform_admin" if admin and admin.is_active else None
    if not current_user.is_authenticated or session.get("mfa_pending"):
        return None
    tenant_id = session.get("active_tenant_id")
    membership = TenantMembership.query.filter_by(user_id=current_user.id, tenant_id=tenant_id, status="active").first() if tenant_id else None
    return membership.role if membership else None


def rate_limit_key():
    """Per person, not per IP: offices often share one address."""
    if session.get("platform_admin_id"):
        return f"kombian:admin:{session['platform_admin_id']}"
    if current_user.is_authenticated:
        return f"kombian:user:{current_user.id}"
    return f"kombian:ip:{request.remote_addr}"


@help_bp.post("/ask")
def ask():
    role = current_help_role()
    if not role:
        abort(401)
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify(error="Type a question first."), 400
    if len(question) > MAX_QUESTION:
        return jsonify(error=f"Please keep questions under {MAX_QUESTION} characters."), 400
    history = data.get("history") if isinstance(data.get("history"), list) else []
    current_app.logger.info("Kombian question (role=%s, chars=%d)", role, len(question))  # never log the text
    result = answer(question, role, history)
    return jsonify(result)


@help_bp.get("/suggestions")
def suggest():
    role = current_help_role()
    if not role:
        abort(401)
    return jsonify(suggestions=suggestions(role))
