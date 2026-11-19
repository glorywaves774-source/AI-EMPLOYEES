# Gate 2E — Production Integration & Release Verification

Gate 2E strengthens deployment checks and supplies an opt-in staging verification path. It does not claim that this repository has been exercised against a live Render, PostgreSQL, Redis, S3 or OpenAI account from this development environment.

## Deployment preflight

`scripts/production_check.py` now validates production configuration and performs read-only live checks before web and worker processes start:

- production mode, strong distinct secrets, valid Fernet keys and HTTPS public URL;
- PostgreSQL connection and Alembic revision equal to the current migration head;
- Redis broker and result-backend connectivity;
- access to the configured private S3 bucket;
- required OpenAI API key presence (the preflight does not make a billable model call).

The Render web service runs `flask --app run.py db upgrade` as its pre-deploy command. This runs reviewed migrations before the new web process starts. The worker runs the same live preflight before starting Celery. Never treat this as a substitute for a verified database backup and staging rehearsal.

Use `python scripts/production_check.py --config-only` to validate environment values without connecting to dependencies. The default command is the full live preflight and is intended for a configured deployment environment.

## Readiness and worker checks

- `/healthz` remains a process/liveness endpoint.
- `/readyz` checks the database and, when configured with Redis, the Redis broker. It returns HTTP 503 if either required dependency is unavailable.
- `ops.ping` is a no-side-effect Celery task used only to verify that a real worker can consume and return a task result.
- `python scripts/check_worker.py` sends that probe and waits for the worker response.
- `python scripts/release_smoke.py` checks the deployed HTTPS `/healthz` and `/readyz` endpoints and then verifies the worker probe.

Run the release smoke command from a trusted operator environment with `PUBLIC_BASE_URL` and `REDIS_URL` set to the staging deployment. It places one harmless task on the queue.

## Opt-in live integration tests

`tests/integration/test_live_stack.py` is skipped by default. On a dedicated, disposable staging stack only, set `AI_WORKFORCE_RUN_LIVE_INTEGRATION=1` and run:

```bash
python -m pytest -q tests/integration
```

The tests verify that the web readiness endpoint sees PostgreSQL and Redis and that the live worker executes `ops.ping`. They do not create or modify customer records. Do not point these tests at production.

## Recommended staging sequence

1. Create a dedicated PostgreSQL database, Redis instance and private S3 bucket.
2. Configure independent application, file-encryption and integration-encryption secrets. Store all secrets in the hosting provider's secret manager.
3. Deploy the web service and allow its pre-deploy migration command to finish. Confirm the Alembic revision is at head.
4. Deploy the Celery worker and confirm its startup preflight passes.
5. Run `python scripts/production_check.py` from the same environment configuration.
6. Run `python scripts/release_smoke.py` from an operator machine.
7. Run the opt-in live integration tests against that staging environment.
8. Exercise tenant isolation, cancellation, failed-step recovery, approval/rejection, file upload/download and backup restore using dedicated test tenants and test documents.
9. Confirm OpenAI requests with a controlled low-cost test assignment and review token/cost accounting. This step is intentionally manual because it may incur provider charges.
10. Record results, service versions, migration revision, operator and date before approving production rollout.

## Boundaries and remaining verification

- This environment cannot install missing Python packages because package-index network access is unavailable. Flask is absent here, so the complete application suite and live Flask/Celery tests could not run.
- No production credentials or live Render services were supplied. PostgreSQL, Redis, S3, OpenAI and Render connectivity remain unverified.
- OpenAI API availability, actual provider billing reconciliation, SMTP delivery and customer-facing OAuth integrations are not validated by the preflight.
- A successful startup check is not a disaster-recovery drill. Perform a backup restore and test data integrity separately.
- Do not enable customer workloads until the staging sequence has passed and operational alerting, backup retention and incident ownership are configured.
