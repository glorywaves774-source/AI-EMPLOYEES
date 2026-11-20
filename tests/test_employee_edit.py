import os, tempfile, unittest
from app import create_app
from app.extensions import db
from app.models import AIEmployee, AuditLog


class EmployeeEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()
        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False; RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"; PUBLIC_BASE_URL = "http://localhost"; STORAGE_BACKEND = "local"
        self.app = create_app(C); self.client = self.app.test_client()
        with self.app.app_context(): db.create_all()
        self.client.post("/auth/register", data={"full_name": "Owner", "email": "o@example.com",
            "business_name": "Example Ltd", "password": "a-very-strong-password-123"})
        with self.app.app_context():
            e = AIEmployee.query.filter_by(job_title="Accountant").first()
            e.job_title = "Accountantant"; db.session.commit(); self.eid = e.id; self.dept = e.department_id

    def tearDown(self):
        with self.app.app_context(): db.session.remove(); db.drop_all()
        os.unlink(self.tmp.name)

    def test_dashboard_shows_edit_form(self):
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn(f"/employees/{self.eid}/edit", html)
        self.assertIn("Edit details", html)

    def test_owner_can_fix_job_title_and_it_is_audited(self):
        r = self.client.post(f"/employees/{self.eid}/edit", data={"name": "AI Accountant",
            "job_title": "Accountant", "department_id": self.dept, "description": "Keeps the books"})
        self.assertIn(r.status_code, (302, 303))
        with self.app.app_context():
            e = db.session.get(AIEmployee, self.eid)
            self.assertEqual(e.job_title, "Accountant"); self.assertEqual(e.description, "Keeps the books")
            log = AuditLog.query.filter_by(action="ai_employee.updated").one()
            self.assertEqual(log.details_json["job_title"]["to"], "Accountant")

    def test_blank_title_rejected(self):
        self.client.post(f"/employees/{self.eid}/edit", data={"name": "X", "job_title": " "})
        with self.app.app_context():
            self.assertEqual(db.session.get(AIEmployee, self.eid).job_title, "Accountantant")

    def test_other_tenant_department_rejected(self):
        r = self.client.post(f"/employees/{self.eid}/edit", data={"name": "X", "job_title": "Y", "department_id": 9999})
        self.assertEqual(r.status_code, 400)

    def test_unknown_employee_404(self):
        r = self.client.post("/employees/9999/edit", data={"name": "X", "job_title": "Y"})
        self.assertEqual(r.status_code, 404)
