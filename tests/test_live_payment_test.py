"""Platform-admin GHS 1 live payment test: proves live Paystack payments and webhooks
reach the app, without changing any business's plan or showing in its billing."""
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from unittest import mock

from app import create_app
from app.extensions import bcrypt, db
from app.models import Payment, PlatformAdmin, Tenant, TenantSubscription

SECRET = "sk_live_unit_test"


class LivePaymentTestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()

        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False; RATELIMIT_ENABLED = False; RATELIMIT_STORAGE_URI = "memory://"
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"; STORAGE_BACKEND = "local"
            PAYSTACK_SECRET_KEY = SECRET
        self.app = create_app(C)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
        self.client.post("/auth/register", data={"full_name": "A", "email": "a@example.com", "business_name": "A Ltd",
                                                 "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.client.get("/billing/")
        self.ctx = self.app.app_context(); self.ctx.push()
        db.session.add(PlatformAdmin(email="admin@example.com", full_name="Admin", is_active=True,
                                     password_hash=bcrypt.generate_password_hash("admin-password-123456").decode()))
        db.session.commit()
        self.tenant = Tenant.query.first()
        self.sub = TenantSubscription.query.first()
        self.plan_before, self.status_before = self.sub.plan_id, self.sub.status
        self.admin = self.app.test_client()
        with self.admin.session_transaction() as s:
            s["platform_admin_id"] = PlatformAdmin.query.first().id

    def tearDown(self):
        db.session.remove(); self.ctx.pop()
        with self.app.app_context():
            db.drop_all()
        os.unlink(self.tmp.name)

    def _start(self):
        with mock.patch("app.billing.services._http_json",
                        return_value={"status": True, "data": {"authorization_url": "https://checkout.paystack.com/x"}}) as init:
            r = self.admin.post("/platform/payments/live-test", data={"tenant_id": self.tenant.id})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "https://checkout.paystack.com/x")
        payload = init.call_args[0][2]
        self.assertEqual(payload["amount"], "100")  # GHS 1.00 in pesewas
        self.assertEqual(payload["email"], "admin@example.com")
        return Payment.query.filter(Payment.provider_reference.like("AWT-%")).one()

    def test_dashboard_offers_test_and_allows_paystack_redirect(self):
        r = self.admin.get("/platform/")
        html = r.get_data(as_text=True)
        self.assertIn("Live payment test", html)
        self.assertIn("Pay GHS 1.00 test", html)
        self.assertIn("checkout.paystack.com", r.headers["Content-Security-Policy"])
        self.assertNotIn("Security monitoring", html.split("</title>")[0])

    def test_workspace_users_cannot_start_it(self):
        self.client.post("/auth/login", data={"email": "a@example.com", "password": "a-very-strong-password-123"})
        r = self.client.post("/platform/payments/live-test", data={"tenant_id": self.tenant.id})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/platform/login", r.headers["Location"])
        self.assertEqual(Payment.query.count(), 0)

    def test_webhook_confirms_without_touching_plan_or_client_billing(self):
        payment = self._start()
        body = json.dumps({"event": "charge.success", "data": {"id": 9, "reference": payment.provider_reference,
                                                                "amount": 100, "currency": "GHS"}}).encode()
        sig = hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()
        r = self.app.test_client().post("/billing/webhooks/paystack", data=body, content_type="application/json",
                                        headers={"X-Paystack-Signature": sig})
        self.assertEqual(r.status_code, 200)
        db.session.expire_all()
        p = db.session.get(Payment, payment.id)
        self.assertEqual(p.status, "paid")
        self.assertEqual(p.metadata_json["last_provider_event"], "charge.success")
        sub = db.session.get(TenantSubscription, self.sub.id)
        self.assertEqual((sub.plan_id, sub.status), (self.plan_before, self.status_before))
        # Admin returns from Paystack: told the webhook did it, on the live key.
        page = self.admin.get(f"/platform/payments/live-test/callback?reference={p.provider_reference}", follow_redirects=True)
        self.assertIn("Live payment test passed (live key)", page.get_data(as_text=True))
        # The business never sees it.
        self.client.post("/auth/login", data={"email": "a@example.com", "password": "a-very-strong-password-123"})
        self.assertNotIn("AWT-", self.client.get("/billing/").get_data(as_text=True))

    def test_callback_verifies_when_webhook_is_late(self):
        payment = self._start()
        with mock.patch("app.billing.services._http_json",
                        return_value={"status": True, "data": {"status": "success", "reference": payment.provider_reference,
                                                                 "amount": 100, "currency": "GHS"}}):
            page = self.admin.get(f"/platform/payments/live-test/callback?reference={payment.provider_reference}",
                                  follow_redirects=True)
        self.assertIn("webhook hadn&#39;t arrived yet", page.get_data(as_text=True))
        db.session.expire_all()
        self.assertEqual(db.session.get(Payment, payment.id).status, "paid")
        self.assertEqual(db.session.get(TenantSubscription, self.sub.id).plan_id, self.plan_before)


if __name__ == "__main__":
    unittest.main()
