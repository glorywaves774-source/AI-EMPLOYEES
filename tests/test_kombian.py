"""Kombian help assistant: access control, privacy, role-aware links, fallback, rate limit."""
import os
import tempfile
import unittest
from unittest import mock

from app import create_app
from app.extensions import db, bcrypt
from app.help import assistant
from app.help.assistant import redact, render_links


def make_app(tmp, **extra):
    class TestConfig:
        SECRET_KEY = "test-secret-key-that-is-long-enough"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + tmp.replace("\\", "/")
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        CELERY_BROKER_URL = "memory://"
        CELERY_RESULT_BACKEND = "cache+memory://"
        RATELIMIT_STORAGE_URI = "memory://"
        PUBLIC_BASE_URL = "http://localhost"
        STORAGE_BACKEND = "local"
        OPENAI_API_KEY = None
    for k, v in extra.items():
        setattr(TestConfig, k, v)
    return create_app(TestConfig)


class KombianTests(unittest.TestCase):
    def setUp(self, **extra):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False); f.close()
        self.db_path = f.name
        self.app = make_app(self.db_path, **extra)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove(); db.drop_all()
        os.unlink(self.db_path)

    def register(self, email="owner@example.com", business="Secretive Holdings Ltd"):
        r = self.client.post("/auth/register", data={"full_name": "Owner Person", "email": email,
                                                     "business_name": business, "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.assertIn(r.status_code, (302, 303))

    def ask(self, q, **kw):
        return self.client.post("/help/ask", json={"question": q, **kw})

    # --- access ---------------------------------------------------------
    def test_requires_sign_in(self):
        self.assertEqual(self.ask("How do I upload documents?").status_code, 401)

    def test_widget_only_for_signed_in_people(self):
        self.assertNotIn("kombian-fab", self.client.get("/auth/login").get_data(as_text=True))
        self.register()
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("kombian-fab", html)
        self.assertIn('name="csrf-token"', html)
        self.assertIn("js/kombian.js", html)

    # --- answering without the AI service (falls back to the guide) ------
    def test_falls_back_to_the_guide(self):
        self.register()
        r = self.ask("How do I upload a document?")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["source"], "guide")
        self.assertIn("PDF", data["answer"])
        self.assertIn("knowledge", data["links"])
        self.assertEqual(data["links"]["knowledge"]["url"], "/knowledge/")

    def test_validates_question(self):
        self.register()
        self.assertEqual(self.ask("   ").status_code, 400)
        self.assertEqual(self.ask("x" * 1001).status_code, 400)

    # --- privacy -----------------------------------------------------------
    def test_redacts_personal_details(self):
        text = redact("Email ama.mensah@example.com, call +233 24 123 4567 or 0241234567, "
                      "card GHA-123456789-0, key sk-proj-abcdefghijklmnop1234, AKIAR2CIJW5X5T6HLV34, acct 12345678")
        for secret in ("ama.mensah@example.com", "123 4567", "0241234567", "GHA-123456789", "sk-proj-abc", "AKIAR2", "12345678"):
            self.assertNotIn(secret, text)
        self.assertIn("[email removed]", text)
        self.assertIn("[phone removed]", text)

    def test_ai_gets_question_and_guide_but_no_records(self):
        self.app.config["OPENAI_API_KEY"] = "test-key"
        self.register(business="Secretive Holdings Ltd")
        seen = {}

        def fake_ai(instructions, input_text):
            seen["instructions"], seen["input"] = instructions, input_text
            return "Go to [[page:knowledge]] and tap **Upload and index**. Figures are on [[page:analytics]]."
        with mock.patch.object(assistant, "_call_ai", side_effect=fake_ai):
            r = self.ask("My number is 0241234567 — how do I upload?",
                         history=[{"role": "user", "content": "I'm owner@example.com"}])
        data = r.get_json()
        self.assertEqual(data["source"], "ai")
        self.assertNotIn("0241234567", seen["input"])
        self.assertNotIn("owner@example.com", seen["input"])
        self.assertNotIn("Secretive Holdings", seen["instructions"] + seen["input"])  # no workspace records
        self.assertIn("HELP GUIDE", seen["instructions"])
        self.assertIn("Owner", seen["instructions"])
        self.assertEqual(set(data["links"]), {"knowledge", "analytics"})
        self.assertIn("[[link:knowledge]]", data["answer"])

    # --- role-aware links ---------------------------------------------------
    def test_links_are_filtered_by_role(self):
        with self.app.test_request_context():
            text, links = render_links("See [[page:analytics]] and [[page:export]] and [[page:home]] [[page:bogus]]", "employee")
        self.assertEqual(set(links), {"home"})
        self.assertNotIn("[[page:", text)
        self.assertIn("Analytics (open to", text)
        self.assertIn("Data export (open to Owner", text)
        with self.app.test_request_context():
            _, links = render_links("[[page:analytics]] [[page:export]]", "owner")
        self.assertEqual(set(links), {"analytics", "export"})

    def test_employee_role_nav_hides_pages_they_cannot_open(self):
        self.register()
        with self.app.app_context():
            from app.models import Tenant, TenantMembership, User
            t = Tenant.query.first()
            u = User(email="staff@example.com", full_name="Staff", password_hash=bcrypt.generate_password_hash("a-very-strong-password-123").decode())
            db.session.add(u); db.session.flush()
            db.session.add(TenantMembership(user_id=u.id, tenant_id=t.id, role="employee", status="active"))
            db.session.commit()
        self.client.post("/auth/logout")
        self.client.post("/auth/login", data={"email": "staff@example.com", "password": "a-very-strong-password-123", "accept_terms": "yes"})
        html = self.client.get("/dashboard").get_data(as_text=True)
        tabbar = html.split('class="tabbar"')[1].split("</nav>")[0]
        self.assertNotIn("/analytics/", tabbar)
        self.assertNotIn('href="/analytics/"', html)
        self.assertIn('href="/billing/"', html)

    # --- platform owner gets the admin guide -------------------------------
    def test_platform_admin_context(self):
        with self.app.app_context():
            from app.models import PlatformAdmin
            db.session.add(PlatformAdmin(email="admin@example.com", full_name="Admin", is_active=True,
                                         password_hash=bcrypt.generate_password_hash("admin-password-123456").decode()))
            db.session.commit()
            admin_id = PlatformAdmin.query.first().id
        self.assertEqual(self.ask("price", context="platform").status_code, 401)
        with self.client.session_transaction() as s:
            s["platform_admin_id"] = admin_id
        r = self.ask("How do I change a plan's price?", context="platform")
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertIn("Update", data["answer"])
        self.assertEqual(set(data["links"]), {"admin"} & set(data["links"]))
        html = self.client.get("/platform/").get_data(as_text=True)
        self.assertIn('data-context="platform"', html)


class KombianCsrfAndRateLimitTests(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False); f.close()
        self.db_path = f.name
        self.app = make_app(self.db_path, RATELIMIT_ENABLED=True)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client.post("/auth/register", data={"full_name": "O", "email": "o@example.com",
                                                 "business_name": "B", "password": "a-very-strong-password-123", "accept_terms": "yes"})

    def tearDown(self):
        with self.app.app_context():
            db.session.remove(); db.drop_all()
        os.unlink(self.db_path)

    def test_csrf_token_required(self):
        self.app.config["WTF_CSRF_ENABLED"] = True
        r = self.client.post("/help/ask", json={"question": "hello"})
        self.assertEqual(r.status_code, 400)

    def test_rate_limited_per_person(self):
        codes = [self.client.post("/help/ask", json={"question": "How do I upload?"}).status_code for _ in range(11)]
        self.assertEqual(codes[:10], [200] * 10)
        self.assertEqual(codes[10], 429)


if __name__ == "__main__":
    unittest.main()
