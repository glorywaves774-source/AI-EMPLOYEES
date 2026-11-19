import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from app.extensions import db, bcrypt
from app.models import PlatformAdmin, SecurityEvent
from app.security_monitor import record_security_event


class Milestone12SecurityTests(unittest.TestCase):
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
            TRUST_PROXY_COUNT = 0
            PLATFORM_ADMIN_MFA_MAX_ATTEMPTS = 2
            PLATFORM_ADMIN_MFA_LOCKOUT_MINUTES = 15
            SECURITY_HEADERS_ENABLED = True

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self.admin = PlatformAdmin(
                email="platform@example.test",
                full_name="Platform Admin",
                password_hash=bcrypt.generate_password_hash("correct-password-123").decode(),
                mfa_enabled=True,
                mfa_secret="JBSWY3DPEHPK3PXP",
            )
            db.session.add(self.admin)
            db.session.commit()
            self.admin_id = self.admin.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        os.unlink(self.tmp.name)

    def test_platform_mfa_route_is_registered(self):
        rules = {rule.rule for rule in self.app.url_map.iter_rules()}
        self.assertIn("/platform/mfa", rules)
        self.assertIn("/platform/login", rules)

    def test_invalid_mfa_attempts_trigger_persisted_lockout(self):
        with self.client.session_transaction() as session:
            session["platform_mfa_pending_admin_id"] = self.admin_id

        first = self.client.post("/platform/mfa", data={"code": "000000"})
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/platform/mfa", data={"code": "000000"})
        self.assertEqual(second.status_code, 302)
        self.assertIn("/platform/login", second.headers["Location"])

        with self.app.app_context():
            admin = db.session.get(PlatformAdmin, self.admin_id)
            self.assertIsNotNone(admin.locked_until)
            self.assertEqual(admin.failed_login_attempts, 0)
            self.assertEqual(
                SecurityEvent.query.filter_by(event_type="platform_admin.mfa_lockout").count(), 1
            )
        with self.client.session_transaction() as session:
            self.assertNotIn("platform_mfa_pending_admin_id", session)
            self.assertNotIn("platform_admin_id", session)

    def test_forwarded_for_is_not_trusted_without_configured_proxy(self):
        with self.app.test_request_context(
            "/platform/login",
            environ_overrides={"REMOTE_ADDR": "198.51.100.10"},
            headers={"X-Forwarded-For": "203.0.113.77"},
        ):
            from flask import g
            g.request_id = "test-request-id"
            event = record_security_event("test.ip_attribution")
            self.assertEqual(event.ip_address, "198.51.100.10")

    def test_platform_login_rejects_external_next_redirect(self):
        with self.app.app_context():
            admin = db.session.get(PlatformAdmin, self.admin_id)
            admin.mfa_enabled = False
            db.session.commit()
        response = self.client.post(
            "/platform/login?next=https://attacker.example/",
            data={"email": "platform@example.test", "password": "correct-password-123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/platform/"))


if __name__ == "__main__":
    unittest.main()
