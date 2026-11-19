# AI Workforce — Milestone 12 Gate 1 Stabilisation

This increment continues from the supplied Milestone 12 source. It does not rebuild the application or claim that the full master specification is complete.

## Changes made

1. **Trusted proxy boundary**
   - Added Werkzeug `ProxyFix` using `TRUST_PROXY_COUNT` for forwarded client IP and protocol metadata.
   - Changed the local default from one trusted proxy to zero. Render web is explicitly configured for one proxy hop.
   - Security-event IP capture now uses `request.remote_addr`, not the raw `X-Forwarded-For` header.
   - Added validation and bounding for externally supplied request correlation IDs.

2. **Platform administrator MFA protection**
   - Invalid MFA challenges now increment the persisted failed-login counter.
   - The configured threshold locks the administrator, records a high-severity security event and audit log, and clears the pending MFA session.
   - Successful MFA resets the counter and lockout.
   - Datetime comparisons handle SQLite's naive datetime return values as UTC.

3. **Authentication redirect safety**
   - Platform login and MFA success redirects now accept only same-host relative paths.

4. **Production configuration**
   - `ENVIRONMENT=production` rejects a weak/default session secret, SQLite database, or insecure session cookie at app startup.
   - PostgreSQL URLs supplied by Render as `postgres://` or `postgresql://` are normalised to the installed psycopg 3 dialect. `scripts/production_check.py` checks production mode, secret length, PostgreSQL, separate encryption keys, HTTPS public URL, secure cookies, S3 storage and required rate-limit storage.
   - Render web starts only after the production check succeeds. Worker and scheduled jobs are marked as production processes and receive secure-cookie configuration.

5. **Backup and migration safety**
   - Backup scripts use restrictive file permissions.
   - Restore now requires `RESTORE_CONFIRM=YES`, verifies the backup exists, uses a single transaction for PostgreSQL restore and a temporary replacement file for SQLite.
   - The original baseline migration's destructive `drop_all()` downgrade is disabled. Its upgrade remains metadata-driven and is explicitly marked for replacement by a reviewed, immutable schema snapshot before production migration automation.
   - Backup directories are ignored by Git.

6. **Documentation and tests**
   - README release label corrected to Milestone 12 and Python 3.12 requirement documented.
   - Added integration tests for registered platform routes, MFA lockout, spoofed forwarded-IP handling and external redirect rejection.
   - Added Gate 1 deployment and release notes.

## Validation results

| Check | Result |
|---|---|
| Python compilation (`compileall`) | Passed |
| Python AST parse of all source files | Passed |
| Shell syntax for backup/restore scripts | Passed |
| Render YAML parse | Passed |
| Production configuration check with synthetic values | Passed |
| Full pytest suite | Blocked: Flask is not installed in the available environment; dependency installation could not be completed due unavailable package-index/network access |
| Live PostgreSQL/Redis/Render validation | Not performed |

## Remaining Gate 1 blocker

The initial Alembic migration still calls `metadata.create_all()` in `upgrade()`, so it is not yet an immutable schema snapshot. The destructive downgrade has been disabled, but a reviewed explicit migration baseline and migration tests against a fresh PostgreSQL database and a Milestone 12 upgrade database remain necessary before production migrations can be considered safe.

## Important release limitations

This update does not implement the missing workflow automation engine, real OAuth integrations, semantic/vector knowledge retrieval, full AI-team orchestration, complete data import/export, or the entire enterprise feature set. It also does not establish production readiness without the blocked runtime and staging tests.
