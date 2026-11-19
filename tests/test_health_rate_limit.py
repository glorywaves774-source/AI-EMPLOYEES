import os
import tempfile
import unittest

from app import create_app
from app.extensions import db


class HealthRateLimitTests(unittest.TestCase):
    """Render polls the health endpoints every few seconds from one IP."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()

        class TestConfig:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name.replace("\\", "/")
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False
            CELERY_BROKER_URL = "memory://"
            CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        os.unlink(self.tmp.name)

    def test_health_endpoints_are_not_rate_limited(self):
        # More than the 300/hour default limit.
        for _ in range(320):
            self.assertEqual(self.client.get("/readyz").status_code, 200)
            self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_other_routes_are_still_rate_limited(self):
        statuses = {self.client.get("/auth/login").status_code for _ in range(305)}
        self.assertIn(429, statuses)


if __name__ == "__main__":
    unittest.main()
