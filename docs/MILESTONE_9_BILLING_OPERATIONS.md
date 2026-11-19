# Milestone 9 — Billing Operations & Production Readiness

Milestone 9 hardens the Milestone 8 commercial billing foundation before real customer payments are enabled.

## Included

- Idempotent Paystack and Stripe webhook event processing.
- Persistent webhook event records with payload hashes and processing status.
- Refund and partial-refund payment states.
- Subscription-expiry processing when a renewal webhook has not arrived.
- Hourly Celery billing-expiry task schedule.
- Manual CLI fallback: `flask --app run.py process-subscription-expirations`.
- Audit records when subscriptions expire.
- Safer Stripe timestamp/signature validation.
- Duplicate webhook delivery protection.

## Important operational rule

Payment-provider webhooks remain the authoritative payment signal. The expiry worker is a safety net: it prevents indefinite access when a billing period has ended without a successful renewal event.

## Migration

Milestone 9 adds `billing_webhook_events` and refund fields to `payments`. Generate and inspect a controlled migration:

```bash
flask --app run.py db migrate -m "milestone 9 billing operations and webhook idempotency"
flask --app run.py db upgrade
```

## Celery

Run the worker and a Celery beat process so the hourly expiry schedule executes:

```bash
celery -A worker.celery worker --loglevel=INFO
celery -A worker.celery beat --loglevel=INFO
```

## Production checklist

1. Generate and review the database migration.
2. Configure production Paystack/Stripe credentials only in Render secrets.
3. Register HTTPS webhook endpoints.
4. Verify successful payment, duplicate webhook, failed payment and refund scenarios in provider test mode.
5. Verify trial expiry and paid-period expiry.
6. Configure recurring billing products/prices at the selected provider.
7. Test restore/backup and audit-log retention before commercial launch.
