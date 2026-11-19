import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from app import create_app
from app.extensions import db, bcrypt
from app.models import User, Tenant, TenantMembership, SecurityToken
from app.security_service import hash_token

class SecurityMilestoneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        class TestConfig:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name.replace("\\", "/")
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SESSION_COOKIE_HTTPONLY = True
            SESSION_COOKIE_SECURE = False
            SESSION_COOKIE_SAMESITE = "Lax"
            WTF_CSRF_ENABLED = False
            CELERY_BROKER_URL = "memory://"
            CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"
            LOGIN_MAX_ATTEMPTS = 3
            LOGIN_LOCKOUT_MINUTES = 15
            PASSWORD_RESET_MINUTES = 30
            EMAIL_VERIFICATION_HOURS = 24
            PUBLIC_BASE_URL = "http://localhost"
            SECURITY_HEADERS_ENABLED = True
            SMTP_HOST = None
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self.user = User(email="security@example.test", full_name="Security User",
                             password_hash=bcrypt.generate_password_hash("correct-password-123").decode())
            self.tenant = Tenant(name="Security Test", slug="security-test")
            db.session.add_all([self.user, self.tenant])
            db.session.flush()
            db.session.add(TenantMembership(user_id=self.user.id, tenant_id=self.tenant.id, role="owner"))
            db.session.commit()
            self.user_id = self.user.id
            self.user_email = self.user.email

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        os.unlink(self.tmp.name)

    def test_security_headers_and_health_endpoints(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertTrue(response.headers.get("X-Request-ID"))
        ready = self.client.get("/readyz")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json["database"], "ok")

    def test_login_lockout_after_configured_failures(self):
        for _ in range(3):
            response = self.client.post("/auth/login", data={"email": self.user_email, "password": "wrong-password"})
            self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            user = db.session.get(User, self.user_id)
            self.assertIsNotNone(user.locked_until)
        response = self.client.post("/auth/login", data={"email": self.user_email, "password": "correct-password-123"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"temporarily locked", response.data)

    def test_password_reset_token_is_hashed_and_single_use(self):
        with self.app.app_context():
            raw = "one-time-reset-token"
            db.session.add(SecurityToken(user_id=self.user_id, token_hash=hash_token(raw),
                                          token_type="password_reset",
                                          expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)))
            db.session.commit()
        response = self.client.get("/auth/reset-password/one-time-reset-token")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/auth/reset-password/one-time-reset-token",
                                    data={"password": "new-correct-password-123"}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/auth/reset-password/one-time-reset-token")
        self.assertEqual(response.status_code, 302)

if __name__ == "__main__":
    unittest.main()
