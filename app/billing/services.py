
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import urllib.error
import urllib.request
import urllib.parse
import uuid
from flask import current_app
from app.extensions import db
from app.security_service import as_utc
from app.models import (
    SubscriptionPlan, TenantSubscription, SubscriptionChangeRequest,
    Payment, Invoice, AuditLog, BillingWebhookEvent
)

PLAN_DEFAULTS = [
    ("starter", "Starter", "For small teams getting started with AI Workforce.", 3, 100),
    ("growth", "Growth", "For growing businesses with a broader AI workforce.", 10, 500),
    ("business", "Business", "For established businesses running larger AI operations.", 30, 2000),
]

def ensure_default_plans():
    changed = False
    for code, name, description, employees, tasks in PLAN_DEFAULTS:
        plan = SubscriptionPlan.query.filter_by(code=code).first()
        if not plan:
            plan = SubscriptionPlan(
                code=code, name=name, description=description,
                amount=Decimal(str(current_app.config.get(f"PLAN_{code.upper()}_AMOUNT", "0"))),
                currency=current_app.config.get("BILLING_CURRENCY", "GHS"),
                billing_interval="monthly", trial_days=14,
                max_ai_employees=employees, monthly_task_limit=tasks,
            )
            db.session.add(plan)
            changed = True
        else:
            # Limits are application policy; prices remain configurable.
            plan.max_ai_employees = employees
            plan.monthly_task_limit = tasks
    if changed:
        db.session.flush()
    return SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.amount.asc()).all()

def create_trial_subscription(tenant_id):
    ensure_default_plans()
    plan = SubscriptionPlan.query.filter_by(code="starter", is_active=True).first()
    now = datetime.now(timezone.utc)
    sub = TenantSubscription.query.filter_by(tenant_id=tenant_id).first()
    if sub:
        return sub
    sub = TenantSubscription(
        tenant_id=tenant_id, plan_id=plan.id, status="trialing",
        trial_ends_at=now + timedelta(days=plan.trial_days),
        current_period_start=now,
        current_period_end=now + timedelta(days=plan.trial_days),
        provider="manual",
    )
    db.session.add(sub)
    return sub

def current_subscription(tenant_id):
    sub = TenantSubscription.query.filter_by(tenant_id=tenant_id).first()
    if not sub:
        return None
    now = datetime.now(timezone.utc)
    if sub.status == "trialing" and sub.trial_ends_at and as_utc(sub.trial_ends_at) <= now:
        sub.status = "expired"
        db.session.commit()
    elif sub.status in {"active", "past_due"} and sub.current_period_end and as_utc(sub.current_period_end) <= now:
        if sub.cancel_at_period_end or sub.status == "past_due":
            sub.status = "expired"
            if not sub.canceled_at:
                sub.canceled_at = now
            db.session.commit()
    return sub


def record_webhook_event(provider, event_id, event_type, raw_body):
    """Create an idempotency record; return (record, already_processed)."""
    if not event_id:
        event_id = hashlib.sha256(raw_body).hexdigest()
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    existing = BillingWebhookEvent.query.filter_by(provider=provider, event_id=str(event_id)).first()
    if existing:
        return existing, existing.status == "processed"
    event = BillingWebhookEvent(provider=provider, event_id=str(event_id),
                                 event_type=event_type or "", payload_hash=payload_hash)
    db.session.add(event)
    db.session.flush()
    return event, False


def process_subscription_expirations():
    now = datetime.now(timezone.utc)
    subscriptions = TenantSubscription.query.filter(
        TenantSubscription.current_period_end.isnot(None),
        TenantSubscription.current_period_end <= now,
        TenantSubscription.status.in_(["active", "trialing", "past_due"])
    ).all()
    changed = 0
    for sub in subscriptions:
        if sub.status == "active" and not sub.cancel_at_period_end and sub.provider in {"stripe", "paystack"}:
            # A provider webhook should extend a paid recurring subscription. If it did not,
            # access is conservatively suspended at the period boundary rather than granted indefinitely.
            sub.status = "expired"
        else:
            sub.status = "expired"
        sub.canceled_at = sub.canceled_at or now
        changed += 1
        db.session.add(AuditLog(tenant_id=sub.tenant_id, actor_user_id=None,
                                action="subscription.expired", target_type="subscription",
                                target_id=str(sub.id), details_json={"reason": "billing_period_ended"}))
    if changed:
        db.session.commit()
    return changed


def mark_payment_refunded(payment, amount=None, provider_event=None):
    refund_amount = Decimal(str(amount)) if amount is not None else Decimal(payment.amount)
    payment.refunded_amount = min(Decimal(payment.amount), refund_amount)
    payment.refunded_at = datetime.now(timezone.utc)
    payment.status = "refunded" if payment.refunded_amount >= Decimal(payment.amount) else "partially_refunded"
    payment.metadata_json = {**(payment.metadata_json or {}), "refund_event": provider_event or ""}
    return payment


def ensure_tenant_subscription(tenant_id):
    sub = TenantSubscription.query.filter_by(tenant_id=tenant_id).first()
    if sub:
        return sub
    return create_trial_subscription(tenant_id)

def task_usage(tenant_id):
    sub = current_subscription(tenant_id)
    if not sub:
        return 0
    from app.models import WorkforceTask
    start = sub.current_period_start
    end = sub.current_period_end
    q = WorkforceTask.query.filter(WorkforceTask.tenant_id == tenant_id)
    if start:
        q = q.filter(WorkforceTask.created_at >= start)
    if end:
        q = q.filter(WorkforceTask.created_at < end)
    return q.count()

def can_create_task(tenant_id):
    sub = current_subscription(tenant_id)
    if not sub or sub.status not in {"trialing", "active"}:
        return False, "Your subscription is not active. Choose a plan to continue."
    used = task_usage(tenant_id)
    if used >= sub.plan.monthly_task_limit:
        return False, f"You have reached the {sub.plan.name} plan task quota ({sub.plan.monthly_task_limit} tasks for this billing period)."
    return True, ""

def can_activate_employee(tenant_id):
    sub = current_subscription(tenant_id)
    if not sub or sub.status not in {"trialing", "active"}:
        return False, "Your subscription is not active. Choose a plan to continue."
    from app.models import AIEmployee
    active = AIEmployee.query.filter_by(tenant_id=tenant_id, status="active").count()
    if active >= sub.plan.max_ai_employees:
        return False, f"Your {sub.plan.name} plan allows up to {sub.plan.max_ai_employees} active AI employees."
    return True, ""

def audit_subscription(tenant_id, user_id, action, target_id=None, details=None):
    db.session.add(AuditLog(
        tenant_id=tenant_id, actor_user_id=user_id, action=action,
        target_type="subscription", target_id=str(target_id or ""),
        details_json=details or {},
    ))

def _http_json(url, method="GET", payload=None, headers=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={"Content-Type":"application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Payment provider returned HTTP {exc.code}: {detail[:500]}") from exc

def initialize_paystack(payment, customer_email, callback_url):
    secret = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not secret:
        raise RuntimeError("PAYSTACK_SECRET_KEY is not configured.")
    payload = {
        "email": customer_email,
        "amount": str(int(Decimal(payment.amount) * 100)),
        "currency": payment.currency,
        "reference": payment.provider_reference,
        "callback_url": callback_url,
        "metadata": {"tenant_id": payment.tenant_id, "payment_id": payment.id, "subscription_id": payment.subscription_id},
    }
    result = _http_json(
        "https://api.paystack.co/transaction/initialize",
        "POST", payload, {"Authorization": f"Bearer {secret}"}
    )
    if not result.get("status"):
        raise RuntimeError(result.get("message", "Paystack initialization failed."))
    payment.metadata_json = {**(payment.metadata_json or {}), "authorization_url": result["data"]["authorization_url"]}
    db.session.commit()
    return result["data"]["authorization_url"]

def verify_paystack_signature(raw_body, signature):
    secret = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature)

def stripe_request(path, method="GET", payload=None):
    secret = current_app.config.get("STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured.")
    return _http_json(
        f"https://api.stripe.com/v1/{path}",
        method,
        payload,
        {"Authorization": f"Bearer {secret}", "Content-Type": "application/x-www-form-urlencoded"},
    )

def initialize_stripe(payment, customer_email, success_url, cancel_url):
    secret = current_app.config.get("STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured.")
    # Stripe Checkout API accepts form encoding; use urllib directly here.
    params = [
        ("mode", "payment"),
        ("success_url", success_url),
        ("cancel_url", cancel_url),
        ("customer_email", customer_email),
        ("line_items[0][price_data][currency]", payment.currency.lower()),
        ("line_items[0][price_data][product_data][name]", "AI Workforce subscription"),
        ("line_items[0][price_data][unit_amount]", str(int(Decimal(payment.amount) * 100))),
        ("metadata[payment_id]", str(payment.id)),
        ("metadata[tenant_id]", str(payment.tenant_id)),
        ("metadata[subscription_id]", str(payment.subscription_id)),
    ]
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions", data=data, method="POST",
        headers={"Authorization": f"Bearer {secret}", "Content-Type":"application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode(errors="replace")[:500]) from exc
    payment.metadata_json = {**(payment.metadata_json or {}), "checkout_session_id": result["id"]}
    db.session.commit()
    return result["url"]
