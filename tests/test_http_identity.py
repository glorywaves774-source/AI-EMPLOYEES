"""Outgoing requests must not use Python's default 'Python-urllib' signature,
which Paystack's firewall rejects with HTTP 403 / error 1010."""
import io
import json
import unittest
from unittest import mock

from app import create_app
from app.http_client import USER_AGENT


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class HttpIdentityTests(unittest.TestCase):
    def setUp(self):
        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"; SQLALCHEMY_DATABASE_URI = "sqlite://"
            WTF_CSRF_ENABLED = False; RATELIMIT_ENABLED = False; RATELIMIT_STORAGE_URI = "memory://"
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"; STORAGE_BACKEND = "local"
            PAYSTACK_SECRET_KEY = "sk_test_x"; STRIPE_SECRET_KEY = "sk_test_y"
        self.app = create_app(C)

    def _capture(self, fn):
        seen = []
        def fake_urlopen(req, timeout=None):
            seen.append(req)
            return _Resp(json.dumps({"status": True, "data": {}, "id": "cs_1", "url": "https://x"}).encode())
        with self.app.app_context(), mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fn()
        return seen

    def test_paystack_requests_name_the_app(self):
        from app.billing.services import _http_json
        req = self._capture(lambda: _http_json("https://api.paystack.co/transaction/verify/x", "GET", None, {"Authorization": "Bearer k"}))[0]
        self.assertEqual(req.get_header("User-agent"), USER_AGENT)
        self.assertEqual(req.get_header("Authorization"), "Bearer k")
        self.assertNotIn("Python-urllib", USER_AGENT)

    def test_stripe_requests_name_the_app(self):
        from app.billing import services
        payment = mock.Mock(amount="450", currency="GHS", id=1, tenant_id=1, subscription_id=1, metadata_json={})
        with mock.patch.object(services.db.session, "commit"):
            req = self._capture(lambda: services.initialize_stripe(payment, "a@b.c", "https://ok", "https://cancel"))[0]
        self.assertEqual(req.get_header("User-agent"), USER_AGENT)


if __name__ == "__main__":
    unittest.main()
