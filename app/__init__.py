from flask import Flask, redirect, url_for, g, session, request, jsonify
from flask_login import current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import uuid
import re
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from .extensions import db, login_manager, csrf, migrate, bcrypt

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    proxy_hops = int(app.config.get("TRUST_PROXY_COUNT", 0))
    if proxy_hops < 0:
        raise ValueError("TRUST_PROXY_COUNT cannot be negative")
    if proxy_hops:
        # Render terminates TLS and forwards the original client/protocol headers.
        # Trust only the explicitly configured number of proxy hops.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_hops, x_proto=proxy_hops)

    if app.config.get("ENVIRONMENT") == "production":
        secret = app.config.get("SECRET_KEY", "")
        if not secret or secret == "dev-only-change-me" or len(secret) < 32:
            raise RuntimeError("Production requires a strong SECRET_KEY (at least 32 characters).")
        if str(app.config.get("SQLALCHEMY_DATABASE_URI", "")).startswith("sqlite:"):
            raise RuntimeError("Production requires PostgreSQL; SQLite is development-only.")
        if not app.config.get("SESSION_COOKIE_SECURE"):
            raise RuntimeError("Production requires secure session cookies.")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    csrf.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    limiter = Limiter(key_func=get_remote_address, default_limits=["300 per hour"], storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://"))
    limiter.init_app(app)
    app.extensions["limiter"] = limiter

    from . import models  # register models with SQLAlchemy

    def request_is_https():
        return request.is_secure

    @app.before_request
    def request_id():
        supplied = request.headers.get("X-Request-ID", "")
        # Keep externally supplied correlation IDs bounded and log-safe.
        g.request_id = supplied[:64] if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied) else uuid.uuid4().hex

    @app.after_request
    def request_logging(response):
        app.logger.info("request method=%s path=%s status=%s request_id=%s", request.method, request.path, response.status_code, g.get("request_id"))
        return response

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Request-ID", getattr(g, "request_id", ""))
        if app.config.get("SECURITY_HEADERS_ENABLED", True):
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
            if request_is_https(): response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.before_request
    def establish_tenant_context():
        # Tenant context is application-wide so workforce and approval blueprints
        # receive the same membership enforcement as workspace routes.
        if not current_user.is_authenticated:
            return
        from .models import TenantMembership
        tenant_id = session.get("active_tenant_id")
        membership = TenantMembership.query.filter_by(
            tenant_id=tenant_id, user_id=current_user.id, status="active"
        ).first() if tenant_id else None
        if membership is None:
            membership = TenantMembership.query.filter_by(
                user_id=current_user.id, status="active"
            ).first()
            if membership:
                session["active_tenant_id"] = membership.tenant_id
        if membership:
            g.active_tenant_id = membership.tenant_id
            g.active_tenant = membership.tenant
            g.membership = membership
    from .auth import auth_bp
    from .workspace import workspace_bp
    from .workforce import workforce_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(workspace_bp)
    app.register_blueprint(workforce_bp)
    from .approvals import approvals_bp
    app.register_blueprint(approvals_bp)
    from .knowledge import knowledge_bp
    app.register_blueprint(knowledge_bp)
    from .analytics import analytics_bp
    app.register_blueprint(analytics_bp)
    from .billing import billing_bp
    app.register_blueprint(billing_bp)
    from .platform import platform_bp
    app.register_blueprint(platform_bp)
    from .help import help_bp
    from .help.routes import rate_limit_key
    limiter.limit("10 per minute;100 per day", key_func=rate_limit_key)(help_bp)
    app.register_blueprint(help_bp)

    @app.context_processor
    def ui_context():
        """Role-aware navigation and Kombian availability for the page shell."""
        from flask import session as _s
        from flask_login import current_user as _cu
        from .help.pages import NAV_ORDER, TAB_KEYS, WORKSPACE_PAGES
        role = None
        if request.blueprint == "platform":
            role = "platform_admin" if _s.get("platform_admin_id") else None
        elif _cu.is_authenticated and not _s.get("mfa_pending"):
            m = g.get("membership")
            if m is None and _s.get("active_tenant_id"):
                from .models import TenantMembership
                m = TenantMembership.query.filter_by(user_id=_cu.id, tenant_id=_s["active_tenant_id"], status="active").first()
            role = m.role if m else None
        nav = [k for k in NAV_ORDER if role in WORKSPACE_PAGES[k][2]] if role and role != "platform_admin" else []
        return {"ui_role": role, "ui_nav": nav, "ui_tabs": [k for k in TAB_KEYS if k in nav], "kombian_enabled": bool(role)}
    from .celery_factory import make_celery
    app.extensions["celery"] = make_celery(app)
    from .workforce.tasks import register_tasks
    register_tasks(app.extensions["celery"])

    @app.cli.command("seed-permissions")
    def seed_permissions():
        from .models import Permission, RolePermission
        codes={
            "workforce.read":"View AI workforce", "workforce.manage":"Manage AI workforce", "tasks.execute":"Execute tasks",
            "approvals.manage":"Review approvals", "billing.manage":"Manage billing", "analytics.read":"View analytics",
            "integrations.manage":"Manage integrations", "knowledge.manage":"Manage knowledge", "settings.manage":"Manage workspace settings"
        }
        role_map={"admin":list(codes),"manager":["workforce.read","workforce.manage","tasks.execute","approvals.manage","analytics.read","knowledge.manage"],"employee":["workforce.read","tasks.execute","analytics.read"]}
        for code,desc in codes.items():
            perm=Permission.query.filter_by(code=code).first() or Permission(code=code,description=desc); db.session.add(perm); db.session.flush()
            for role in role_map:
                if code in role_map[role] and not RolePermission.query.filter_by(role=role,permission_id=perm.id).first(): db.session.add(RolePermission(role=role,permission_id=perm.id))
        db.session.commit(); print("Permissions seeded.")

    @app.cli.command("enable-platform-admin-mfa")
    def enable_platform_admin_mfa():
        """Enable MFA for an existing platform administrator and print the provisioning secret."""
        import pyotp
        email = input("Platform admin email: ").strip().lower()
        from .models import PlatformAdmin
        admin = PlatformAdmin.query.filter_by(email=email).first()
        if not admin:
            raise SystemExit("Platform administrator not found.")
        secret = pyotp.random_base32()
        admin.mfa_secret = secret
        admin.mfa_enabled = True
        raw_codes = [uuid.uuid4().hex[:10].upper() for _ in range(8)]
        admin.mfa_recovery_codes_json = [bcrypt.generate_password_hash(code).decode("utf-8") for code in raw_codes]
        db.session.commit()
        uri = pyotp.TOTP(secret).provisioning_uri(name=admin.email, issuer_name=app.config.get("MFA_ISSUER", "AI Workforce"))
        print("MFA enabled.")
        print(f"Secret: {secret}")
        print(f"Provisioning URI: {uri}")
        print("Recovery codes:")
        for code in raw_codes:
            print(code)

    @app.cli.command("purge-security-events")
    def purge_security_events():
        """Remove security events older than the configured retention period."""
        from datetime import timedelta, datetime, timezone
        from .models import SecurityEvent
        cutoff = datetime.now(timezone.utc) - timedelta(days=app.config.get("SECURITY_EVENT_RETENTION_DAYS", 180))
        count = SecurityEvent.query.filter(SecurityEvent.created_at < cutoff).delete(synchronize_session=False)
        db.session.commit()
        print(f"Purged {count} security event(s).")

    @app.cli.command("create-platform-admin")
    def create_platform_admin():
        """Create the first platform administrator interactively."""
        import getpass
        from .models import PlatformAdmin
        from .extensions import db, bcrypt
        email = input("Platform admin email: ").strip().lower()
        full_name = input("Full name: ").strip()
        password = getpass.getpass("Password (minimum 12 characters): ")
        if len(password) < 12:
            raise SystemExit("Password must contain at least 12 characters.")
        if PlatformAdmin.query.filter_by(email=email).first():
            raise SystemExit("A platform administrator with that email already exists.")
        admin = PlatformAdmin(email=email, full_name=full_name,
                              password_hash=bcrypt.generate_password_hash(password).decode("utf-8"))
        db.session.add(admin)
        db.session.commit()
        print("Platform administrator created.")

    @app.cli.command("process-subscription-expirations")
    def process_subscription_expirations_command():
        """Expire subscriptions whose billing/trial period ended without a renewal webhook."""
        from .billing.services import process_subscription_expirations
        count = process_subscription_expirations()
        print(f"Expired {count} subscription(s).")

    # Health probes are exempt from rate limiting: Render's checker polls every
    # few seconds from one internal IP, which exceeds the default per-IP limit
    # and would get the service marked unhealthy (502 for every visitor).
    @app.get("/favicon.ico")
    @limiter.exempt
    def favicon():
        return redirect(url_for("static", filename="favicon.svg"), code=301)

    @app.get("/healthz")
    @limiter.exempt
    def healthz():
        return jsonify({"status": "ok", "service": "ai-workforce"})

    @app.get("/readyz")
    @limiter.exempt
    def readyz():
        checks = {"database": "ok"}
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception:
            db.session.rollback()
            app.logger.exception("Database readiness check failed")
            checks["database"] = "unavailable"

        broker_url = str(app.config.get("CELERY_BROKER_URL", ""))
        if broker_url.startswith(("redis://", "rediss://")):
            try:
                from redis import Redis
                client = Redis.from_url(broker_url, socket_connect_timeout=2, socket_timeout=2)
                try:
                    client.ping()
                finally:
                    client.close()
                checks["redis"] = "ok"
            except Exception:
                app.logger.exception("Redis readiness check failed")
                checks["redis"] = "unavailable"

        ready = all(value == "ok" for value in checks.values())
        return jsonify({"status": "ready" if ready else "not_ready", **checks}), (200 if ready else 503)

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"error": "request_too_large", "request_id": g.get("request_id")}), 413

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        app.logger.exception("Unhandled application error", extra={"request_id": g.get("request_id")})
        return jsonify({"error": "internal_server_error", "request_id": g.get("request_id")}), 500

    @app.get("/")
    def index():
        return redirect(url_for("workspace.dashboard"))

    return app
