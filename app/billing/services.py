
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


def close_abandoned_payments(older_than_hours=2):
    """Checkouts that were opened but never paid stay 'pending' forever; mark them
    'abandoned' after a while so billing history is clear. A late webhook can still
    activate one (activation only skips payments already marked paid)."""
    from app.models import Payment
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    stale = Payment.query.filter(Payment.status == "pending", Payment.created_at < cutoff).all()
    for p in stale:
        p.status = "abandoned"
    if stale:
        db.session.commit()
    return len(stale)


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

# Failures caused by the AI provider (for example the platform's OpenAI balance
# running out) are the platform's problem, not the client's: they never count
# against an allowance. ai_engine prefixes those task errors with this marker.
AI_SERVICE_UNAVAILABLE = "The AI service is temporarily unavailable"


def _cfg(name, default):
    try:
        value = current_app.config.get(name, default)
        return default if value is None else value
    except RuntimeError:
        return default


def is_trial(sub):
    return bool(sub and sub.status == "trialing")


def employee_limit(sub):
    """Trials get the whole starter workforce; paid plans use their own limit."""
    if is_trial(sub):
        return max(sub.plan.max_ai_employees, int(_cfg("TRIAL_MAX_AI_EMPLOYEES", 10)))
    return sub.plan.max_ai_employees


def _counted_tasks(tenant_id):
    from app.models import WorkforceTask
    return WorkforceTask.query.filter(
        WorkforceTask.tenant_id == tenant_id,
        ~db.and_(WorkforceTask.status == "failed",
                 db.func.coalesce(WorkforceTask.error_message, "").like(AI_SERVICE_UNAVAILABLE + "%")))


def _utc_midnight():
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def task_usage(tenant_id):
    sub = current_subscription(tenant_id)
    if not sub:
        return 0
    from app.models import WorkforceTask
    start = sub.current_period_start
    end = sub.current_period_end
    q = _counted_tasks(tenant_id)
    if start:
        q = q.filter(WorkforceTask.created_at >= start)
    if end:
        q = q.filter(WorkforceTask.created_at < end)
    return q.count()


def tasks_today(tenant_id):
    from app.models import WorkforceTask
    return _counted_tasks(tenant_id).filter(WorkforceTask.created_at >= _utc_midnight()).count()


def trial_tokens_today():
    """AI tokens used today by all workspaces that are on a free trial."""
    from app.models import AgentRun
    total = (db.session.query(db.func.coalesce(db.func.sum(AgentRun.input_tokens + AgentRun.output_tokens), 0))
             .join(TenantSubscription, TenantSubscription.tenant_id == AgentRun.tenant_id)
             .filter(TenantSubscription.status == "trialing", AgentRun.created_at >= _utc_midnight())
             .scalar())
    from app.models import WidgetMessage
    chat = (db.session.query(db.func.coalesce(db.func.sum(WidgetMessage.input_tokens + WidgetMessage.output_tokens), 0))
            .join(TenantSubscription, TenantSubscription.tenant_id == WidgetMessage.tenant_id)
            .filter(TenantSubscription.status == "trialing", WidgetMessage.created_at >= _utc_midnight())
            .scalar())
    return int(total or 0) + int(chat or 0)


def trial_summary(tenant_id):
    """Figures for the trial banner; None when the workspace is not on a trial."""
    sub = current_subscription(tenant_id)
    if not is_trial(sub):
        return None
    ends = as_utc(sub.trial_ends_at) if sub.trial_ends_at else None
    days_left = max(0, (ends - datetime.now(timezone.utc)).days + 1) if ends else None
    return {"daily_limit": int(_cfg("TRIAL_DAILY_TASK_LIMIT", 5)), "used_today": tasks_today(tenant_id),
            "ends_at": ends, "days_left": days_left, "employee_limit": employee_limit(sub)}


def can_create_task(tenant_id):
    sub = current_subscription(tenant_id)
    if not sub or sub.status not in {"trialing", "active"}:
        return False, "Your subscription is not active. Choose a plan to continue."
    used = task_usage(tenant_id)
    if used >= sub.plan.monthly_task_limit:
        return False, f"You have reached the {sub.plan.name} plan task quota ({sub.plan.monthly_task_limit} tasks for this billing period)."
    from app.models import AIEmployee
    active = AIEmployee.query.filter_by(tenant_id=tenant_id, status="active").count()
    if active > employee_limit(sub):
        return False, (f"Your {sub.plan.name} plan allows {sub.plan.max_ai_employees} active AI employees and "
                       f"{active} are active. Pause some on the dashboard, or upgrade, to continue.")
    if is_trial(sub):
        daily = int(_cfg("TRIAL_DAILY_TASK_LIMIT", 5))
        if daily and tasks_today(tenant_id) >= daily:
            return False, (f"Your free trial includes {daily} assignments a day so it lasts the full 14 days. "
                           "Your allowance renews at midnight (GMT), or choose a plan to keep going today.")
        pool = int(_cfg("TRIAL_DAILY_TOKEN_POOL", 0))
        if pool and trial_tokens_today() >= pool:
            return False, ("Free-trial capacity for today is fully booked. It renews at midnight (GMT), "
                           "or choose a plan to keep going today.")
    return True, ""

def visuals_today(tenant_id):
    from app.models import GeneratedAsset
    return GeneratedAsset.query.filter(GeneratedAsset.tenant_id == tenant_id,
                                       GeneratedAsset.created_at >= _utc_midnight(),
                                       GeneratedAsset.status != "failed").count()


def can_create_visual(tenant_id):
    sub = current_subscription(tenant_id)
    if not sub or sub.status not in {"trialing", "active"}:
        return False, "Your subscription is not active. Choose a plan to continue."
    if is_trial(sub):
        limit = int(_cfg("TRIAL_DAILY_VISUAL_LIMIT", 5))
        if limit and visuals_today(tenant_id) >= limit:
            return False, (f"Your free trial includes {limit} charts, presentations or graphics a day. "
                           "This renews at midnight (GMT), or choose a plan to keep going today.")
        pool = int(_cfg("TRIAL_DAILY_TOKEN_POOL", 0))
        if pool and trial_tokens_today() >= pool:
            return False, "Free-trial capacity for today is fully booked. It renews at midnight (GMT)."
    else:
        limit = int(_cfg("VISUALS_DAILY_LIMIT", 40))
        if limit and visuals_today(tenant_id) >= limit:
            return False, f"You have made {limit} charts, presentations or graphics today. This renews at midnight (GMT)."
    return True, ""


def can_activate_employee(tenant_id):
    sub = current_subscription(tenant_id)
    if not sub or sub.status not in {"trialing", "active"}:
        return False, "Your subscription is not active. Choose a plan to continue."
    from app.models import AIEmployee
    active = AIEmployee.query.filter_by(tenant_id=tenant_id, status="active").count()
    limit = employee_limit(sub)
    if active >= limit:
        if is_trial(sub):
            return False, f"Your free trial allows up to {limit} active AI employees."
        return False, f"Your {sub.plan.name} plan allows up to {sub.plan.max_ai_employees} active AI employees."
    return True, ""

def audit_subscription(tenant_id, user_id, action, target_id=None, details=None):
    db.session.add(AuditLog(
        tenant_id=tenant_id, actor_user_id=user_id, action=action,
        target_type="subscription", target_id=str(target_id or ""),
        details_json=details or {},
    ))

def _ua(extra):
    from app.http_client import headers as _h
    return _h(extra)


def _http_json(url, method="GET", payload=None, headers=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=_ua({"Content-Type":"application/json", **(headers or {})}))
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
    if payment.currency == "GHS":
        # Mobile Money (MTN MoMo, Telecel Cash, AT Money) and Visa/Mastercard.
        payload["channels"] = ["mobile_money", "card"]
    result = _http_json(
        "https://api.paystack.co/transaction/initialize",
        "POST", payload, {"Authorization": f"Bearer {secret}"}
    )
    if not result.get("status"):
        raise RuntimeError(result.get("message", "Paystack initialization failed."))
    payment.metadata_json = {**(payment.metadata_json or {}), "authorization_url": result["data"]["authorization_url"]}
    db.session.commit()
    return result["data"]["authorization_url"]

def paystack_amount_matches(payment, data):
    """Paystack reports amounts in the smallest unit (pesewas)."""
    try:
        expected = int(Decimal(payment.amount) * 100)
        return int(data.get("amount", -1)) == expected and str(data.get("currency", "")).upper() == payment.currency.upper()
    except (TypeError, ValueError, ArithmeticError):
        return False


def verify_paystack_transaction(reference):
    """Ask Paystack directly whether a payment succeeded (does not rely on the webhook)."""
    secret = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not secret:
        raise RuntimeError("PAYSTACK_SECRET_KEY is not configured.")
    result = _http_json(f"https://api.paystack.co/transaction/verify/{urllib.parse.quote(reference, safe='')}",
                        "GET", None, {"Authorization": f"Bearer {secret}"})
    return result.get("data") or {}


def configured_payment_providers():
    providers = []
    if current_app.config.get("PAYSTACK_SECRET_KEY"):
        providers.append(("paystack", "Mobile Money or card (Paystack)"))
    if current_app.config.get("STRIPE_SECRET_KEY"):
        providers.append(("stripe", "International card (Stripe)"))
    return providers


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
        headers=_ua({"Authorization": f"Bearer {secret}", "Content-Type":"application/x-www-form-urlencoded"})
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode(errors="replace")[:500]) from exc
    payment.metadata_json = {**(payment.metadata_json or {}), "checkout_session_id": result["id"]}
    db.session.commit()
    return result["url"]
