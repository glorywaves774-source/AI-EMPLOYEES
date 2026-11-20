"""Fail-fast production configuration and live dependency validation.

Run before starting web/worker processes. No external writes are performed.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Running `python scripts/production_check.py` puts scripts/ (not the project
# root) on sys.path, so `from app import ...` would fail without this.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def validate_environment(environ=None):
    env = os.environ if environ is None else environ
    required = [
        "SECRET_KEY", "DATABASE_URL", "FILE_ENCRYPTION_KEY",
        "INTEGRATION_ENCRYPTION_KEY", "PUBLIC_BASE_URL", "RATELIMIT_STORAGE_URI",
        "REDIS_URL", "S3_BUCKET", "AWS_REGION",
    ]
    errors = [f"Missing required production environment variable: {key}"
              for key in required if not env.get(key)]
    if not (env.get("ANTHROPIC_API_KEY") or env.get("OPENAI_API_KEY")):
        errors.append("Set ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY (OpenAI) so AI employees can work.")
    if env.get("ENVIRONMENT", "").lower() != "production":
        errors.append("ENVIRONMENT must be set to production.")
    if len(env.get("SECRET_KEY", "")) < 32:
        errors.append("SECRET_KEY must contain at least 32 characters.")
    if not env.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        errors.append("DATABASE_URL must point to PostgreSQL in production.")
    if not env.get("REDIS_URL", "").startswith(("redis://", "rediss://")):
        errors.append("REDIS_URL must use redis:// or rediss:// in production.")
    if not env.get("RATELIMIT_STORAGE_URI", "").startswith(("redis://", "rediss://")):
        errors.append("RATELIMIT_STORAGE_URI must use the production Redis service.")
    if env.get("FILE_ENCRYPTION_KEY") == env.get("INTEGRATION_ENCRYPTION_KEY"):
        errors.append("FILE_ENCRYPTION_KEY and INTEGRATION_ENCRYPTION_KEY must be different.")
    if env.get("SECRET_KEY") in {env.get("FILE_ENCRYPTION_KEY"), env.get("INTEGRATION_ENCRYPTION_KEY")}:
        errors.append("Application and data-encryption keys must be distinct.")
    if env.get("STORAGE_BACKEND", "").lower() != "s3" or not env.get("S3_BUCKET"):
        errors.append("Production requires STORAGE_BACKEND=s3 and S3_BUCKET.")
    if not env.get("PUBLIC_BASE_URL", "").startswith("https://"):
        errors.append("PUBLIC_BASE_URL must use HTTPS in production.")
    if env.get("COOKIE_SECURE", "false").lower() != "true":
        errors.append("COOKIE_SECURE must be true in production.")
    if env.get("SECURITY_HEADERS_ENABLED", "true").lower() != "true":
        errors.append("SECURITY_HEADERS_ENABLED must be true in production.")

    # Validate key encoding before a deployment accepts encrypted customer data.
    try:
        from cryptography.fernet import Fernet
        for key_name in ("FILE_ENCRYPTION_KEY", "INTEGRATION_ENCRYPTION_KEY"):
            value = env.get(key_name)
            if value:
                Fernet(value.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError):
        errors.append("Encryption keys must be valid Fernet keys.")
    return errors


def check_database_and_migrations(app):
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from app.extensions import db

    with app.app_context():
        with db.engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
            alembic_config = Config()
            alembic_config.set_main_option("script_location", str(ROOT / "migrations"))
            head = ScriptDirectory.from_config(alembic_config).get_current_head()
            if current != head:
                raise RuntimeError(
                    f"Database migration is not at head (current={current!r}, expected={head!r}). "
                    "Apply reviewed migrations before starting services."
                )
    return current


def check_redis(url):
    from redis import Redis
    client = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3,
                            health_check_interval=30)
    try:
        if client.ping() is not True:
            raise RuntimeError("Redis did not return PONG.")
    finally:
        client.close()


def check_s3(bucket, region):
    import boto3
    client = boto3.client("s3", region_name=region)
    client.head_bucket(Bucket=bucket)


def run_live_checks():
    from app import create_app

    app = create_app()
    revision = check_database_and_migrations(app)
    print(f"Database connection and migrations: OK ({revision})")
    check_redis(app.config["CELERY_BROKER_URL"])
    print("Redis broker connection: OK")
    check_redis(app.config["CELERY_RESULT_BACKEND"])
    print("Redis result backend connection: OK")
    check_s3(app.config["S3_BUCKET"], app.config["AWS_REGION"])
    print("Private S3 bucket access: OK")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-only", action="store_true",
                        help="validate environment variables without connecting to services")
    args = parser.parse_args(argv)
    errors = validate_environment()
    if errors:
        raise SystemExit("Production preflight failed:\n- " + "\n- ".join(errors))
    print("Production configuration: OK")
    if not args.config_only:
        run_live_checks()
    print("Production preflight passed.")


if __name__ == "__main__":
    main()
