"""Team members: Owners and Admins invite colleagues, change roles and remove access."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user

from app.extensions import bcrypt, db
from app.models import AuditLog, TeamInvitation, TenantMembership, User
from app.security import active_membership_required, roles_required
from app.security_service import as_utc, notify_by_email

team_bp = Blueprint("team", __name__, url_prefix="/team")

INVITE_ROLES = {"admin": "Admin", "manager": "Manager", "employee": "Employee"}
ROLE_HELP = {
    "owner": "Everything, including billing and data export.",
    "admin": "Everything except data export: plan, billing, integrations, approvals and team.",
    "manager": "Assigns work, manages AI employees and documents.",
    "employee": "Views work, results and documents.",
}
INVITE_DAYS = 7
MAX_MEMBERS = 50


def _hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _join_url(raw):
    base = (current_app.config.get("PUBLIC_BASE_URL") or request.host_url).rstrip("/")
    return f"{base}{url_for('team.join', token=raw)}"


def _audit(action, target_id, details=None):
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id, action=action,
                            target_type="team", target_id=str(target_id), details_json=details or {}))


@team_bp.get("/")
@roles_required("owner", "admin")
def index():
    members = (TenantMembership.query.filter_by(tenant_id=g.active_tenant_id)
               .join(User, User.id == TenantMembership.user_id).order_by(User.full_name).all())
    invites = (TeamInvitation.query.filter_by(tenant_id=g.active_tenant_id, accepted_at=None, revoked_at=None)
               .order_by(TeamInvitation.created_at.desc()).all())
    pending = [i for i in invites if as_utc(i.expires_at) > _now()]
    return render_template("team/index.html", members=members, invites=pending, roles=INVITE_ROLES,
                           role_help=ROLE_HELP, new_link=session.pop("new_invite_link", None),
                           email_ready=bool(current_app.config.get("SMTP_HOST")))


@team_bp.post("/invite")
@roles_required("owner", "admin")
def invite():
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "employee")
    if role not in INVITE_ROLES or "@" not in email or len(email) > 254:
        flash("Enter a valid email address and role.", "error")
        return redirect(url_for("team.index"))
    if role == "admin" and g.membership.role != "owner":
        flash("Only the Owner can invite Admins.", "error")
        return redirect(url_for("team.index"))
    existing_user = User.query.filter_by(email=email).first()
    if existing_user and TenantMembership.query.filter_by(tenant_id=g.active_tenant_id, user_id=existing_user.id).first():
        flash(f"{email} is already a member of this workspace.", "info")
        return redirect(url_for("team.index"))
    if TenantMembership.query.filter_by(tenant_id=g.active_tenant_id).count() >= MAX_MEMBERS:
        flash(f"A workspace can have up to {MAX_MEMBERS} members.", "error")
        return redirect(url_for("team.index"))
    # One live invitation per email: replace any earlier one.
    for old in TeamInvitation.query.filter_by(tenant_id=g.active_tenant_id, email=email, accepted_at=None, revoked_at=None):
        old.revoked_at = _now()
    raw = secrets.token_urlsafe(32)
    inv = TeamInvitation(tenant_id=g.active_tenant_id, email=email, role=role, token_hash=_hash(raw),
                         invited_by_user_id=current_user.id, expires_at=_now() + timedelta(days=INVITE_DAYS))
    db.session.add(inv)
    db.session.flush()
    _audit("team.invited", inv.id, {"email": email, "role": role})
    db.session.commit()
    link = _join_url(raw)
    sent = notify_by_email(email, f"Join {g.active_tenant.name} on AI Workforce",
        f"Hello,\n\n{current_user.full_name} has invited you to join {g.active_tenant.name} on AI Workforce "
        f"as {INVITE_ROLES[role]}.\n\nAccept the invitation: {link}\n\nThe link works for {INVITE_DAYS} days.\n\n"
        "— AI Workforce by Kayron Global Tech Services")
    if sent:
        flash(f"Invitation emailed to {email}.", "success")
    else:
        session["new_invite_link"] = {"email": email, "link": link}
        flash(f"Invitation created for {email}. Copy the link below and send it by WhatsApp or SMS.", "success")
    return redirect(url_for("team.index"))


@team_bp.post("/invitations/<int:invite_id>/revoke")
@roles_required("owner", "admin")
def revoke(invite_id):
    inv = TeamInvitation.query.filter_by(id=invite_id, tenant_id=g.active_tenant_id, accepted_at=None).first_or_404()
    inv.revoked_at = _now()
    _audit("team.invitation_revoked", inv.id, {"email": inv.email})
    db.session.commit()
    flash(f"Invitation for {inv.email} cancelled.", "success")
    return redirect(url_for("team.index"))


@team_bp.post("/members/<int:membership_id>/role")
@roles_required("owner", "admin")
def change_role(membership_id):
    m = TenantMembership.query.filter_by(id=membership_id, tenant_id=g.active_tenant_id).first_or_404()
    role = request.form.get("role")
    if m.role == "owner" or role not in INVITE_ROLES or m.user_id == current_user.id:
        abort(400)
    if "admin" in (role, m.role) and g.membership.role != "owner":
        flash("Only the Owner can add or change Admins.", "error")
        return redirect(url_for("team.index"))
    old, m.role = m.role, role
    _audit("team.role_changed", m.id, {"from": old, "to": role})
    db.session.commit()
    flash(f"{m.user.full_name} is now {INVITE_ROLES[role]}.", "success")
    return redirect(url_for("team.index"))


@team_bp.post("/members/<int:membership_id>/remove")
@roles_required("owner", "admin")
def remove(membership_id):
    m = TenantMembership.query.filter_by(id=membership_id, tenant_id=g.active_tenant_id).first_or_404()
    if m.role == "owner" or m.user_id == current_user.id:
        abort(400)
    if m.role == "admin" and g.membership.role != "owner":
        flash("Only the Owner can remove Admins.", "error")
        return redirect(url_for("team.index"))
    name = m.user.full_name
    _audit("team.member_removed", m.id, {"user_id": m.user_id, "role": m.role})
    db.session.delete(m)
    db.session.commit()
    flash(f"{name} no longer has access to this workspace. Their past work is kept.", "success")
    return redirect(url_for("team.index"))


def _valid_invite(token):
    inv = TeamInvitation.query.filter_by(token_hash=_hash(token or "")).first()
    if not inv or inv.accepted_at or inv.revoked_at or as_utc(inv.expires_at) <= _now():
        return None
    return inv


def _accept(inv, user):
    if not TenantMembership.query.filter_by(tenant_id=inv.tenant_id, user_id=user.id).first():
        db.session.add(TenantMembership(tenant_id=inv.tenant_id, user_id=user.id, role=inv.role, status="active"))
    inv.accepted_at = _now()
    db.session.add(AuditLog(tenant_id=inv.tenant_id, actor_user_id=user.id, action="team.invitation_accepted",
                            target_type="team", target_id=str(inv.id), details_json={"role": inv.role}))
    db.session.commit()
    session["active_tenant_id"] = inv.tenant_id


@team_bp.route("/join/<token>", methods=["GET", "POST"])
def join(token):
    from app.models import Tenant
    inv = _valid_invite(token)
    if not inv:
        return render_template("team/join.html", invalid=True), 404
    tenant = db.session.get(Tenant, inv.tenant_id)
    existing = User.query.filter_by(email=inv.email).first()
    signed_in = current_user.is_authenticated and not session.get("mfa_pending")
    if request.method == "POST":
        if signed_in:
            if current_user.email.lower() != inv.email:
                abort(403)
            _accept(inv, current_user)
        elif existing:
            return redirect(url_for("auth.login", invite=token))
        else:
            name = request.form.get("full_name", "").strip()
            password = request.form.get("password", "")
            if not name or len(name) > 160 or len(password) < 12:
                flash("Enter your name and a password of at least 12 characters.", "error")
                return render_template("team/join.html", inv=inv, tenant=tenant, existing=None, signed_in=False, roles=INVITE_ROLES)
            if request.form.get("accept_terms") != "yes":
                flash("Please agree to the terms of use and privacy policy.", "error")
                return render_template("team/join.html", inv=inv, tenant=tenant, existing=None, signed_in=False, roles=INVITE_ROLES)
            user = User(email=inv.email, full_name=name, password_hash=bcrypt.generate_password_hash(password).decode(),
                        email_verified_at=_now())  # the invitation link proves they control this inbox
            db.session.add(user)
            db.session.flush()
            session.clear()
            login_user(user)
            _accept(inv, user)
        flash(f"Welcome to {tenant.name}!", "success")
        return redirect(url_for("workspace.dashboard"))
    return render_template("team/join.html", inv=inv, tenant=tenant, existing=existing, signed_in=signed_in,
                           roles=INVITE_ROLES, wrong_account=signed_in and current_user.email.lower() != inv.email)
