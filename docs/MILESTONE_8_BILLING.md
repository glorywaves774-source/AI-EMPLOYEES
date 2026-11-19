# Milestone 8 — Subscription, Billing & SaaS Administration Centre

## Purpose

Move AI Workforce from a tenant/workforce application toward a commercially operable multi-business SaaS platform owned and administered by Kayron Global Tech Services.

## Commercial controls

The platform defines Starter, Growth and Business plans. Each plan controls:

- monthly price;
- billing currency;
- trial duration;
- maximum active AI employees;
- monthly task quota.

Prices are intentionally configuration-driven. The source does not invent or assert Kayron's final commercial pricing.

## Trial

Newly registered businesses receive a 14-day Starter trial. The subscription is created at registration and becomes expired when its trial period ends unless the business activates a paid plan.

Existing tenants created before Milestone 8 receive a trial subscription when they first open the Billing Centre, if they have no subscription record.

## Quota enforcement

Task creation is blocked when:

- the subscription is missing, expired, canceled or past due; or
- the plan's task quota has been reached.

AI employee activation is blocked when the active employee count has reached the plan's configured limit.

## Payments

The application creates payment records before redirecting to the selected provider.

### Paystack

- Transaction initialization uses the Paystack secret key.
- The provider reference is stored.
- The callback is informational only.
- `POST /billing/webhooks/paystack` verifies the `X-Paystack-Signature` HMAC SHA-512 signature.
- `charge.success` activates the subscription and records the payment.

### Stripe

- Checkout Session initialization is supported.
- The browser success page is informational only.
- `POST /billing/webhooks/stripe` validates the Stripe webhook signature.
- Successful checkout/payment events activate the subscription.
- Failed invoice payment events can mark a subscription `past_due`.

Provider dashboard configuration and live credentials remain deployment tasks.

## Renewals and cancellation

A successful provider payment resets the subscription billing period. Cancellation is scheduled at period end rather than immediately deleting access. Users can revoke the scheduled cancellation before the period ends.

For full automatic recurring billing, the provider account must be configured with the appropriate recurring product/price/subscription settings and webhook events.

## Invoices and payment history

Each confirmed payment has a persistent payment record. A corresponding invoice record is created or marked paid. The Billing Centre displays recent payments and invoices.

## Platform administration

The `/platform` area is separate from tenant membership. Platform administrators are stored in `platform_admins` and authenticated independently.

The administration centre provides:

- business overview;
- subscription overview;
- plan price and quota configuration;
- manual subscription status control;
- recent payment visibility;
- platform audit events.

Create the first platform administrator with:

```bash
flask --app run.py create-platform-admin
```

## Security

- Platform administrator passwords are bcrypt-hashed.
- Tenant billing routes use existing tenant membership/role enforcement.
- Payment activation is webhook-driven rather than trusted from browser redirects.
- Paystack and Stripe secrets are environment configuration and must not be committed.
- Subscription changes and administrative status changes are audited.

## Production completion checklist

Before accepting real customer payments:

1. Generate and inspect the Flask-Migrate migration.
2. Configure approved commercial prices in the platform administration centre.
3. Add Paystack and/or Stripe production credentials to Render secrets.
4. Register HTTPS webhook endpoints with the providers.
5. Test successful and failed payments in provider test mode.
6. Test trial expiry, upgrade, renewal, cancellation and cancellation reversal.
7. Configure provider recurring billing products/prices where automatic renewals are required.
8. Add provider-specific reconciliation and refund handling before full commercial launch.
9. Add scheduled expiry processing for subscriptions whose period ends without renewal.
10. Run a security review of webhook, platform-admin and payment workflows.
