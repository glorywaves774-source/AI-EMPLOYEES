from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from decimal import Decimal, InvalidOperation
from functools import wraps
import pyotp
from flask import abort, flash, redirect, render_template, request, session, url_for, current_app
from app.extensions import db, bcrypt
from app.models import PlatformAdmin, PlatformAuditLog, SecurityEvent, Tenant, TenantSubscription, SubscriptionPlan, Payment
from app.security_monitor import record_security_event
from . import platform_bp


def _now():
    return datetime.now(timezone.utc)


def _is_locked_until(value):
    if not value:
        return False
    # SQLite returns naive datetimes for timezone=True columns; treat those
    # persisted UTC values as UTC before comparing them with an aware clock.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > _now()


def _safe_next_url(target):
    """Allow only same-host relative redirects after authentication."""
    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def platform_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin_id = session.get("platform_admin_id")
        admin = PlatformAdmin.query.get(admin_id) if admin_id else None
        if not admin or not admin.is_active or _is_locked_until(admin.locked_until):
            return redirect(url_for("platform.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@platform_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        admin = PlatformAdmin.query.filter_by(email=email).first()
        locked = admin and _is_locked_until(admin.locked_until)
        if admin and admin.is_active and not locked and bcrypt.check_password_hash(admin.password_hash, password):
            admin.failed_login_attempts = 0
            admin.locked_until = None
            if admin.mfa_enabled:
                session.clear()
                session["platform_mfa_pending_admin_id"] = admin.id
                record_security_event("platform_admin.mfa_challenge", user_id=None, platform_admin_id=admin.id)
                db.session.commit()
                return redirect(url_for("platform.mfa"))
            session["platform_admin_id"] = admin.id
            admin.last_login_at = _now()
            db.session.add(PlatformAuditLog(platform_admin_id=admin.id, action="platform_admin.login"))
            record_security_event("platform_admin.login", platform_admin_id=admin.id)
            db.session.commit()
            return redirect(_safe_next_url(request.args.get("next")) or url_for("platform.dashboard"))
        if admin and admin.is_active and not locked:
            admin.failed_login_attempts += 1
            if admin.failed_login_attempts >= current_app.config.get("PLATFORM_ADMIN_LOGIN_MAX_ATTEMPTS", 5):
                admin.locked_until = _now() + timedelta(minutes=current_app.config.get("PLATFORM_ADMIN_LOCKOUT_MINUTES", 15))
                admin.failed_login_attempts = 0
                record_security_event("platform_admin.lockout", "high", platform_admin_id=admin.id)
            else:
                record_security_event("platform_admin.login_failed", "medium", platform_admin_id=admin.id)
            db.session.commit()
        flash("Invalid platform administrator credentials.", "error")
    return render_template("platform/login.html")


@platform_bp.route("/mfa", methods=["GET", "POST"])
def mfa():
    admin_id = session.get("platform_mfa_pending_admin_id")
    admin = PlatformAdmin.query.get(admin_id) if admin_id else None
    if not admin or not admin.is_active or not admin.mfa_enabled:
        session.pop("platform_mfa_pending_admin_id", None)
        return redirect(url_for("platform.login"))

    # The same persisted lockout applies to password and MFA challenges. Password
    # success resets it before issuing this pending-MFA session.
    if _is_locked_until(admin.locked_until):
        session.pop("platform_mfa_pending_admin_id", None)
        flash("Platform administrator access is temporarily locked. Try again later.", "error")
        return redirect(url_for("platform.login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip().replace(" ", "")
        valid = bool(admin.mfa_secret and pyotp.TOTP(admin.mfa_secret).verify(code, valid_window=1))
        if not valid:
            recovery = admin.mfa_recovery_codes_json or []
            match = next((stored for stored in recovery if bcrypt.check_password_hash(stored, code)), None) if code else None
            if match:
                admin.mfa_recovery_codes_json = [x for x in recovery if x != match]
                valid = True
        if valid:
            admin.failed_login_attempts = 0
            admin.locked_until = None
            session.pop("platform_mfa_pending_admin_id", None)
            session["platform_admin_id"] = admin.id
            admin.last_login_at = _now()
            db.session.add(PlatformAuditLog(platform_admin_id=admin.id, action="platform_admin.mfa_success"))
            record_security_event("platform_admin.mfa_success", platform_admin_id=admin.id)
            db.session.commit()
            return redirect(_safe_next_url(request.args.get("next")) or url_for("platform.dashboard"))

        admin.failed_login_attempts += 1
        max_attempts = max(1, int(current_app.config.get("PLATFORM_ADMIN_MFA_MAX_ATTEMPTS", 5)))
        if admin.failed_login_attempts >= max_attempts:
            admin.failed_login_attempts = 0
            admin.locked_until = _now() + timedelta(
                minutes=max(1, int(current_app.config.get("PLATFORM_ADMIN_MFA_LOCKOUT_MINUTES", 15)))
            )
            session.pop("platform_mfa_pending_admin_id", None)
            record_security_event("platform_admin.mfa_lockout", "critical", platform_admin_id=admin.id)
            db.session.add(PlatformAuditLog(platform_admin_id=admin.id, action="platform_admin.mfa_lockout"))
            db.session.commit()
            flash("Too many invalid MFA attempts. Access is temporarily locked.", "error")
            return redirect(url_for("platform.login"))

        record_security_event("platform_admin.mfa_failed", "high", platform_admin_id=admin.id)
        db.session.commit()
        flash("Invalid MFA code.", "error")
    return render_template("platform/mfa.html")

@platform_bp.post("/logout")
@platform_admin_required
def logout():
    admin_id = session.pop("platform_admin_id", None)
    if admin_id:
        db.session.add(PlatformAuditLog(platform_admin_id=admin_id, action="platform_admin.logout"))
        record_security_event("platform_admin.logout", platform_admin_id=admin_id)
        db.session.commit()
    return redirect(url_for("platform.login"))


@platform_bp.get("/")
@platform_admin_required
def dashboard():
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.amount.asc()).all()
    subscriptions = TenantSubscription.query.order_by(TenantSubscription.created_at.desc()).all()
    payments = Payment.query.order_by(Payment.created_at.desc()).limit(30).all()
    security_events = SecurityEvent.query.order_by(SecurityEvent.created_at.desc()).limit(50).all()
    return render_template("platform/dashboard.html", tenants=tenants, plans=plans, subscriptions=subscriptions,
                           payments=payments, security_events=security_events,
                           platform_name=current_app.config.get("PLATFORM_NAME", "Kayron Global Tech Services"))


@platform_bp.post("/plans/<int:plan_id>")
@platform_admin_required
def update_plan(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    try:
        plan.amount = Decimal(request.form.get("amount", "0"))
        plan.max_ai_employees = int(request.form.get("max_ai_employees", "0"))
        plan.monthly_task_limit = int(request.form.get("monthly_task_limit", "0"))
    except (InvalidOperation, ValueError):
        flash("Enter valid numeric plan values.", "error")
        return redirect(url_for("platform.dashboard"))
    if plan.amount < 0 or plan.max_ai_employees < 1 or plan.monthly_task_limit < 1:
        flash("Plan limits must be positive and price cannot be negative.", "error")
        return redirect(url_for("platform.dashboard"))
    admin_id = session["platform_admin_id"]
    db.session.add(PlatformAuditLog(platform_admin_id=admin_id, action="plan.updated", target_type="subscription_plan",
                                    target_id=str(plan.id), details_json={"amount": str(plan.amount), "employees": plan.max_ai_employees, "tasks": plan.monthly_task_limit}))
    record_security_event("platform_admin.plan_updated", platform_admin_id=admin_id, details={"plan_id": plan.id})
    db.session.commit()
    flash(f"{plan.name} plan updated.", "success")
    return redirect(url_for("platform.dashboard"))


@platform_bp.post("/subscriptions/<int:subscription_id>/status")
@platform_admin_required
def update_subscription_status(subscription_id):
    sub = TenantSubscription.query.get_or_404(subscription_id)
    status = request.form.get("status")
    if status not in {"trialing", "active", "past_due", "canceled", "expired"}:
        abort(400)
    sub.status = status
    if status == "canceled":
        sub.canceled_at = _now()
    db.session.add(PlatformAuditLog(platform_admin_id=session["platform_admin_id"], action="subscription.status_changed",
                                    target_type="tenant_subscription", target_id=str(sub.id), details_json={"status": status}))
    record_security_event("platform_admin.subscription_status_changed", platform_admin_id=session["platform_admin_id"], details={"subscription_id": sub.id, "status": status})
    db.session.commit()
    flash("Subscription status updated.", "success")
    return redirect(url_for("platform.dashboard"))
