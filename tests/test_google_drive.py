"""Google Drive integration: OAuth flow, encrypted tokens, roles, import, CSP scope."""
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
from unittest import mock

from cryptography.fernet import Fernet

from app import create_app
from app.extensions import bcrypt, db
from app.integrations import google_drive as gd


class FakeGoogle:
    """Stands in for gd._http: records calls and returns canned Google responses."""
    def __init__(self, scope="https://www.googleapis.com/auth/drive.file openid https://www.googleapis.com/auth/userinfo.email"):
        self.calls, self.scope = [], scope
        self.files = {
            "doc1": ({"id": "doc1", "name": "Pricing policy", "mimeType": "application/vnd.google-apps.document"}, None),
            "txt1": ({"id": "txt1", "name": "notes.txt", "mimeType": "text/plain", "size": "20"}, b"Fuel surcharge is 4 percent."),
            "img1": ({"id": "img1", "name": "logo.png", "mimeType": "image/png", "size": "10"}, b"x"),
        }

    def __call__(self, url, data=None, headers=None, method=None, raw=False, limit=None):
        self.calls.append((url, data))
        if url == gd.TOKEN_URL:
            if data.get("grant_type") == "authorization_code":
                return {"access_token": "AT-1", "refresh_token": "RT-secret-123", "expires_in": 3600, "scope": self.scope}
            return {"access_token": "AT-2", "expires_in": 3600}
        if url == gd.USERINFO_URL:
            return {"email": "ama@accra-logistics.com"}
        if url == gd.REVOKE_URL:
            return {}
        fid = url[len(gd.DRIVE_FILES):].split("?")[0].split("/")[0]
        meta, body = self.files[fid]
        if "/export?" in url:
            return b"PK-docx-bytes"
        if "alt=media" in url:
            return body
        return meta


class DriveTests(unittest.TestCase):
    def setUp(self, configured=True):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False); f.close()
        self.db_path, self.store = f.name, tempfile.mkdtemp()

        class TestConfig:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + f.name.replace("\\", "/")
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False
            RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"
            CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"
            PUBLIC_BASE_URL = "https://ai-workforce.example"
            STORAGE_BACKEND = "local"
            PRIVATE_UPLOAD_ROOT = self.store
            FILE_ENCRYPTION_KEY = Fernet.generate_key().decode()
            INTEGRATION_ENCRYPTION_KEY = Fernet.generate_key().decode()
            GOOGLE_CLIENT_ID = "client-id.apps.googleusercontent.com" if configured else None
            GOOGLE_CLIENT_SECRET = "client-secret" if configured else None
            GOOGLE_API_KEY = "picker-api-key" if configured else None
            GOOGLE_APP_ID = "123456789012" if configured else None
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
        self.client.post("/auth/register", data={"full_name": "Ama", "email": "owner@example.com",
                                                 "business_name": "Accra Logistics", "password": "a-very-strong-password-123", "accept_terms": "yes"})
        with self.app.app_context():
            from app.models import KnowledgeRepository, Tenant
            t = Tenant.query.first()
            db.session.add(KnowledgeRepository(tenant_id=t.id, name="Finance policies", description=""))
            db.session.commit()
            self.repo_id = KnowledgeRepository.query.first().id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove(); db.drop_all()
        os.unlink(self.db_path); shutil.rmtree(self.store, ignore_errors=True)

    def connect(self, fake=None):
        fake = fake or FakeGoogle()
        r = self.client.post("/knowledge/integrations/google/connect")
        state = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["Location"]).query)["state"][0]
        with mock.patch.object(gd, "_http", side_effect=fake):
            r = self.client.get(f"/knowledge/integrations/google/callback?state={state}&code=auth-code")
        return r, fake

    def connection(self):
        with self.app.app_context():
            from app.models import IntegrationConnection
            return IntegrationConnection.query.filter_by(provider="google_drive").first()

    # ------------------------------------------------------------------
    def test_connect_asks_google_for_narrow_scopes_only(self):
        r = self.client.post("/knowledge/integrations/google/connect")
        self.assertEqual(r.status_code, 302)
        url = urllib.parse.urlparse(r.headers["Location"])
        q = urllib.parse.parse_qs(url.query)
        self.assertEqual(url.netloc, "accounts.google.com")
        scopes = q["scope"][0].split()
        self.assertIn("https://www.googleapis.com/auth/drive.file", scopes)
        self.assertFalse(any(s.endswith(("drive", "drive.readonly")) for s in scopes))
        self.assertEqual(q["redirect_uri"][0], "https://ai-workforce.example/knowledge/integrations/google/callback")
        self.assertEqual(q["access_type"][0], "offline")
        self.assertTrue(len(q["state"][0]) > 30)

    def test_callback_rejects_wrong_state(self):
        self.client.post("/knowledge/integrations/google/connect")
        with mock.patch.object(gd, "_http", side_effect=FakeGoogle()) as m:
            self.client.get("/knowledge/integrations/google/callback?state=forged&code=x")
        m.assert_not_called()
        self.assertIsNone(self.connection())

    def test_callback_stores_tokens_encrypted(self):
        r, _ = self.connect()
        self.assertEqual(r.status_code, 302)
        conn = self.connection()
        self.assertEqual(conn.status, "connected")
        self.assertNotIn("RT-secret-123", conn.credential_ciphertext)
        self.assertEqual(conn.metadata_json["account_email"], "ama@accra-logistics.com")
        with self.app.app_context():
            from app.integrations.vault import decrypt_credentials
            self.assertEqual(decrypt_credentials(conn.credential_ciphertext)["refresh_token"], "RT-secret-123")

    def test_callback_requires_drive_permission(self):
        self.connect(FakeGoogle(scope="openid https://www.googleapis.com/auth/userinfo.email"))
        self.assertIsNone(self.connection())

    def test_page_states_and_csp_scope(self):
        page = self.client.get("/knowledge/integrations")
        self.assertIn("Connect Google Drive", page.get_data(as_text=True))
        csp = page.headers["Content-Security-Policy"]
        self.assertNotIn("apis.google.com", csp)
        # the Connect form redirects to Google sign-in: browsers check form-action on that redirect
        form_action = csp.split("form-action")[1].split(";")[0]
        self.assertIn("https://accounts.google.com", form_action)
        self.assertNotIn("accounts.google.com", self.client.get("/dashboard").headers["Content-Security-Policy"])
        self.connect()
        page = self.client.get("/knowledge/integrations")
        html = page.get_data(as_text=True)
        self.assertIn("ama@accra-logistics.com", html)
        self.assertIn("Import from Google Drive", html)
        self.assertIn("js/drive-picker.js", html)
        self.assertIn("https://apis.google.com", page.headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", page.headers["Content-Security-Policy"])
        self.assertIn("https://accounts.google.com", page.headers["Content-Security-Policy"].split("form-action")[1])
        # every other page keeps the strict policy
        self.assertNotIn("apis.google.com", self.client.get("/dashboard").headers["Content-Security-Policy"])

    def test_picker_token(self):
        self.assertEqual(self.client.post("/knowledge/integrations/google/picker-token").status_code, 409)
        self.connect()
        with mock.patch.object(gd, "_http", side_effect=FakeGoogle()):
            r = self.client.post("/knowledge/integrations/google/picker-token")
        d = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(d["access_token"], "AT-1")
        self.assertEqual(d["api_key"], "picker-api-key")
        self.assertEqual(d["app_id"], "123456789012")
        self.assertNotIn("refresh", json.dumps(d))

    def test_import_adds_documents_and_reports_failures(self):
        self.connect()
        with mock.patch.object(gd, "_http", side_effect=FakeGoogle()):
            r = self.client.post("/knowledge/integrations/google/import",
                                 json={"repository_id": self.repo_id, "file_ids": ["txt1", "img1"]})
        d = r.get_json()
        self.assertEqual(r.status_code, 200, d)
        self.assertEqual(d["imported"], 1)
        self.assertTrue(d["results"][0]["ok"])
        self.assertFalse(d["results"][1]["ok"])
        self.assertIn("can't read", d["results"][1]["error"])
        with self.app.app_context():
            from app.models import AuditLog, KnowledgeDocument
            doc = KnowledgeDocument.query.one()
            self.assertEqual(doc.original_filename, "notes.txt")
            self.assertEqual(doc.repository_id, self.repo_id)
            self.assertTrue(AuditLog.query.filter_by(action="integration.google_drive_import").first())

    def test_import_validation(self):
        self.connect()
        self.assertEqual(self.client.post("/knowledge/integrations/google/import", json={"repository_id": 999, "file_ids": ["txt1"]}).status_code, 400)
        self.assertEqual(self.client.post("/knowledge/integrations/google/import", json={"repository_id": self.repo_id, "file_ids": []}).status_code, 400)
        many = [f"f{i}" for i in range(11)]
        self.assertEqual(self.client.post("/knowledge/integrations/google/import", json={"repository_id": self.repo_id, "file_ids": many}).status_code, 400)

    def test_disconnect_revokes_and_forgets(self):
        self.connect()
        fake = FakeGoogle()
        with mock.patch.object(gd, "_http", side_effect=fake):
            self.client.post("/knowledge/integrations/google/disconnect")
        self.assertTrue(any(u == gd.REVOKE_URL for u, _ in fake.calls))
        conn = self.connection()
        self.assertEqual(conn.status, "not_connected")
        self.assertEqual(conn.credential_ciphertext, "")

    def test_roles(self):
        with self.app.app_context():
            from app.models import Tenant, TenantMembership, User
            t = Tenant.query.first()
            u = User(email="staff@example.com", full_name="Staff", password_hash=bcrypt.generate_password_hash("a-very-strong-password-123").decode())
            db.session.add(u); db.session.flush()
            db.session.add(TenantMembership(user_id=u.id, tenant_id=t.id, role="employee", status="active")); db.session.commit()
        self.client.post("/auth/logout")
        self.client.post("/auth/login", data={"email": "staff@example.com", "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.assertEqual(self.client.post("/knowledge/integrations/google/connect").status_code, 403)
        self.assertEqual(self.client.post("/knowledge/integrations/google/picker-token").status_code, 403)
        self.assertIn("Ask a workspace Owner or Admin", self.client.get("/knowledge/integrations").get_data(as_text=True))

    def test_download_formats(self):
        fake = FakeGoogle()
        with self.app.app_context(), mock.patch.object(gd, "_http", side_effect=fake):
            name, data = gd.download("AT", "doc1")
            self.assertEqual(name, "Pricing policy.docx")
            self.assertIn("export?mimeType=application%2Fvnd.openxmlformats", fake.calls[-1][0])
            self.assertEqual(gd.download("AT", "txt1"), ("notes.txt", b"Fuel surcharge is 4 percent."))
            with self.assertRaises(gd.DriveError):
                gd.download("AT", "img1")
            with self.assertRaises(gd.DriveError):
                gd.download("AT", "../../etc")


class DriveNotConfiguredTests(DriveTests):
    def setUp(self):
        super().setUp(configured=False)

    def test_page_says_not_available(self):
        html = self.client.get("/knowledge/integrations").get_data(as_text=True)
        self.assertIn("not available yet", html)
        self.assertNotIn("Connect Google Drive", html)
        r = self.client.post("/knowledge/integrations/google/connect")
        self.assertEqual(r.headers["Location"], "/knowledge/integrations")

    # the configured-only tests don't apply here
    test_connect_asks_google_for_narrow_scopes_only = test_callback_rejects_wrong_state = None
    test_callback_stores_tokens_encrypted = test_callback_requires_drive_permission = None
    test_page_states_and_csp_scope = test_picker_token = test_import_adds_documents_and_reports_failures = None
    test_import_validation = test_disconnect_revokes_and_forgets = test_roles = None


if __name__ == "__main__":
    unittest.main()
