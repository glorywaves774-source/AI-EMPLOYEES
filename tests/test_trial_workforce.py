"""Free trial: whole workforce for 14 days, paced allowance, protected AI balance,
and agents that run end to end (with the AI model mocked)."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import create_app
from app.extensions import bcrypt, db
from app.models import (AgentRun, AIEmployee, PlatformAdmin, TeamExecution, TeamExecutionStep,
                        TenantSubscription, WorkforceTask)
from app.billing.services import AI_SERVICE_UNAVAILABLE, can_activate_employee, can_create_task, task_usage
from app.workforce.profiles import STARTER_PROFILES


class Base(unittest.TestCase):
    extra = {}

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()
        extra = self.extra

        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False; RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"; PUBLIC_BASE_URL = "http://localhost"; STORAGE_BACKEND = "local"
            OPENAI_API_KEY = "test-key"; OPENAI_MODEL = "paid-model"
            TRIAL_DAILY_TASK_LIMIT = 5; TRIAL_DAILY_TOKEN_POOL = 100000; TRIAL_MAX_AI_EMPLOYEES = 10
            TEAM_EXECUTION_TOKEN_BUDGET = 60000; TEAM_MAX_STEPS = 5
        for k, v in extra.items():
            setattr(C, k, v)
        self.app = create_app(C); self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
        r = self.client.post("/auth/register", data={"full_name": "Owner", "email": "o@example.com",
            "business_name": "Example Ltd", "password": "a-very-strong-password-123"})
        self.assertIn(r.status_code, (302, 303))
        with self.app.app_context():
            self.tid = TenantSubscription.query.first().tenant_id
        self.ctx = self.app.app_context(); self.ctx.push()

    def tearDown(self):
        db.session.remove(); self.ctx.pop()
        with self.app.app_context():
            db.drop_all()
        os.unlink(self.tmp.name)

    def add_tasks(self, n, status="completed", error=""):
        for i in range(n):
            db.session.add(WorkforceTask(tenant_id=self.tid, title=f"t{i}", instructions="x",
                                         status=status, error_message=error))
        db.session.commit()


class SignupTests(Base):
    def test_new_workspace_gets_whole_team_active_with_profiles(self):
        emps = AIEmployee.query.filter_by(tenant_id=self.tid).all()
        self.assertEqual(len(emps), 10)
        self.assertTrue(all(e.status == "active" for e in emps))
        for e in emps:
            self.assertEqual(e.description, STARTER_PROFILES[e.job_title][0])
            self.assertGreaterEqual(len(e.responsibilities_json), 3)
            self.assertGreaterEqual(len(e.skills_json), 3)

    def test_dashboard_shows_trial_note(self):
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Free trial:", html)
        self.assertIn("0 of 5 assignments today", html)


class AllowanceTests(Base):
    def test_trial_daily_limit(self):
        self.add_tasks(4)
        self.assertTrue(can_create_task(self.tid)[0])
        self.add_tasks(1)
        ok, msg = can_create_task(self.tid)
        self.assertFalse(ok); self.assertIn("5 assignments a day", msg)

    def test_yesterdays_tasks_do_not_count_today(self):
        self.add_tasks(5)
        WorkforceTask.query.update({"created_at": datetime.now(timezone.utc) - timedelta(days=1)})
        db.session.commit()
        self.assertTrue(can_create_task(self.tid)[0])

    def test_provider_failures_are_not_counted(self):
        self.add_tasks(5, status="failed", error=AI_SERVICE_UNAVAILABLE + ". Kayron has been alerted.")
        self.add_tasks(1, status="failed", error=None)
        self.assertTrue(can_create_task(self.tid)[0])
        self.assertEqual(task_usage(self.tid), 1)

    def test_shared_trial_token_pool_protects_balance(self):
        self.add_tasks(1)
        db.session.add(AgentRun(tenant_id=self.tid, task_id=WorkforceTask.query.first().id, employee_name="x", model_name="m", status="completed",
                                input_text="", input_tokens=60000, output_tokens=40000))
        db.session.commit()
        ok, msg = can_create_task(self.tid)
        self.assertFalse(ok); self.assertIn("fully booked", msg)
        # Paying customers are never affected by the trial pool or the daily trial limit.
        TenantSubscription.query.update({"status": "active"}); db.session.commit()
        AIEmployee.query.filter(AIEmployee.job_title.notin_(["Team Coordinator", "Accountant", "Marketing Officer"])) \
            .update({"status": "paused"}, synchronize_session=False); db.session.commit()
        self.add_tasks(5)
        self.assertTrue(can_create_task(self.tid)[0])

    def test_paid_starter_must_trim_team_to_plan_limit(self):
        TenantSubscription.query.update({"status": "active"}); db.session.commit()
        ok, msg = can_create_task(self.tid)
        self.assertFalse(ok); self.assertIn("allows 3 active AI employees", msg)
        self.assertFalse(can_activate_employee(self.tid)[0])

    def test_trial_can_activate_up_to_ten(self):
        AIEmployee.query.filter_by(job_title="Accountant").update({"status": "draft"}); db.session.commit()
        self.assertTrue(can_activate_employee(self.tid)[0])
        AIEmployee.query.update({"status": "active"}); db.session.commit()
        ok, msg = can_activate_employee(self.tid)
        self.assertFalse(ok); self.assertIn("free trial allows up to 10", msg)


class ProviderErrorTests(Base):
    extra = {"TRIAL_OPENAI_MODEL": "trial-model"}

    def test_trial_uses_trial_model(self):
        from app.ai_engine import model_for_tenant
        self.assertEqual(model_for_tenant(self.tid), "trial-model")
        TenantSubscription.query.update({"status": "active"}); db.session.commit()
        self.assertEqual(model_for_tenant(self.tid), "paid-model")

    def test_credit_exhausted_becomes_friendly_uncounted_error(self):
        from app.ai_engine import AIServiceUnavailable, _call_model
        client = mock.Mock()
        client.responses.create.side_effect = Exception(
            "Error code: 429 - {'error': {'code': 'credit_balance_exhausted', 'type': 'insufficient_quota'}}")
        with mock.patch("app.ai_engine._client", return_value=client):
            with self.assertRaises(AIServiceUnavailable) as cm:
                _call_model("i", "x", tenant_id=self.tid)
        self.assertTrue(str(cm.exception).startswith(AI_SERVICE_UNAVAILABLE))
        self.assertEqual(client.responses.create.call_args.kwargs["model"], "trial-model")

    def test_other_errors_still_raise_normally(self):
        from app.ai_engine import AIServiceUnavailable, _call_model
        client = mock.Mock(); client.responses.create.side_effect = TimeoutError("slow")
        with mock.patch("app.ai_engine._client", return_value=client):
            with self.assertRaises(TimeoutError):
                _call_model("i", "x")

    def test_platform_admin_sees_credit_warning(self):
        db.session.add(PlatformAdmin(email="admin@example.com", full_name="Admin", is_active=True,
                                     password_hash=bcrypt.generate_password_hash("admin-password-123456").decode()))
        self.add_tasks(1, status="failed")
        db.session.add(AgentRun(tenant_id=self.tid, task_id=WorkforceTask.query.first().id, employee_name="x", model_name="", status="failed",
                                input_text="", error_message="Error code: 429 insufficient_quota credit_balance_exhausted"))
        db.session.commit()
        with self.client.session_transaction() as s:
            s["platform_admin_id"] = PlatformAdmin.query.first().id
        html = self.client.get("/platform/").get_data(as_text=True)
        self.assertIn("run out of credit", html)


class TeamRunTests(Base):
    """Planner -> specialists -> coordinator, with the model mocked."""

    def _plan(self):
        from app.workforce.team_execution import create_team_plan
        task = WorkforceTask(tenant_id=self.tid, title="Launch plan", instructions="Plan a product launch",
                             status="queued")
        db.session.add(task); db.session.commit()
        return task, create_team_plan(self.tid, task.id, None)

    def _run_steps(self, execution_id):
        from app.workforce.team_execution import execute_step
        for st in TeamExecutionStep.query.filter_by(team_execution_id=execution_id).all():
            st.status = "dispatched"
        db.session.commit()
        for st in TeamExecutionStep.query.filter_by(team_execution_id=execution_id).all():
            execute_step(self.tid, execution_id, st.step_key)

    def test_full_team_run_completes_within_budget(self):
        ids = {e.job_title: e.id for e in AIEmployee.query.filter_by(tenant_id=self.tid)}
        plan = {"steps": [{"employee_id": ids[t], "title": f"{t} part", "instructions": "do it", "depends_on": []}
                          for t in ["Marketing Officer", "Accountant", "Project Manager", "Research Officer",
                                    "Customer Service Officer", "Operations Manager", "Executive Assistant"]]}
        calls = []

        def fake(instructions, prompt, tenant_id=None):
            calls.append(instructions)
            if "Break the business assignment" in instructions:
                return json.dumps(plan), "m", 2500, 600
            if "Consolidate" in instructions:
                return json.dumps({"deliverable": "Final launch plan", "requires_human_review": False,
                                   "review_reason": ""}), "m", 12000, 2500
            return "Specialist contribution", "m", 3000, 2000

        from app.workforce.team_execution import finalize_team_execution
        with mock.patch("app.workforce.team_execution._call_model", side_effect=fake):
            task, eid = self._plan()
            steps = TeamExecutionStep.query.filter_by(team_execution_id=eid).all()
            self.assertEqual(len(steps), 5, "plan is capped at TEAM_MAX_STEPS")
            self.assertIn("1 to 5 focused", calls[0])
            self.assertIn(STARTER_PROFILES["Marketing Officer"][0], calls[0], "planner sees job profiles")
            self._run_steps(eid)
            self.assertTrue(all(s.status == "completed" for s in
                                TeamExecutionStep.query.filter_by(team_execution_id=eid)))
            finalize_team_execution(self.tid, eid)
        task = db.session.get(WorkforceTask, task.id)
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.final_output, "Final launch plan")
        self.assertLessEqual(db.session.get(TeamExecution, eid).tokens_used, 60000)

    def test_credit_outage_fails_fast_with_clear_uncounted_message(self):
        from app.ai_engine import AIServiceUnavailable
        from app.workforce.team_execution import finalize_team_execution
        outage = AIServiceUnavailable(AI_SERVICE_UNAVAILABLE + ". Kayron has been alerted.")

        def planner_ok(instructions, prompt, tenant_id=None):
            if "Break the business assignment" in instructions:
                raise ValueError("bad json")  # planner falls back to the simple plan
            raise outage

        with mock.patch("app.workforce.team_execution._call_model", side_effect=planner_ok):
            task, eid = self._plan()
            self._run_steps(eid)
            steps = TeamExecutionStep.query.filter_by(team_execution_id=eid).all()
            self.assertTrue(all(s.status == "failed" and s.attempts == 1 for s in steps), "no pointless retries")
            finalize_team_execution(self.tid, eid)
        task = db.session.get(WorkforceTask, task.id)
        self.assertEqual(task.status, "failed")
        self.assertTrue(task.error_message.startswith(AI_SERVICE_UNAVAILABLE))
        self.assertEqual(task_usage(self.tid), 0)

    def test_planner_outage_is_not_hidden_by_fallback(self):
        from app.ai_engine import AIServiceUnavailable
        with mock.patch("app.workforce.team_execution._call_model",
                        side_effect=AIServiceUnavailable(AI_SERVICE_UNAVAILABLE + ".")):
            with self.assertRaises(AIServiceUnavailable):
                self._plan()


if __name__ == "__main__":
    unittest.main()
