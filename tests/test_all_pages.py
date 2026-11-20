"""Open every parameterless GET page as a signed-in workspace owner.

Guards against pages that crash at runtime (missing templates, bad
url_for targets, template errors) that unit tests of individual
routes do not cover.
"""
import os
import tempfile
import unittest

from app import create_app
from app.extensions import db

SKIP = {"/logout", "/auth/logout", "/platform/logout"}


class AllPagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()

        class TestConfig:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name.replace("\\", "/")
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False
            RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"
            CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"
            PUBLIC_BASE_URL = "http://localhost"
            STORAGE_BACKEND = "local"

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
        r = self.client.post("/auth/register", data={
            "full_name": "Owner Person", "email": "owner@example.com",
            "business_name": "Example Ltd", "password": "a-very-strong-password-123", "accept_terms": "yes",
        })
        self.assertIn(r.status_code, (302, 303))

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        os.unlink(self.tmp.name)

    def test_every_page_renders_without_server_error(self):
        failures = []
        for rule in self.app.url_map.iter_rules():
            if "GET" not in rule.methods or rule.arguments or rule.rule.startswith("/static"):
                continue
            if rule.rule in SKIP or "logout" in rule.endpoint:
                continue
            resp = self.client.get(rule.rule)
            if resp.status_code >= 500:
                failures.append(f"{rule.rule} -> {resp.status_code}")
        self.assertEqual(failures, [], "Pages returning server errors:\n" + "\n".join(failures))

    def test_integrations_page_lists_providers(self):
        resp = self.client.get("/knowledge/integrations")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Google Drive", resp.data)
        self.assertIn(b"Business Email", resp.data)
        self.assertIn(b"Request setup", resp.data)


if __name__ == "__main__":
    unittest.main()
