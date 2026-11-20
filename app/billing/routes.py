
from datetime import datetime, timedelta, timezone
import json
import uuid
from decimal import Decimal
from flask import flash, g, make_response, redirect, render_template, request, url_for, current_app, abort
from flask_login import current_user, login_required
from app.extensions import csrf, db
from app.billing.services import configured_payment_providers
from app.models import SubscriptionPlan, TenantSubscription, SubscriptionChangeRequest, Payment, Invoice, AuditLog
from app.security import roles_required

CHECKOUT_CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; "
                "frame-ancestors 'none'; base-uri 'self'; "
                "form-action 'self' https://checkout.paystack.com https://checkout.stripe.com")
from . import billing_bp
from .services import (
    ensure_default_plans, current_subscription, task_usage,
    initialize_paystack, initialize_stripe, verify_paystack_signature,
    audit_subscription, record_webhook_event, mark_payment_refunded
)

def _invoice_number():
    return f"AW-{datetime.now(timezone.utc):%Y%m%d}-{datetime.now(timezone.utc).strftime('%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

def _activate_payment(payment, provider_event=None, period_end=None):
    if payment.status == "paid":
        return
    if (payment.metadata_json or {}).get("kind") == "video_pack":
        from app.video.service import add_pack
        now = datetime.now(timezone.utc)
        payment.status, payment.paid_at = "paid", now
        payment.metadata_json = {**(payment.metadata_json or {}), "last_provider_event": provider_event or ""}
        add_pack(payment)
        if not Invoice.query.filter_by(invoice_number=payment.invoice_number).first():
            db.session.add(Invoice(tenant_id=payment.tenant_id, subscription_id=payment.subscription_id,
                                   invoice_number=payment.invoice_number, amount=payment.amount, currency=payment.currency,
                                   status="paid", period_start=now, period_end=now, paid_at=now))
        db.session.add(AuditLog(tenant_id=payment.tenant_id, actor_user_id=None, action="video.pack_paid",
                                target_type="payment", target_id=str(payment.id), details_json={"provider": payment.provider}))
        return
    sub = TenantSubscription.query.get(payment.subscription_id) if payment.subscription_id else None
    if not sub:
        return
    plan_code = (payment.metadata_json or {}).get("plan_code")
    if plan_code:
        target_plan = SubscriptionPlan.query.filter_by(code=plan_code, is_active=True).first()
        if target_plan:
            sub.plan_id = target_plan.id
    now = datetime.now(timezone.utc)
    payment.status = "paid"
    payment.paid_at = now
    payment.metadata_json = {**(payment.metadata_json or {}), "last_provider_event": provider_event or ""}
    sub.status = "active"
    sub.provider = payment.provider
    sub.current_period_start = now
    sub.current_period_end = period_end or (now + timedelta(days=30))
    sub.cancel_at_period_end = False
    sub.canceled_at = None
    invoice = Invoice.query.filter_by(invoice_number=payment.invoice_number).first() if payment.invoice_number else None
    if not invoice:
        invoice = Invoice(
            tenant_id=payment.tenant_id, subscription_id=sub.id,
            invoice_number=payment.invoice_number or f"AW-{uuid.uuid4().hex[:12].upper()}",
            amount=payment.amount, currency=payment.currency,
            status="paid", period_start=sub.current_period_start,
            period_end=sub.current_period_end, paid_at=now
        )
        db.session.add(invoice)
    else:
        invoice.status = "paid"; invoice.paid_at = now
    change_id = (payment.metadata_json or {}).get("change_request_id")
    if change_id:
        change = SubscriptionChangeRequest.query.get(change_id)
        if change:
            change.status = "approved"
            change.decided_at = now
    db.session.add(AuditLog(
        tenant_id=payment.tenant_id, actor_user_id=None,
        action="subscription.payment_confirmed", target_type="payment",
        target_id=str(payment.id), details_json={"provider": payment.provider}
    ))

@billing_bp.get("/")
@login_required
def index():
    ensure_default_plans()
    sub = current_subscription(g.active_tenant_id)
    if not sub:
        from .services import ensure_tenant_subscription
        sub = ensure_tenant_subscription(g.active_tenant_id)
        db.session.commit()
    payments = Payment.query.filter_by(tenant_id=g.active_tenant_id).order_by(Payment.created_at.desc()).limit(20).all()
    invoices = Invoice.query.filter_by(tenant_id=g.active_tenant_id).order_by(Invoice.issued_at.desc()).limit(20).all()
    usage = task_usage(g.active_tenant_id)
    plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.amount.asc()).all()
    response = make_response(render_template("billing/index.html", subscription=sub, plans=plans, payments=payments, invoices=invoices, usage=usage, providers=configured_payment_providers()))
    # "Choose plan" posts here, then redirects to the provider's checkout. Browsers apply
    # form-action to that redirect, so the checkout origins are allowed on this page only.
    response.headers["Content-Security-Policy"] = CHECKOUT_CSP
    return response

@billing_bp.post("/subscribe/<int:plan_id>")
@roles_required("owner", "admin")
def subscribe(plan_id):
    ensure_default_plans()
    plan = SubscriptionPlan.query.filter_by(id=plan_id, is_active=True).first_or_404()
    sub = current_subscription(g.active_tenant_id)
    if not sub:
        flash("Subscription record is unavailable. Please contact platform administration.", "error")
        return redirect(url_for("billing.index"))
    if plan.amount <= 0:
        flash("This plan is not yet commercially configured. Platform administration must set its approved price first.", "error")
        return redirect(url_for("billing.index"))
    if sub.plan_id == plan.id and sub.status == "active":
        flash("That plan is already active.", "info")
        return redirect(url_for("billing.index"))

    change = SubscriptionChangeRequest(
        tenant_id=g.active_tenant_id, requested_by_user_id=current_user.id,
        current_plan_id=sub.plan_id, requested_plan_id=plan.id, status="pending",
        notes="Plan selected from billing centre."
    )
    db.session.add(change)
    db.session.flush()
    amount = Decimal(plan.amount)
    payment = Payment(
        tenant_id=g.active_tenant_id, subscription_id=sub.id,
        provider=request.form.get("provider", "paystack"),
        provider_reference=f"AW-{uuid.uuid4().hex}",
        amount=amount, currency=plan.currency, status="pending",
        invoice_number=f"INV-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        metadata_json={"change_request_id": change.id, "plan_code": plan.code},
    )
    from .services import configured_payment_providers
    if payment.provider not in {code for code, _ in configured_payment_providers()}:
        abort(400)
    db.session.add(payment)
    db.session.flush()
    audit_subscription(g.active_tenant_id, current_user.id, "subscription.plan_change_requested",
                       change.id, {"requested_plan": plan.code, "provider": payment.provider})
    db.session.commit()

    try:
        if payment.provider == "paystack":
            url = initialize_paystack(payment, current_user.email, url_for("billing.paystack_callback", _external=True))
        else:
            url = initialize_stripe(
                payment, current_user.email,
                url_for("billing.stripe_success", _external=True),
                url_for("billing.index", _external=True),
            )
    except Exception as exc:
        payment.status = "failed"
        payment.metadata_json = {"error": str(exc)[:500]}
        db.session.commit()
        flash(f"Payment could not be initialized: {str(exc)[:240]}", "error")
        return redirect(url_for("billing.index"))
    return redirect(url)


@billing_bp.post("/video-pack")
@roles_required("owner", "admin")
def buy_video_pack():
    from .services import configured_payment_providers
    sub = current_subscription(g.active_tenant_id)
    if not sub or sub.status != "active" or (sub.plan and sub.plan.code not in {"growth", "business"}):
        flash("Extra AI video clips are available on the Growth and Business plans.", "error")
        return redirect(url_for("billing.index"))
    if "paystack" not in {code for code, _ in configured_payment_providers()}:
        flash("Online payment is being set up. Contact Kayron to buy extra clips.", "error")
        return redirect(url_for("billing.index"))
    clips = int(current_app.config.get("VIDEO_PACK_CLIPS") or 10)
    payment = Payment(tenant_id=g.active_tenant_id, subscription_id=sub.id, provider="paystack",
                      provider_reference=f"AWV-{uuid.uuid4().hex}", amount=Decimal(str(current_app.config.get("VIDEO_PACK_PRICE") or "300")),
                      currency=sub.plan.currency if sub.plan else "GHS", status="pending",
                      invoice_number=f"INV-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
                      metadata_json={"kind": "video_pack", "clips": clips})
    db.session.add(payment)
    db.session.commit()
    try:
        url = initialize_paystack(payment, current_user.email, url_for("billing.paystack_callback", _external=True))
    except Exception as exc:
        payment.status = "failed"; payment.metadata_json = {**payment.metadata_json, "error": str(exc)[:500]}
        db.session.commit()
        flash(f"Payment could not be started: {str(exc)[:200]}", "error")
        return redirect(url_for("billing.index"))
    return redirect(url)


@billing_bp.post("/cancel")
@roles_required("owner", "admin")
def cancel():
    sub = current_subscription(g.active_tenant_id)
    if not sub or sub.status not in {"trialing", "active"}:
        flash("There is no active subscription to cancel.", "error")
        return redirect(url_for("billing.index"))
    sub.cancel_at_period_end = True
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
                            action="subscription.cancellation_scheduled", target_type="subscription",
                            target_id=str(sub.id)))
    db.session.commit()
    flash("Cancellation scheduled for the end of the current trial/billing period.", "success")
    return redirect(url_for("billing.index"))

@billing_bp.post("/resume")
@roles_required("owner", "admin")
def resume():
    sub = current_subscription(g.active_tenant_id)
    if not sub:
        flash("Subscription not found.", "error")
        return redirect(url_for("billing.index"))
    sub.cancel_at_period_end = False
    sub.canceled_at = None
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
                            action="subscription.cancellation_revoked", target_type="subscription",
                            target_id=str(sub.id)))
    db.session.commit()
    flash("Subscription cancellation has been revoked.", "success")
    return redirect(url_for("billing.index"))

@billing_bp.get("/paystack/callback")
@login_required
def paystack_callback():
    from .services import paystack_amount_matches, verify_paystack_transaction
    reference = request.args.get("reference", "")
    payment = Payment.query.filter_by(tenant_id=g.active_tenant_id, provider="paystack", provider_reference=reference).first()
    if not payment:
        flash("Payment reference not found.", "error")
        return redirect(url_for("billing.index"))
    if payment.status == "paid":
        flash("Payment confirmed. Your plan is active.", "success")
        return redirect(url_for("billing.index"))
    try:
        data = verify_paystack_transaction(reference)
    except Exception:
        current_app.logger.exception("Paystack verification failed")
        flash("We couldn't confirm the payment with Paystack yet. If money left your account, your plan will switch on automatically within a few minutes.", "info")
        return redirect(url_for("billing.index"))
    if data.get("status") == "success" and data.get("reference") == reference and paystack_amount_matches(payment, data):
        _activate_payment(payment, "paystack.verify")
        db.session.commit()
        if (payment.metadata_json or {}).get("kind") == "video_pack":
            flash(f"Payment confirmed. {payment.metadata_json.get('clips', 10)} extra AI video clips have been added. Thank you!", "success")
        else:
            flash("Payment confirmed. Your plan is now active. Thank you!", "success")
    elif data.get("status") in {"failed", "abandoned", "reversed"}:
        payment.status = "failed"; db.session.commit()
        flash("The payment did not go through. No money was taken; please try again.", "error")
    else:
        flash("Payment is still being processed. Your plan will switch on automatically once Paystack confirms it.", "info")
    return redirect(url_for("billing.index"))

@billing_bp.post("/webhooks/paystack")
@csrf.exempt  # server-to-server: authenticated by Paystack's HMAC signature instead of a CSRF token
def paystack_webhook():
    raw = request.get_data()
    if not verify_paystack_signature(raw, request.headers.get("X-Paystack-Signature")):
        abort(401)
    event = request.get_json(silent=True) or {}
    event_type = event.get("event", "")
    data = event.get("data", {}) or {}
    event_id = data.get("id") or data.get("reference") or event.get("id")
    webhook, already = record_webhook_event("paystack", event_id, event_type, raw)
    if already:
        return "", 200
    try:
        reference = data.get("reference")
        payment = Payment.query.filter_by(provider="paystack", provider_reference=reference).first()
        if payment and event_type == "charge.success":
            from .services import paystack_amount_matches
            if paystack_amount_matches(payment, data):
                _activate_payment(payment, event_type)
            else:
                current_app.logger.error("Paystack amount/currency mismatch for %s", reference)
                payment.metadata_json = {**(payment.metadata_json or {}), "mismatch": True}
        elif payment and event_type in {"refund.processed", "charge.refund"}:
            mark_payment_refunded(payment, data.get("amount", 0) / 100, event_type)
        webhook.status = "processed"
        webhook.processed_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        webhook = record_webhook_event("paystack", event_id, event_type, raw)[0]
        webhook.status = "failed"
        webhook.error_message = str(exc)[:500]
        db.session.commit()
        raise
    return "", 200

@billing_bp.get("/stripe/success")
@login_required
def stripe_success():
    flash("Stripe checkout completed. Your subscription will activate after Stripe confirms the payment.", "info")
    return redirect(url_for("billing.index"))

@billing_bp.post("/webhooks/stripe")
@csrf.exempt  # server-to-server: authenticated by Stripe's signature instead of a CSRF token
def stripe_webhook():
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    signature = request.headers.get("Stripe-Signature", "")
    if not secret or not signature:
        abort(401)
    import hmac, hashlib, time
    timestamp = None; signatures = []
    for item in signature.split(","):
        k, _, v = item.partition("=")
        if k == "t": timestamp = v
        elif k == "v1": signatures.append(v)
    if not timestamp or not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
        abort(401)
    raw = request.get_data()
    signed = f"{timestamp}.{raw.decode('utf-8')}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        abort(401)
    event = request.get_json(silent=True) or {}
    event_type = event.get("type", "")
    event_id = event.get("id")
    webhook, already = record_webhook_event("stripe", event_id, event_type, raw)
    if already:
        return "", 200
    obj = event.get("data", {}).get("object", {}) or {}
    metadata = obj.get("metadata", {}) or {}
    payment_id = metadata.get("payment_id")
    payment = Payment.query.get(int(payment_id)) if str(payment_id).isdigit() else None
    try:
        if event_type in {"checkout.session.completed", "invoice.payment_succeeded"} and payment:
            period_end = None
            if obj.get("lines", {}).get("data"):
                period = obj["lines"]["data"][0].get("period", {})
                if period.get("end"):
                    period_end = datetime.fromtimestamp(period["end"], timezone.utc)
            _activate_payment(payment, event_type, period_end)
        elif event_type in {"invoice.payment_failed", "invoice.payment_action_required"} and payment:
            payment.status = "failed"
            sub = TenantSubscription.query.get(payment.subscription_id)
            if sub: sub.status = "past_due"
        elif event_type in {"charge.refunded", "refund.updated"} and payment:
            amount = obj.get("amount_refunded") or obj.get("amount") or 0
            mark_payment_refunded(payment, Decimal(str(amount)) / Decimal("100"), event_type)
        webhook.status = "processed"
        webhook.processed_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        webhook = record_webhook_event("stripe", event_id, event_type, raw)[0]
        webhook.status = "failed"
        webhook.error_message = str(exc)[:500]
        db.session.commit()
        raise
    return "", 200

