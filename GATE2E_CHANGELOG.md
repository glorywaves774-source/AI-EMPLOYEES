# Gate 2E — Production Integration & Release Verification

## Added
- Live production preflight for required environment, Fernet keys, PostgreSQL connection and migration head, Redis broker/result backend and private S3 bucket access.
- Required production OpenAI API key presence check without making a billable API request.
- Render web pre-deploy database migration command.
- Shared production preflight before Celery worker startup.
- Redis-aware `/readyz` dependency check while retaining `/healthz` as liveness.
- No-side-effect `ops.ping` Celery task.
- `scripts/check_worker.py` and `scripts/release_smoke.py` for post-deploy verification.
- Opt-in live staging integration tests in `tests/integration/test_live_stack.py`.

## Changed
- Production readiness now fails when the configured Redis broker is unavailable.
- Production deployment checks no longer stop at environment-variable presence; they verify core dependency reachability and migration state.

## Validation
- Focused local policy, dependency graph, migration contract, team plan and reliability tests: 16 passed.
- Python compileall: passed.
- Full application test suite and live service tests: not run; Flask is unavailable in this environment and package-index network access prevented installing project requirements.
- PostgreSQL, Redis, S3, OpenAI and Render connectivity: not tested.

## Rollout caution
Back up the database, rehearse the Render pre-deploy migration on PostgreSQL staging, confirm S3 bucket permissions, and run the release smoke test against staging before production.
