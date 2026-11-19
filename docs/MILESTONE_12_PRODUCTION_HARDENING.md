# Milestone 12 — Production Hardening, Observability & SaaS Launch Controls

AI Workforce is a commercial multi-tenant SaaS owned by **Kayron Global Tech Services**. This milestone hardens the production boundary after Milestone 11.

## Security monitoring

Every request receives a correlation ID. Security-sensitive events are persisted in `security_events` with tenant/user/platform-admin scope, severity, IP, user agent and request ID. The platform administration centre exposes recent security events for operational review.

Security events include login failures, account lockouts, MFA challenges/success/failure, platform administrative changes and tenant data exports.

Retention is configurable with `SECURITY_EVENT_RETENTION_DAYS` and can be enforced using `flask --app run.py purge-security-events`.

## Platform administrator protection

Platform administrator login now supports failed-attempt lockout and MFA challenge. MFA can be enabled for an existing platform administrator with:

```bash
flask --app run.py enable-platform-admin-mfa
```

The command prints the authenticator provisioning secret/URI and one-time recovery codes. Recovery codes are stored as hashes.

## Privacy and tenant data export

Tenant owners can request an operational JSON export at `/workspace/settings/data-export`. The export is tenant-scoped and includes workspace membership metadata, departments, AI employees and task metadata. The export action is audited.

This is an operational export, not a legal-compliance certification. Retention schedules, legal holds, backup deletion and regulatory erasure procedures must be defined for the applicable jurisdiction and customer contract.

## Database baseline

A Flask-Migrate/Alembic baseline is included under `migrations/`. New environments should use:

```bash
flask --app run.py db upgrade
```

Future schema changes should be generated and reviewed with `flask db migrate` and then applied with `flask db upgrade`.

Always take a verified backup before a production migration.

## Backup and recovery

Helper scripts are provided:

```bash
DATABASE_URL="$DATABASE_URL" BACKUP_DIR=./backups ./scripts/backup_database.sh
DATABASE_URL="$DATABASE_URL" BACKUP_FILE=./backups/ai_workforce_TIMESTAMP.dump RESTORE_CONFIRM=YES ./scripts/restore_database.sh
```

PostgreSQL production backups should be encrypted, access-controlled and tested through scheduled restore drills. Encryption keys for private knowledge and integration credentials must be backed up separately under controlled key-management procedures.

## Render operations

`render.yaml` now includes web, worker, Redis, PostgreSQL and scheduled jobs for subscription-expiry processing and security-event retention.

The web service uses `/readyz` as the health check, so deployment readiness includes a live database connectivity check.

## Release checklist

Before production onboarding:

- Apply and verify database migrations in staging.
- Confirm `SECRET_KEY`, encryption keys, database, Redis, SMTP and AI provider secrets are present.
- Confirm private object storage is not publicly readable.
- Run the complete test suite in an environment with project dependencies installed.
- Verify login lockout, MFA, password recovery, email verification and platform-admin MFA.
- Verify cross-tenant access is denied for every tenant-scoped route and worker operation.
- Test database backup and restore on a separate environment.
- Confirm Render web and worker services share the same required secrets.
- Configure external alerting for repeated 5xx errors, queue failures, database failures and suspicious authentication events.
- Perform a final security review before enabling customer data or external write integrations.


## Gate 1 stabilisation update

The post-Milestone-12 stabilisation increment applies trusted proxy handling through Werkzeug `ProxyFix`, records client IPs from the trusted `request.remote_addr`, validates correlation IDs, adds platform-administrator MFA lockout, and prevents external post-login redirects. Production startup now rejects unsafe secret/database/cookie settings. The Render web start command runs `scripts/production_check.py` before Gunicorn; the worker receives production environment and secure-cookie settings as well.

The restore helper now requires `RESTORE_CONFIRM=YES`, verifies the backup file exists, uses a single PostgreSQL restore transaction, and performs SQLite replacement through a temporary file. Backup scripts use restrictive file permissions. The initial migration downgrade is disabled because its previous `drop_all()` could delete all application data. Gate 2B replaces the metadata-driven upgrade with a frozen explicit schema snapshot and adds revision `0002_team_orchestration`. See `docs/GATE2B_MIGRATION_ORCHESTRATION.md`; PostgreSQL staging rehearsal is still required before production migration automation is considered validated.


## Gate 2D review and recovery controls

Revision `0004_review_recovery_controls` adds persisted reviewer identity, decision, timestamp and note fields to team executions, plus a recovery counter. The application exposes a tenant-scoped review decision for owner/admin users and a bounded manual retry for failed/blocked specialist steps. Retry eligibility is capped at three total step attempts and preserves successful contributions. These controls do not provide automatic recovery from a Redis outage or a crashed chord callback. PostgreSQL staging, Redis/Celery worker tests, and a full deployment rehearsal remain required.

## Gate 2E production integration checks

The production preflight now validates PostgreSQL connectivity and migration head, Redis broker/result backend, private S3 bucket access, OpenAI key presence and independent Fernet encryption keys. Render applies migrations with a web pre-deploy command; both web and worker start commands run the preflight. `/readyz` now includes Redis when the production broker is Redis. `scripts/release_smoke.py` checks the deployed health/readiness endpoints and submits the harmless Celery `ops.ping` task. See `docs/GATE2E_PRODUCTION_INTEGRATION.md`. These checks have not been run against a live Render environment from this workspace.
