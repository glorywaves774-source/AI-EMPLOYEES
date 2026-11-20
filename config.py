import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    ENVIRONMENT = os.environ.get("ENVIRONMENT", os.environ.get("FLASK_ENV", "development")).lower()
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///ai_workforce_dev.db")
    # Render commonly exposes PostgreSQL connection strings with the legacy
    # postgres:// scheme. Normalise them to the installed psycopg 3 driver.
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    elif SQLALCHEMY_DATABASE_URI.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = None
    PREFERRED_URL_SCHEME = "https"
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.5")
    # Claude (Anthropic). With AI_PROVIDER=auto, Claude is used first when its key is set and
    # OpenAI takes over automatically if Claude refuses (e.g. no credit), and vice versa.
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "auto")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
    TRIAL_CLAUDE_MODEL = os.environ.get("TRIAL_CLAUDE_MODEL", "claude-haiku-5-5")
    HELP_MODEL = os.environ.get("HELP_MODEL")  # Kombian help assistant; defaults to OPENAI_MODEL
    # Google Drive integration (drive.file scope + Google Picker). All four are needed to enable it.
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    GOOGLE_APP_ID = os.environ.get("GOOGLE_APP_ID")  # Google Cloud project number

    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    PRIVATE_UPLOAD_ROOT = os.environ.get("PRIVATE_UPLOAD_ROOT", os.path.join(os.path.dirname(__file__), "instance", "knowledge-private"))
    FILE_ENCRYPTION_KEY = os.environ.get("FILE_ENCRYPTION_KEY")
    INTEGRATION_ENCRYPTION_KEY = os.environ.get("INTEGRATION_ENCRYPTION_KEY")
    S3_BUCKET = os.environ.get("S3_BUCKET")
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

    CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
    # A team task = planner + up to TEAM_MAX_STEPS specialists + a final summary.
    # 12k tokens was too small for more than ~2 specialists; 60k fits 5 comfortably.
    TEAM_EXECUTION_TOKEN_BUDGET = int(os.environ.get("TEAM_EXECUTION_TOKEN_BUDGET", "60000"))
    TEAM_MAX_STEPS = int(os.environ.get("TEAM_MAX_STEPS", "5"))
    OPENAI_MAX_OUTPUT_TOKENS = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "3000"))
    # Free trial: whole workforce for 14 days, paced so one workspace cannot drain the AI balance.
    TRIAL_OPENAI_MODEL = os.environ.get("TRIAL_OPENAI_MODEL") or None  # defaults to OPENAI_MODEL
    TRIAL_MAX_AI_EMPLOYEES = int(os.environ.get("TRIAL_MAX_AI_EMPLOYEES", "10"))
    TRIAL_DAILY_TASK_LIMIT = int(os.environ.get("TRIAL_DAILY_TASK_LIMIT", "5"))
    # Shared ceiling for all trial workspaces together per UTC day (0 = no ceiling).
    # Charts, presentations and graphics made from finished assignments (per workspace per UTC day).
    TRIAL_DAILY_VISUAL_LIMIT = int(os.environ.get("TRIAL_DAILY_VISUAL_LIMIT", "5"))
    VISUALS_DAILY_LIMIT = int(os.environ.get("VISUALS_DAILY_LIMIT", "40"))
    OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")
    OPENAI_IMAGE_SIZE = os.environ.get("OPENAI_IMAGE_SIZE", "1024x1024")
    # Website chat answers per business per UTC day.
    WIDGET_TRIAL_DAILY_LIMIT = int(os.environ.get("WIDGET_TRIAL_DAILY_LIMIT", "100"))
    WIDGET_DAILY_LIMIT = int(os.environ.get("WIDGET_DAILY_LIMIT", "1000"))
    TRIAL_DAILY_TOKEN_POOL = int(os.environ.get("TRIAL_DAILY_TOKEN_POOL", "2000000"))
    TEAM_EXECUTION_MAX_PARALLELISM = int(os.environ.get("TEAM_EXECUTION_MAX_PARALLELISM", "3"))
    TEAM_EXECUTION_COST_BUDGET_USD = os.environ.get("TEAM_EXECUTION_COST_BUDGET_USD") or None

    ESTIMATED_INPUT_USD_PER_MILLION = float(os.environ.get("ESTIMATED_INPUT_USD_PER_MILLION", "0"))
    ESTIMATED_OUTPUT_USD_PER_MILLION = float(os.environ.get("ESTIMATED_OUTPUT_USD_PER_MILLION", "0"))

    PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "Kayron Global Tech Services")
    BILLING_CURRENCY = os.environ.get("BILLING_CURRENCY", "GHS")
    PLAN_STARTER_AMOUNT = os.environ.get("PLAN_STARTER_AMOUNT", "0")
    PLAN_GROWTH_AMOUNT = os.environ.get("PLAN_GROWTH_AMOUNT", "0")
    PLAN_BUSINESS_AMOUNT = os.environ.get("PLAN_BUSINESS_AMOUNT", "0")
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

    # Milestone 10 security controls
    MFA_ISSUER = os.environ.get("MFA_ISSUER", "AI Workforce")
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
    PASSWORD_RESET_MINUTES = int(os.environ.get("PASSWORD_RESET_MINUTES", "30"))
    EMAIL_VERIFICATION_HOURS = int(os.environ.get("EMAIL_VERIFICATION_HOURS", "24"))
    SECURITY_HEADERS_ENABLED = os.environ.get("SECURITY_HEADERS_ENABLED", "true").lower() == "true"
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USERNAME or "")
    SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() == "true"  # port 465
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5000")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Milestone 12 production hardening
    # Trust forwarded client/protocol headers only from the configured reverse-proxy hop count.
    TRUST_PROXY_COUNT = int(os.environ.get("TRUST_PROXY_COUNT", "0"))
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    SECURITY_EVENT_RETENTION_DAYS = int(os.environ.get("SECURITY_EVENT_RETENTION_DAYS", "180"))
    PLATFORM_ADMIN_LOGIN_MAX_ATTEMPTS = int(os.environ.get("PLATFORM_ADMIN_LOGIN_MAX_ATTEMPTS", "5"))
    PLATFORM_ADMIN_LOCKOUT_MINUTES = int(os.environ.get("PLATFORM_ADMIN_LOCKOUT_MINUTES", "15"))
    PLATFORM_ADMIN_MFA_MAX_ATTEMPTS = int(os.environ.get("PLATFORM_ADMIN_MFA_MAX_ATTEMPTS", "5"))
    PLATFORM_ADMIN_MFA_LOCKOUT_MINUTES = int(os.environ.get("PLATFORM_ADMIN_MFA_LOCKOUT_MINUTES", "15"))
