import os
import tempfile
import unittest
from app import create_app
from app.extensions import db

class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        class TestConfig:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name.replace("\\\\", "/")
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SESSION_COOKIE_HTTPONLY = True
            SESSION_COOKIE_SECURE = False
            SESSION_COOKIE_SAMESITE = "Lax"
            WTF_CSRF_ENABLED = False
            CELERY_BROKER_URL = "memory://"
            CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"
            PUBLIC_BASE_URL = "http://localhost"
            SMTP_HOST = None
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.drop_all()
        os.unlink(self.tmp.name)

    def test_registration_creates_workspace(self):
        response = self.client.post("/auth/register", data={
            "full_name": "Test Owner",
            "email": "owner@example.test",
            "business_name": "Example Business",
            "password": "a-very-long-test-password", "accept_terms": "yes"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Example Business", response.data)

if __name__ == "__main__":
    unittest.main()
