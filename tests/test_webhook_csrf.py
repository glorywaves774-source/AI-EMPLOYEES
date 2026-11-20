"""Payment webhooks must work with CSRF protection on (as in production):
Paystack/Stripe can't send a CSRF token; their signatures authenticate them."""
import hashlib
import hmac
import json
import os
import tempfile
import unittest

from app import create_app
from app.extensions import db
from app.models import Payment, SubscriptionPlan, TenantSubscription

SECRET = "sk_test_webhook"


class WebhookCsrfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()

        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False; RATELIMIT_ENABLED = False; RATELIMIT_STORAGE_URI = "memory://"
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"; STORAGE_BACKEND = "local"
            PAYSTACK_SECRET_KEY = SECRET; STRIPE_SECRET_KEY = "sk_test_s"; STRIPE_WEBHOOK_SECRET = "whsec_x"
        self.app = create_app(C)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
        self.client.post("/auth/register", data={"full_name": "A", "email": "a@example.com", "business_name": "A Ltd",
                                                 "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.client.get("/billing/")
        self.app.config["WTF_CSRF_ENABLED"] = True  # production setting
        self.ctx = self.app.app_context(); self.ctx.push()
        sub = TenantSubscription.query.first()
        plan = SubscriptionPlan.query.filter_by(code="growth").first()
        self.payment = Payment(tenant_id=sub.tenant_id, subscription_id=sub.id, provider="paystack",
                               provider_reference="AW-test", amount=plan.amount, currency="GHS", status="pending",
                               invoice_number="INV-T", metadata_json={"plan_id": plan.id})
        db.session.add(self.payment); db.session.commit()
        self.webhook_client = self.app.test_client()  # no session, no CSRF token, like Paystack's servers

    def tearDown(self):
        db.session.remove(); self.ctx.pop()
        with self.app.app_context():
            db.drop_all()
        os.unlink(self.tmp.name)

    def _send(self, body, signature):
        return self.webhook_client.post("/billing/webhooks/paystack", data=body, content_type="application/json",
                                        headers={"X-Paystack-Signature": signature})

    def test_signed_paystack_webhook_activates_with_csrf_on(self):
        amount = int(self.payment.amount * 100)
        body = json.dumps({"event": "charge.success", "data": {"id": 1, "reference": "AW-test", "amount": amount,
                                                                "currency": "GHS"}}).encode()
        sig = hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()
        r = self._send(body, sig)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:200])
        self.assertEqual(db.session.get(Payment, self.payment.id).status, "paid")
        self.assertEqual(TenantSubscription.query.first().status, "active")

    def test_unsigned_or_forged_webhook_still_rejected(self):
        body = json.dumps({"event": "charge.success", "data": {"reference": "AW-test", "amount": 1, "currency": "GHS"}}).encode()
        self.assertEqual(self._send(body, "forged").status_code, 401)
        self.assertEqual(db.session.get(Payment, self.payment.id).status, "pending")

    def test_ordinary_forms_still_need_csrf(self):
        self.assertEqual(self.webhook_client.post("/auth/login", data={"email": "a@example.com", "password": "x"}).status_code, 400)

    def test_stripe_webhook_not_blocked_by_csrf(self):
        r = self.webhook_client.post("/billing/webhooks/stripe", data=b"{}", content_type="application/json",
                                     headers={"Stripe-Signature": "t=1,v1=bad"})
        self.assertNotEqual(r.status_code, 400, "must reach signature check, not fail CSRF")


if __name__ == "__main__":
    unittest.main()
