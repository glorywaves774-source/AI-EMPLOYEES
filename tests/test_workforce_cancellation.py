import os
import tempfile
import unittest

from app import create_app
from app.extensions import db, bcrypt
from app.models import Tenant, User, TenantMembership, WorkforceTask, AuditLog
from app.ai_engine import _cancel_requested


class WorkforceCancellationTests(unittest.TestCase):
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

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            tenant = Tenant(name="Test workspace", slug="test-workspace")
            user = User(email="owner@example.test", full_name="Owner",
                        password_hash=bcrypt.generate_password_hash("test-password-123").decode())
            db.session.add_all([tenant, user])
            db.session.flush()
            db.session.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="owner", status="active"))
            task = WorkforceTask(tenant_id=tenant.id, created_by_user_id=user.id,
                                 title="Test task", instructions="Do a test", status="queued")
            db.session.add(task)
            db.session.commit()
            self.user_id, self.tenant_id, self.task_id = user.id, tenant.id, task.id
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user_id)
            session["_fresh"] = True
            session["active_tenant_id"] = self.tenant_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        os.unlink(self.tmp.name)

    def test_queued_task_can_be_cancelled_and_audited(self):
        response = self.client.post(f"/workforce/tasks/{self.task_id}/cancel")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            task = db.session.get(WorkforceTask, self.task_id)
            self.assertEqual(task.status, "cancelled")
            self.assertEqual(AuditLog.query.filter_by(action="workforce_task.cancelled").count(), 1)

    def test_running_task_receives_cooperative_cancel_request(self):
        with self.app.app_context():
            task = db.session.get(WorkforceTask, self.task_id)
            task.status = "running"
            db.session.commit()
        response = self.client.post(f"/workforce/tasks/{self.task_id}/cancel")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            task = db.session.get(WorkforceTask, self.task_id)
            self.assertEqual(task.status, "cancel_requested")

    def test_worker_finalises_a_cooperative_cancel_request(self):
        with self.app.app_context():
            task = db.session.get(WorkforceTask, self.task_id)
            task.status = "cancel_requested"
            db.session.commit()
            self.assertTrue(_cancel_requested(self.task_id, self.tenant_id, self.user_id))
            db.session.expire_all()
            self.assertEqual(db.session.get(WorkforceTask, self.task_id).status, "cancelled")

    def test_task_from_another_tenant_is_not_visible(self):
        with self.app.app_context():
            other = Tenant(name="Other workspace", slug="other-workspace")
            db.session.add(other)
            db.session.flush()
            foreign_task = WorkforceTask(tenant_id=other.id, title="Private", instructions="Private", status="queued")
            db.session.add(foreign_task)
            db.session.commit()
            foreign_id = foreign_task.id
        response = self.client.post(f"/workforce/tasks/{foreign_id}/cancel")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
