# AI Workforce — Milestone 12
Enterprise multi-tenant AI workforce platform by Kayron Global Tech Services.

## What this milestone adds

### Business knowledge centre
- Tenant-scoped knowledge repositories.
- Secure upload of PDF, DOCX, TXT, Markdown and CSV documents (12 MB per file).
- File validation, text extraction and chunking. Scanned/image-only PDFs requiring OCR are rejected with a clear message.
- Application-level Fernet encryption before private local or S3 object storage. S3 uploads also request server-side AES-256 encryption.
- Tenant-scoped keyword search over extracted document sections.
- Download and delete controls with audit records.

### Employee-specific knowledge access
- Owners, administrators and managers can grant repository access to individual AI employees.
- Specialist agents and the Team Coordinator retrieve only matching chunks from repositories explicitly granted to that employee.
- Retrieved source names are passed with the excerpts; document text is explicitly treated as untrusted reference material.
- Retrieval events are audited against the requesting user, AI employee and task without writing document content or search terms into the audit log.
- Employees have no repository access by default.

### Integration foundation
- Tenant-scoped integration connection model.
- Separate encrypted credential-envelope helper using `INTEGRATION_ENCRYPTION_KEY`.
- Google Drive OAuth, Gmail / Microsoft Graph and external API security architecture documented in `docs/INTEGRATION_ARCHITECTURE.md`.
- The provider integrations are **not live** in this milestone: no OAuth callback, Drive sync, mailbox access or email sending is enabled.

## Local setup
Python 3.12 and Redis are required. PostgreSQL is recommended for integration testing.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Configure environment variables (never commit secrets):
- `SECRET_KEY`: long random session secret.
- `DATABASE_URL`: PostgreSQL URL; SQLite is acceptable only for local smoke tests.
- `REDIS_URL`: Redis connection URL for Celery.
- `OPENAI_API_KEY`: OpenAI API key.
- `OPENAI_MODEL`: optional model override.
- `FILE_ENCRYPTION_KEY`: a generated Fernet key for uploaded files.
- `INTEGRATION_ENCRYPTION_KEY`: a separate generated Fernet key for future provider credentials.
- `STORAGE_BACKEND`: `local` for development or `s3` for production.

Generate two independent Fernet keys:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Run the command twice and store the results as secrets. Never reuse the same key for file encryption and integration credentials. Losing either key makes the corresponding encrypted data unrecoverable; back up keys securely and restrict access.

For local development, use `STORAGE_BACKEND=local` and `PRIVATE_UPLOAD_ROOT=./instance/knowledge-private`. The storage directory is private and should not be placed under `app/static` or served directly by a web server.

For production, configure a private S3 bucket, `STORAGE_BACKEND=s3`, `S3_BUCKET`, `AWS_REGION`, and restricted AWS credentials or an appropriate workload identity. Block public access on the bucket, enable lifecycle/backup policies, and restrict the application's IAM policy to the required `knowledge/` prefix. Render's blueprint is configured for S3 and requires the bucket, AWS credentials, and both encryption keys to be added as secrets. Set the exact same `FILE_ENCRYPTION_KEY` and `INTEGRATION_ENCRYPTION_KEY` values on both the web service and worker service; mismatched keys will make encrypted data unreadable.

## Database migration

Milestone 6 introduced the knowledge and integration schema. The current repository now carries a frozen Alembic baseline and subsequent versioned revisions. For current installations, use the migration procedure in the later **Database migration** section and `docs/GATE2B_MIGRATION_ORCHESTRATION.md`. Do not initialize a second migration directory or regenerate the historical baseline.

Start the web app and worker separately:

```bash
flask --app run.py run
celery -A worker.celery worker --loglevel=INFO
```

## Important limitations and production readiness

This is a development increment, not a production-ready deployment. The current document search is keyword-based, not vector/semantic search. OCR, malware scanning, DLP/classification, retention automation, legal hold, versioning, document-level ACLs, provider OAuth flows, Drive sync, email access and email sending are not implemented. Extracted text is stored in PostgreSQL; enable provider-managed database encryption at rest, strict database access controls and backups.

Before onboarding real businesses:
1. Add PostgreSQL row-level security and transaction-local tenant context, then test tenant isolation for web requests and Celery workers.
2. Add malware scanning and content-disarm/reconstruction where appropriate, plus upload quotas, rate limits and abuse monitoring.
3. Add formal retention/deletion workflows covering object storage, extracted chunks, backups and audit records.
4. Add MFA, email verification, password recovery, session rotation, security headers and account lockout controls.
5. Add idempotent job handling, queue monitoring, dead-letter handling and operational alerts.
6. Add cross-tenant, employee-permission, upload/download, encryption-key-rotation and backup-restore tests.
7. Complete a security review before enabling any OAuth provider or external write action.

Syntax compilation and ZIP integrity are the validation checks for this package. Runtime Flask/database/Redis/OpenAI/S3 integration tests and a Render deployment have not been performed in this environment.


## Milestone 7 — Analytics & Operational Intelligence

Open **Analytics** from the top navigation. Owners, admins and managers can view tenant-scoped reports and export CSV. Token cost estimates are disabled by default; see `docs/MILESTONE_7_ANALYTICS.md`.


## Milestone 8 — Subscription, Billing & SaaS Administration Centre

This increment adds the commercial SaaS foundation for multi-business AI Workforce, with **Kayron Global Tech Services** as the platform administration owner.

### Included
- Starter, Growth and Business subscription foundations are present in this Milestone 12 codebase. The master product specification instead defines Starter, Professional and Enterprise; reconcile the live plan catalogue before enabling paid customer subscriptions.
- 14-day initial free trial.
- Tenant-scoped subscription records with billing periods and cancellation scheduling.
- Configurable plan pricing in GHS by default; no business pricing is hard-coded as a commercial claim.
- AI employee limits per plan.
- Monthly task quotas per plan, enforced when assignments are created.
- Active AI employee quota enforcement when an employee is activated.
- Subscription plan-change requests with tenant audit records.
- Payment records and invoice records.
- Paystack transaction initialization and signed webhook verification.
- Stripe Checkout initialization and signed webhook verification.
- Payment-confirmed subscription activation and billing-period renewal handling.
- Subscription cancellation at period end and cancellation reversal.
- Platform administration centre for businesses, plans, subscriptions and recent payments.
- Secure platform administrator accounts stored as password hashes.
- CLI setup for the first platform administrator.

### Platform administrator setup

After applying the database migration:

```bash
flask --app run.py create-platform-admin
```

The command asks for an administrator email, name and password. It does not store the plaintext password.

Open the platform administration centre at `/platform/login`.

### Billing configuration

Prices are intentionally configurable rather than invented:

```text
BILLING_CURRENCY=GHS
PLAN_STARTER_AMOUNT=0
PLAN_GROWTH_AMOUNT=0
PLAN_BUSINESS_AMOUNT=0
```

Set the three plan amounts to the commercial prices approved by Kayron Global Tech Services before onboarding paying customers.

For Paystack, configure `PAYSTACK_SECRET_KEY` and register the public webhook endpoint:

```text
POST /billing/webhooks/paystack
```

For Stripe, configure `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` and register:

```text
POST /billing/webhooks/stripe
```

Payment activation is webhook-driven. The browser callback/success page does not itself mark a payment as paid.

### Database migration

The repository now has a frozen initial schema snapshot (`0001_initial`) and versioned orchestration migrations (`0002_team_orchestration`, `0003_team_execution_steps`, `0004_review_recovery_controls`). Back up the database, then apply reviewed migrations:

```bash
flask --app run.py db current
flask --app run.py db upgrade
flask --app run.py db current
```

Do not run `db.create_all()` in production. For future model changes, generate a new revision with `flask --app run.py db migrate -m "describe change"`, review the generated operations, test upgrade and downgrade against a disposable database, and commit the revision. Never edit a migration that has already been deployed. See `docs/GATE2B_MIGRATION_ORCHESTRATION.md` for existing-database and new-database rollout steps.

### Production notes

- Keep Paystack and Stripe secrets in Render environment secrets, never in Git.
- Configure the payment provider webhook URLs over HTTPS.
- Use provider webhook events as the authoritative payment signal.
- Confirm the exact approved commercial prices before changing the plan amounts.
- Configure a real recurring billing product/price strategy with the selected payment provider before advertising automatic renewals to customers.
- The current implementation provides the integration and webhook foundation; provider dashboard configuration and live credential validation still have to be completed in the deployment environment.


## Milestone 9 — Billing Operations & Production Readiness

This release hardens the Milestone 8 commercial billing foundation with webhook idempotency, refund tracking, subscription expiry processing, and scheduled billing operations. See `docs/MILESTONE_9_BILLING_OPERATIONS.md`.

## Production release checklist

Milestone 11 adds `docs/MILESTONE_11_TESTING_DEPLOYMENT.md`, `gunicorn.conf.py`, `scripts/production_check.py`, `/healthz`, `/readyz`, and security regression tests. Review that document before deploying to Render. Production databases must be upgraded with Flask-Migrate/Alembic rather than `db.create_all()`.

## Milestone 12 — Production Hardening, Observability & SaaS Launch Controls

This milestone adds persistent security-event monitoring, platform administrator lockout/MFA, tenant data export, database migration baseline, backup/restore helpers, Render scheduled operational jobs, request correlation IDs and production release documentation. See `docs/MILESTONE_12_PRODUCTION_HARDENING.md`.


## Milestone 12 security and release notes

- `TRUST_PROXY_COUNT` defaults to `0` locally. Set it only to the exact number of trusted reverse-proxy hops in front of the service. The application now uses Werkzeug `ProxyFix` for forwarded client/protocol metadata; security-event IP logging reads `request.remote_addr` after that middleware. Do not expose the app directly while trusting forwarded headers.
- Platform administrator MFA failures now use the persisted administrator lockout fields. Configure `PLATFORM_ADMIN_MFA_MAX_ATTEMPTS` and `PLATFORM_ADMIN_MFA_LOCKOUT_MINUTES`. A successful MFA challenge resets the counter; reaching the threshold clears the pending MFA session and locks the administrator.
- Platform administrator post-login redirects are restricted to same-host relative paths to prevent open redirects.
- `ENVIRONMENT=production` makes app startup reject a weak/default secret, SQLite, or non-secure session cookies. Run `python scripts/production_check.py` as part of production release validation.
- Gate 2B replaces the metadata-driven initial Alembic migration with a frozen explicit snapshot and adds `0002_team_orchestration`. Gate 2C adds `0003_team_execution_steps`; Gate 2D adds `0004_review_recovery_controls`. Review all gate guides and rehearse the full migration chain on a PostgreSQL staging copy before production.
- Runtime tests require installing `requirements.txt`; this audit environment could not access the package index, so the new Flask integration tests are included but have not been executed here.


## Gate 2A — Task Execution Controls

The first Stage 4 increment adds tenant-scoped cooperative task cancellation, cancellation audit events, worker cancellation checkpoints, and 9/10-minute Celery soft/hard execution limits. See `docs/GATE2A_TASK_EXECUTION_CONTROLS.md`. Gate 2B and Gate 2C subsequently add the migration foundation and queue-backed specialist orchestration.


## Gate 2B — Migration Foundation & Team Orchestration Data Model

Gate 2B freezes the Milestone 12 schema baseline and adds tenant-safe team execution records, task dependency edges, cycle detection, readiness evaluation, and atomic token/cost budget reservations. See `docs/GATE2B_MIGRATION_ORCHESTRATION.md`.

## Gate 2C — AI Team Orchestration

Gate 2C connects the Team Coordinator to the durable Celery workflow. It validates a bounded specialist plan, persists each work unit, dispatches independent steps in parallel Celery chords, releases dependent steps in later waves, shares prerequisite outputs, tracks usage and failures, and consolidates completed contributions with an explicit human-review decision. The task detail page now exposes specialist plan/progress. Apply migration `0003_team_execution_steps` after a verified backup. SQLite migration and pure plan tests pass, but live PostgreSQL/Redis/Celery/OpenAI/Render integration has not been run in this environment. Review `docs/GATE2C_TEAM_ORCHESTRATION.md` and `docs/GATE2D_RELIABILITY_HUMAN_REVIEW.md` before staging rollout.


## Gate 2D — Workflow Reliability & Human Review

Gate 2D adds an owner/admin human-review decision on consolidated AI deliverables, an approvals-centre queue for deliverables awaiting review, auditable approval/rejection notes, and bounded manual recovery for failed/blocked specialist steps. Recovery preserves completed specialist contributions and never re-runs them. It is not an automatic Redis outage recovery mechanism, and review decisions do not execute external actions. Apply `0004_review_recovery_controls` after `0003_team_execution_steps`; back up and rehearse the migration on PostgreSQL staging. See `docs/GATE2D_RELIABILITY_HUMAN_REVIEW.md`.

## Gate 2E — production integration and release verification

Gate 2E adds live dependency preflight for PostgreSQL/migration head, Redis broker/result backend and private S3 access; production config validation now requires the OpenAI key and independent valid Fernet keys. Render applies reviewed migrations in the web pre-deploy command, then web and worker processes run the live preflight. `/readyz` checks database and Redis availability. A harmless `ops.ping` task and `scripts/release_smoke.py` verify that a deployed Celery worker can consume work. See `docs/GATE2E_PRODUCTION_INTEGRATION.md` for the staging sequence and opt-in integration tests. Live provider/deployment checks still need to be run in the user's configured staging environment.
