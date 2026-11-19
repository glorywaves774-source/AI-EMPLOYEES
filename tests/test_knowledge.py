import os
import tempfile
import unittest

from cryptography.fernet import Fernet
from app import create_app
from app.extensions import db
from app.models import (AIEmployee, AIEmployeeKnowledgePermission, KnowledgeChunk,
                        KnowledgeDocument, KnowledgeRepository, Tenant, User)
from app.knowledge.services import chunk_text, extract_document_text, retrieve_employee_knowledge
from app.knowledge.storage import read_file, store_file
from app.integrations.vault import decrypt_credentials, encrypt_credentials


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "knowledge-test.db")
        key = Fernet.generate_key().decode("ascii")

        class TestConfig:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.db_path.replace("\\", "/")
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SESSION_COOKIE_HTTPONLY = True
            SESSION_COOKIE_SECURE = False
            SESSION_COOKIE_SAMESITE = "Lax"
            WTF_CSRF_ENABLED = False
            MAX_CONTENT_LENGTH = 12 * 1024 * 1024
            FILE_ENCRYPTION_KEY = key
            INTEGRATION_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
            STORAGE_BACKEND = "local"
            PRIVATE_UPLOAD_ROOT = os.path.join(self.tmp.name, "private")
            CELERY_BROKER_URL = "memory://"
            CELERY_RESULT_BACKEND = "cache+memory://"

        self.app = create_app(TestConfig)
        with self.app.app_context():
            db.create_all()
            tenant = Tenant(name="Knowledge Test", slug="knowledge-test")
            user = User(email="owner@example.test", password_hash="test-hash", full_name="Test Owner")
            db.session.add_all([tenant, user])
            db.session.flush()
            repo = KnowledgeRepository(tenant_id=tenant.id, name="Policies")
            employee = AIEmployee(tenant_id=tenant.id, name="AI HR Officer", job_title="Human Resource Officer",
                                  description="HR support", status="active")
            db.session.add_all([repo, employee])
            db.session.flush()
            doc = KnowledgeDocument(tenant_id=tenant.id, repository_id=repo.id,
                original_filename="leave-policy.txt", storage_key="a" * 32,
                mime_type="text/plain", file_size=80, sha256="b" * 64,
                status="ready", extracted_chars=80)
            db.session.add(doc)
            db.session.flush()
            db.session.add(KnowledgeChunk(tenant_id=tenant.id, document_id=doc.id,
                chunk_index=0, content="Employees receive annual leave according to the company leave policy."))
            db.session.add(AIEmployeeKnowledgePermission(tenant_id=tenant.id,
                employee_id=employee.id, repository_id=repo.id))
            db.session.commit()
            self.tenant_id = tenant.id
            self.employee_id = employee.id
            self.repo_id = repo.id
            self.doc_id = doc.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.tmp.cleanup()

    def test_text_extraction_and_chunking(self):
        mime, text = extract_document_text("policy.txt", b"Annual leave policy for all employees.")
        self.assertEqual(mime, "text/plain")
        self.assertIn("Annual leave", text)
        chunks = chunk_text("A" * 3500)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunks))

    def test_employee_retrieval_requires_explicit_repository_grant(self):
        with self.app.app_context():
            result = retrieve_employee_knowledge(self.tenant_id, self.employee_id, "annual leave")
            self.assertIn("annual leave", result.lower())
            unassigned = AIEmployee(tenant_id=self.tenant_id, name="AI Accountant", job_title="Accountant")
            db.session.add(unassigned)
            db.session.commit()
            denied = retrieve_employee_knowledge(self.tenant_id, unassigned.id, "annual leave")
            self.assertEqual(denied, "")
            cross_tenant = retrieve_employee_knowledge(self.tenant_id + 999, self.employee_id, "annual leave")
            self.assertEqual(cross_tenant, "")

    def test_private_storage_encrypts_and_decrypts_file(self):
        with self.app.app_context():
            store_file("c" * 32, b"confidential business document")
            stored_path = os.path.join(self.app.config["PRIVATE_UPLOAD_ROOT"], "c" * 32 + ".enc")
            with open(stored_path, "rb") as handle:
                self.assertNotIn(b"confidential business document", handle.read())
            self.assertEqual(read_file("c" * 32), b"confidential business document")

    def test_integration_credential_envelope_round_trip(self):
        with self.app.app_context():
            credentials = {"refresh_token": "example-secret", "scope": "drive.readonly"}
            ciphertext = encrypt_credentials(credentials)
            self.assertNotIn("example-secret", ciphertext)
            self.assertEqual(decrypt_credentials(ciphertext), credentials)


if __name__ == "__main__":
    unittest.main()
