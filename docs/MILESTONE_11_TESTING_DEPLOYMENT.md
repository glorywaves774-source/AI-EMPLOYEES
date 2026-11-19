# AI Workforce — Milestone 11
## Testing, Deployment & Production Release Candidate

Milestone 11 hardens the Milestone 10 security foundation for production operation. It adds production health/readiness endpoints, request correlation IDs, security regression tests, production Gunicorn configuration, Render readiness checks, production environment validation, and release procedures.

### Automated test suite
Run from the project root after installing dependencies:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
pytest -q
```

The security regression suite covers security headers, health/readiness endpoints, login lockout and one-time password-reset tokens. Existing knowledge, agent routing, smoke, and integration tests remain part of the suite.

### Database migrations
This release continues to use Flask-Migrate/Alembic. **Do not use `db.create_all()` against a production database.** On the first production deployment, establish a migration baseline from the exact production schema, review it, commit it to source control, and then use:

```bash
flask --app run.py db upgrade
```

For schema changes during development:

```bash
flask --app run.py db migrate -m "describe change"
flask --app run.py db upgrade
```

Before every release, inspect the generated Alembic revision and confirm it contains only the intended schema changes.

### Render deployment
The included `render.yaml` configures:
- Flask web service behind Gunicorn
- `/readyz` as the Render health check
- PostgreSQL database
- Redis for Celery and rate-limit storage
- background Celery worker
- encrypted private storage through S3
- production security and email environment variables

The web service should run migrations as an explicit deployment step before serving a schema-dependent release. Do not silently create or alter production tables from application startup.

### Required production secrets
Set unique production values for:
- `SECRET_KEY`
- `DATABASE_URL`
- `FILE_ENCRYPTION_KEY`
- `INTEGRATION_ENCRYPTION_KEY`
- `PUBLIC_BASE_URL`
- `REDIS_URL`
- S3 credentials/bucket settings
- `OPENAI_API_KEY`
- SMTP credentials for verification and password-reset delivery

Set `COOKIE_SECURE=true` and `SECURITY_HEADERS_ENABLED=true`.

### Release verification
After deployment:

```bash
curl -fsS https://YOUR-DOMAIN/healthz
curl -fsS https://YOUR-DOMAIN/readyz
```

Then verify manually:
1. registration and email verification;
2. login and lockout behavior;
3. MFA setup and MFA login;
4. password reset;
5. tenant/workspace isolation;
6. workforce task creation and execution;
7. approvals;
8. knowledge upload and retrieval;
9. billing dashboard and webhook handling;
10. platform administration;
11. Celery worker execution;
12. logs and error monitoring.

### Backup and recovery
The PostgreSQL database is the system of record. Enable automated database backups at the hosting layer and periodically perform a restore test into a non-production environment. S3/private uploads must use versioning or an equivalent recovery policy appropriate to the chosen storage configuration.

A backup is not considered validated until a restore has been completed and the application passes `/readyz` plus the release smoke tests against the restored copy.

### Observability
Gunicorn access/error logs are emitted to stdout/stderr for Render log collection. Every application response receives an `X-Request-ID`; retain that identifier when investigating a customer-visible error so application logs can be correlated.

### Production configuration check
Run:

```bash
python scripts/production_check.py
```

The check fails when required production secrets or critical security flags are missing.

### Known release discipline
The application source is the deployable artifact. Never patch production files manually. Commit source changes, migration revisions, configuration changes, and tests together, deploy from the reviewed Git revision, and verify the resulting service through the health/readiness endpoints and release smoke tests.
