import re
from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, current_user
from sqlalchemy.exc import IntegrityError
from app.extensions import db, bcrypt
from app.models import User, Tenant, TenantMembership, AuditLog, Department, AIEmployee, SecurityToken
from app.billing.services import create_trial_subscription
from app.workforce.profiles import STARTER_PROFILES
from app.security_service import issue_token, consume_token, send_email, verify_mfa, setup_mfa, hash_token, as_utc
from . import auth_bp

def slugify(value):
    value=re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-"); return value[:150] or "business"

def _utcnow(): return datetime.now(timezone.utc)

def _locked(user):
    return bool(user.locked_until) and as_utc(user.locked_until) > _utcnow()

def _security_failure(user):
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= current_app.config.get("LOGIN_MAX_ATTEMPTS",5):
        user.locked_until=_utcnow()+timedelta(minutes=current_app.config.get("LOGIN_LOCKOUT_MINUTES",15)); user.failed_login_attempts=0
    db.session.commit()

@auth_bp.route("/register", methods=["GET","POST"])
def register():
    if current_user.is_authenticated: return redirect(url_for("workspace.dashboard"))
    if request.method=="POST":
        full_name=request.form.get("full_name","").strip(); email=request.form.get("email","").strip().lower(); business_name=request.form.get("business_name","").strip(); password=request.form.get("password","")
        if not all([full_name,email,business_name]) or len(password)<12: flash("Complete all fields. Passwords must contain at least 12 characters.","error"); return render_template("auth/register.html")
        if User.query.filter_by(email=email).first(): flash("An account with that email already exists.","error"); return render_template("auth/register.html")
        base=slugify(business_name); slug,suffix=base,1
        while Tenant.query.filter_by(slug=slug).first(): suffix+=1; slug=f"{base}-{suffix}"
        user=User(email=email,full_name=full_name,password_hash=bcrypt.generate_password_hash(password).decode())
        tenant=Tenant(name=business_name,slug=slug)
        try:
            db.session.add_all([user,tenant]); db.session.flush(); db.session.add(TenantMembership(tenant_id=tenant.id,user_id=user.id,role="owner"))
            specs=[("Executive Office","Executive support, coordination and administration."),("Human Resources","People operations, recruitment and employee administration."),("Finance","Financial analysis, bookkeeping support and reporting."),("Marketing","Brand, communications and marketing campaigns."),("Customer Service","Customer enquiries, support and service quality."),("Research","Research, analysis and business intelligence."),("Projects","Project planning, delivery and monitoring."),("Operations","Business operations and process improvement."),("Technology","Software development and technical support.")]
            deps={}
            for n,d in specs: deps[n]=Department(tenant_id=tenant.id,name=n,description=d); db.session.add(deps[n])
            db.session.flush()
            emps=[("AI Executive Assistant","Executive Assistant","Executive Office"),("AI Human Resource Officer","Human Resource Officer","Human Resources"),("AI Accountant","Accountant","Finance"),("AI Marketing Officer","Marketing Officer","Marketing"),("AI Customer Service Officer","Customer Service Officer","Customer Service"),("AI Research Officer","Research Officer","Research"),("AI Project Manager","Project Manager","Projects"),("AI Operations Manager","Operations Manager","Operations"),("AI Software Developer","Software Developer","Technology"),("AI Team Coordinator","Team Coordinator","Executive Office")]
            # Every new workspace starts its free trial with the whole team switched on and ready to work.
            for n,t,d in emps:
                desc,resp,skills=STARTER_PROFILES[t]
                db.session.add(AIEmployee(tenant_id=tenant.id,department_id=deps[d].id,name=n,job_title=t,description=desc,responsibilities_json=resp,skills_json=skills,status="active",is_system_template=True))
            create_trial_subscription(tenant.id); db.session.add(AuditLog(tenant_id=tenant.id,actor_user_id=user.id,action="tenant.registered",target_type="tenant",target_id=str(tenant.id)))
            token=issue_token(user.id,"email_verification",current_app.config.get("EMAIL_VERIFICATION_HOURS",24)*60); db.session.commit()
            link=f"{(current_app.config.get('PUBLIC_BASE_URL') or request.host_url).rstrip('/')}{url_for('auth.verify_email',token=token)}"
            try:
                sent=send_email(email,"Verify your AI Workforce account",f"Hello {full_name},\n\nVerify your account: {link}\n\nThis link expires in 24 hours.")
            except Exception:
                current_app.logger.exception("Email verification delivery failed")
                sent=False
        except IntegrityError: db.session.rollback(); flash("Registration could not be completed. Please try again.","error"); return render_template("auth/register.html")
        session.clear(); login_user(user); session["active_tenant_id"]=tenant.id; flash("Account created. Please verify your email before using sensitive features.","success")
        if not sent: flash("Email verification is pending SMTP configuration.","info")
        return redirect(url_for("workspace.dashboard"))
    return render_template("auth/register.html")

@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    record=consume_token(token,"email_verification")
    if not record: flash("The verification link is invalid or expired.","error"); return redirect(url_for("auth.login"))
    user=db.session.get(User,record.user_id); user.email_verified_at=_utcnow(); db.session.commit(); flash("Email verified successfully.","success"); return redirect(url_for("auth.login"))

@auth_bp.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("workspace.dashboard"))
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); password=request.form.get("password",""); user=User.query.filter_by(email=email).first()
        if not user or not user.is_active or _locked(user) or not bcrypt.check_password_hash(user.password_hash,password):
            if user and user.is_active and not _locked(user): _security_failure(user)
            flash("Invalid credentials or account temporarily locked.","error"); return render_template("auth/login.html")
        user.failed_login_attempts=0; user.locked_until=None
        session.clear(); login_user(user)
        if user.mfa_enabled: session["mfa_pending_user_id"]=user.id; session["mfa_pending"]=True; db.session.commit(); return redirect(url_for("auth.mfa_verify"))
        membership=TenantMembership.query.filter_by(user_id=user.id,status="active").first()
        if membership: session["active_tenant_id"]=membership.tenant_id; db.session.commit(); return redirect(url_for("workspace.dashboard"))
        logout_user()
    return render_template("auth/login.html")

@auth_bp.route("/mfa", methods=["GET","POST"])
def mfa_verify():
    if not current_user.is_authenticated or not session.get("mfa_pending"): return redirect(url_for("auth.login"))
    if request.method=="POST":
        if verify_mfa(current_user,request.form.get("code","").strip()):
            session.pop("mfa_pending",None); session.pop("mfa_pending_user_id",None); membership=TenantMembership.query.filter_by(user_id=current_user.id,status="active").first()
            if membership: session["active_tenant_id"]=membership.tenant_id; db.session.commit(); return redirect(url_for("workspace.dashboard"))
        flash("Invalid MFA code.","error")
    return render_template("auth/mfa.html")

@auth_bp.route("/mfa/setup", methods=["GET", "POST"])
def mfa_setup():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if current_user.mfa_enabled:
        flash("MFA is already enabled on this account.", "info")
        return redirect(url_for("workspace.dashboard"))
    secret = session.get("mfa_setup_secret")
    if request.method == "GET" and not secret:
        secret, _ = setup_mfa(current_user)
        db.session.rollback()
        current_user.mfa_secret = secret
        current_user.mfa_recovery_codes_json = []
        session["mfa_setup_secret"] = secret
        return render_template("auth/mfa_setup.html", secret=secret, codes=None)
    if request.method == "POST":
        if not secret:
            return redirect(url_for("auth.mfa_setup"))
        import pyotp
        code = request.form.get("code", "").strip().replace(" ", "")
        if not pyotp.TOTP(secret).verify(code, valid_window=1):
            flash("Enter the current code from your authenticator app to confirm MFA.", "error")
            return render_template("auth/mfa_setup.html", secret=secret, codes=None)
        secret, codes = setup_mfa(current_user)
        db.session.commit()
        session.pop("mfa_setup_secret", None)
        flash("MFA enabled. Save your recovery codes securely.", "success")
        return render_template("auth/mfa_setup.html", secret=secret, codes=codes)
    return render_template("auth/mfa_setup.html", secret=secret, codes=None)

@auth_bp.route("/forgot-password", methods=["GET","POST"])
def forgot_password():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); user=User.query.filter_by(email=email).first()
        if user:
            token=issue_token(user.id,"password_reset",current_app.config.get("PASSWORD_RESET_MINUTES",30)); db.session.commit(); link=f"{(current_app.config.get('PUBLIC_BASE_URL') or request.host_url).rstrip('/')}{url_for('auth.reset_password',token=token)}"
            try:
                send_email(email,"Reset your AI Workforce password",f"Reset your password: {link}\n\nThe link expires in 30 minutes.")
            except Exception:
                current_app.logger.exception("Password reset email delivery failed")
        flash("If the account exists, password reset instructions have been sent.","info"); return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html")

@auth_bp.route("/reset-password/<token>", methods=["GET","POST"])
def reset_password(token):
    record=SecurityToken.query.filter_by(token_hash=hash_token(token),token_type="password_reset",used_at=None).first()
    if not record or as_utc(record.expires_at)<=_utcnow(): flash("The password reset link is invalid or expired.","error"); return redirect(url_for("auth.login"))
    if request.method=="POST":
        password=request.form.get("password","")
        if len(password)<12: flash("Password must contain at least 12 characters.","error"); return render_template("auth/reset_password.html")
        user=db.session.get(User,record.user_id); user.password_hash=bcrypt.generate_password_hash(password).decode(); user.failed_login_attempts=0; user.locked_until=None; record.used_at=_utcnow(); db.session.commit(); flash("Password reset successfully. Please sign in.","success"); return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html")

@auth_bp.post("/logout")
def logout(): logout_user(); session.clear(); return redirect(url_for("auth.login"))
