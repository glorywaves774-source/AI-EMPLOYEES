"""Paystack (Mobile Money), email notices, legal pages, Word/Excel, templates, recurring, team invites."""
import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import create_app
from app.extensions import db
from app.models import (AuditLog, Payment, RecurringAssignment, TeamInvitation, TenantMembership,
                        TenantSubscription, User, WorkforceTask)

REPORT = """# Promotion plan

Our goal is **12 paying customers** by month 3.

## Budget

| Item | Month 1 | Share |
|---|---|---|
| Ads | GHS 1,500 | 36% |
| Events | GHS 900 | 22% |
| **Total** | **GHS 2,400** | 58% |

- Launch ads in week 1
- Book two events

1. Approve the budget
2. Start
"""


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
            RATELIMIT_STORAGE_URI = "memory://"; PUBLIC_BASE_URL = "https://app.example.test"; STORAGE_BACKEND = "local"
            PAYSTACK_SECRET_KEY = "sk_test_x"; PLAN_STARTER_AMOUNT = "450"
            SMTP_HOST = None
        for k, v in extra.items():
            setattr(C, k, v)
        self.app = create_app(C); self.client = self.app.test_client()
        from flask import g as _g
        # Tests keep an app context open; don't let one client's sign-in leak into another's request.
        def _fresh_request_state():
            for key in ("_login_user", "active_tenant_id", "active_tenant", "membership"):
                _g.pop(key, None)
        self.app.before_request_funcs.setdefault(None, []).insert(0, _fresh_request_state)
        with self.app.app_context():
            db.create_all()
        r = self.client.post("/auth/register", data={"full_name": "Ama Owner", "email": "owner@example.com",
            "business_name": "Example Ltd", "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.assertEqual(r.status_code, 302)
        self.ctx = self.app.app_context(); self.ctx.push()
        self.tid = TenantSubscription.query.first().tenant_id
        self.send = mock.patch.object(self.app.extensions["celery"], "send_task"); self.sent = self.send.start()

    def tearDown(self):
        self.send.stop(); db.session.remove(); self.ctx.pop()
        with self.app.app_context():
            db.drop_all()
        os.unlink(self.tmp.name)


class PaystackTests(Base):
    def _subscribe(self):
        self.client.get("/billing/")
        from app.models import SubscriptionPlan
        plan = SubscriptionPlan.query.filter_by(code="starter").first()
        with mock.patch("app.billing.services._http_json", return_value={"status": True, "data": {"authorization_url": "https://checkout.paystack.com/x"}}) as http:
            r = self.client.post(f"/billing/subscribe/{plan.id}", data={"provider": "paystack"})
        return r, http, Payment.query.one()

    def test_trial_can_subscribe_to_starter_with_mobile_money(self):
        page = self.client.get("/billing/").get_data(as_text=True)
        self.assertIn("Mobile Money or card", page); self.assertIn("Subscribe", page)
        r, http, payment = self._subscribe()
        self.assertEqual(r.headers["Location"], "https://checkout.paystack.com/x")
        payload = http.call_args.args[2]
        self.assertEqual(payload["channels"], ["mobile_money", "card"])
        self.assertEqual(payload["amount"], "45000"); self.assertEqual(payload["currency"], "GHS")

    def test_callback_verifies_and_activates(self):
        _, _, payment = self._subscribe()
        ok = {"status": "success", "reference": payment.provider_reference, "amount": 45000, "currency": "GHS"}
        with mock.patch("app.billing.services._http_json", return_value={"status": True, "data": ok}):
            self.client.get(f"/billing/paystack/callback?reference={payment.provider_reference}")
        self.assertEqual(db.session.get(Payment, payment.id).status, "paid")
        self.assertEqual(TenantSubscription.query.first().status, "active")

    def test_callback_refuses_wrong_amount(self):
        _, _, payment = self._subscribe()
        bad = {"status": "success", "reference": payment.provider_reference, "amount": 100, "currency": "GHS"}
        with mock.patch("app.billing.services._http_json", return_value={"status": True, "data": bad}):
            self.client.get(f"/billing/paystack/callback?reference={payment.provider_reference}")
        self.assertNotEqual(db.session.get(Payment, payment.id).status, "paid")
        self.assertEqual(TenantSubscription.query.first().status, "trialing")


class NoPaymentTests(Base):
    extra = {"PAYSTACK_SECRET_KEY": None}

    def test_billing_explains_when_payments_not_set_up(self):
        self.assertIn("Online payment is being set up", self.client.get("/billing/").get_data(as_text=True))


class LegalAndSignupTests(Base):
    def test_public_legal_pages(self):
        self.client.post("/auth/logout")
        for path in ("/privacy", "/terms"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn("Act 843", html) if path == "/privacy" else self.assertIn("Republic of Ghana", html)
            self.assertIn("0539926867", html)

    def test_signup_requires_agreement_and_records_version(self):
        self.client.post("/auth/logout")
        self.client.post("/auth/register", data={"full_name": "B", "email": "b@example.com", "business_name": "B Ltd",
                                                 "password": "a-very-strong-password-123"})
        self.assertIsNone(User.query.filter_by(email="b@example.com").first())
        log = AuditLog.query.filter_by(action="tenant.registered").first()
        self.assertEqual(log.details_json["accepted_terms_version"], "2026-11-20")


class ExportTests(Base):
    def setUp(self):
        super().setUp()
        self.task = WorkforceTask(tenant_id=self.tid, title="Promotion plan", instructions="x", status="completed",
                                  final_output=REPORT, completed_at=datetime.now(timezone.utc))
        db.session.add(self.task); db.session.commit()

    def test_word_download(self):
        r = self.client.get(f"/workforce/tasks/{self.task.id}/download/docx")
        self.assertEqual(r.status_code, 200); self.assertIn("promotion-plan.docx", r.headers["Content-Disposition"])
        from docx import Document
        doc = Document(io.BytesIO(r.data))
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("Budget", text); self.assertIn("Launch ads in week 1", text)
        self.assertEqual(len(doc.tables), 1); self.assertEqual(doc.tables[0].cell(1, 1).text, "GHS 1,500")

    def test_excel_download_has_real_numbers(self):
        page = self.client.get(f"/workforce/tasks/{self.task.id}").get_data(as_text=True)
        self.assertIn("Download Excel", page); self.assertIn("Download Word", page)
        r = self.client.get(f"/workforce/tasks/{self.task.id}/download/xlsx")
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(r.data)).active
        self.assertEqual(ws["A4"].value, "Item")
        self.assertEqual(ws["B5"].value, 1500); self.assertIn("GHS", ws["B5"].number_format)
        self.assertAlmostEqual(ws["C5"].value, 0.36); self.assertEqual(ws["B7"].value, 2400)

    def test_no_excel_without_tables(self):
        self.task.final_output = "Just words."; db.session.commit()
        self.assertEqual(self.client.get(f"/workforce/tasks/{self.task.id}/download/xlsx").status_code, 404)
        self.assertNotIn("Download Excel", self.client.get(f"/workforce/tasks/{self.task.id}").get_data(as_text=True))


class TemplateTests(Base):
    def test_template_prefills_and_placeholders_must_be_replaced(self):
        html = self.client.get("/dashboard?template=cash-flow").get_data(as_text=True)
        self.assertIn("Cash-flow forecast for [months]", html); self.assertIn("Template added", html)
        self.client.post("/workforce/execute", data={"title": "Cash-flow forecast for [months]", "instructions": "x"})
        self.assertEqual(WorkforceTask.query.count(), 0)
        self.client.post("/workforce/execute", data={"title": "Cash-flow Jan-Mar", "instructions": "Sales GHS 5,000."})
        self.assertEqual(WorkforceTask.query.count(), 1)


class RecurringTests(Base):
    def test_create_and_run_due(self):
        from app.workforce.recurring import next_run, run_due
        self.client.post("/workforce/execute", data={"title": "Weekly posts", "instructions": "Write posts.",
                                                     "repeat": "weekly", "repeat_hour": "9"})
        r = RecurringAssignment.query.one()
        self.assertEqual(r.hour, 9); self.assertGreater(r.next_run_at.replace(tzinfo=timezone.utc), datetime.now(timezone.utc))
        self.assertIn("Weekly posts", self.client.get("/workforce/recurring").get_data(as_text=True))
        started, _ = run_due(r.next_run_at.replace(tzinfo=timezone.utc) + timedelta(minutes=5))
        self.assertEqual(started, 1)
        self.assertEqual(WorkforceTask.query.count(), 2)
        self.assertEqual(self.sent.call_args.args[0], "workforce.start_team_orchestration")
        r = RecurringAssignment.query.one()
        self.assertEqual(run_due(r.next_run_at.replace(tzinfo=timezone.utc) + timedelta(minutes=1))[0], 1)

    def test_next_run_rules(self):
        from app.workforce.recurring import next_run
        r = RecurringAssignment(frequency="daily", hour=8, weekday=0, day_of_month=31)
        t = datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)
        self.assertEqual(next_run(r, t), datetime(2026, 11, 21, 8, tzinfo=timezone.utc))
        r.frequency = "weekly"  # Monday
        self.assertEqual(next_run(r, t), datetime(2026, 11, 23, 8, tzinfo=timezone.utc))
        r.frequency = "monthly"
        self.assertEqual(next_run(r, t), datetime(2026, 11, 28, 8, tzinfo=timezone.utc))  # day 31 -> 28
        self.assertEqual(next_run(r, datetime(2026, 11, 28, 9, tzinfo=timezone.utc)), datetime(2026, 12, 28, 8, tzinfo=timezone.utc))

    def test_blocked_runs_are_skipped_not_retried_hourly(self):
        from app.workforce.recurring import run_due
        r = RecurringAssignment(tenant_id=self.tid, title="T", instructions="x", frequency="daily", hour=8,
                                next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        db.session.add(r); db.session.commit()
        TenantSubscription.query.update({"status": "expired"}); db.session.commit()
        self.assertEqual(run_due(), (0, 1))
        r = RecurringAssignment.query.one()
        self.assertIn("not active", r.last_error)
        self.assertGreater(r.next_run_at.replace(tzinfo=timezone.utc), datetime.now(timezone.utc))


class TeamTests(Base):
    def test_invite_link_new_user_joins_with_role(self):
        r = self.client.post("/team/invite", data={"email": "Kofi@Example.com", "role": "manager"})
        page = self.client.get("/team/").get_data(as_text=True)
        self.assertIn("kofi@example.com", page)
        link = page.split('value="https://app.example.test/team/join/')[1].split('"')[0]
        self.client.post("/auth/logout")
        self.assertIn("Join Example Ltd", self.client.get(f"/team/join/{link}").get_data(as_text=True))
        self.client.post(f"/team/join/{link}", data={"full_name": "Kofi", "password": "another-strong-pass-1", "accept_terms": "yes"})
        kofi = User.query.filter_by(email="kofi@example.com").one()
        m = TenantMembership.query.filter_by(user_id=kofi.id).one()
        self.assertEqual((m.tenant_id, m.role), (self.tid, "manager"))
        self.assertEqual(self.client.get(f"/team/join/{link}").status_code, 404, "single use")
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_existing_user_signs_in_to_join(self):
        other = self.app.test_client()
        other.post("/auth/register", data={"full_name": "Esi", "email": "esi@example.com", "business_name": "Esi Ltd",
                                           "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.client.post("/team/invite", data={"email": "esi@example.com", "role": "employee"})
        token = self.client.get("/team/").get_data(as_text=True).split("/team/join/")[1].split('"')[0]
        fresh = self.app.test_client()
        r = fresh.post(f"/auth/login?invite={token}", data={"email": "esi@example.com", "password": "a-very-strong-password-123"})
        self.assertIn(f"/team/join/{token}", r.headers["Location"])
        fresh.post(f"/team/join/{token}")
        esi = User.query.filter_by(email="esi@example.com").one()
        self.assertEqual(TenantMembership.query.filter_by(user_id=esi.id).count(), 2)

    def test_roles_and_removal_rules(self):
        self.client.post("/team/invite", data={"email": "k@example.com", "role": "employee"})
        token = self.client.get("/team/").get_data(as_text=True).split("/team/join/")[1].split('"')[0]
        self.app.test_client().post(f"/team/join/{token}", data={"full_name": "K", "password": "another-strong-pass-1", "accept_terms": "yes"})
        m = TenantMembership.query.filter_by(role="employee").one()
        self.client.post(f"/team/members/{m.id}/role", data={"role": "admin"})
        self.assertEqual(db.session.get(TenantMembership, m.id).role, "admin")
        owner = TenantMembership.query.filter_by(role="owner").one()
        self.assertEqual(self.client.post(f"/team/members/{owner.id}/remove").status_code, 400)
        self.client.post(f"/team/members/{m.id}/remove")
        self.assertIsNone(db.session.get(TenantMembership, m.id))

    def test_employee_cannot_open_team_page(self):
        self.client.post("/team/invite", data={"email": "e@example.com", "role": "employee"})
        token = self.client.get("/team/").get_data(as_text=True).split("/team/join/")[1].split('"')[0]
        c = self.app.test_client()
        c.post(f"/team/join/{token}", data={"full_name": "E", "password": "another-strong-pass-1", "accept_terms": "yes"})
        self.assertEqual(c.get("/team/").status_code, 403)

    def test_invite_email_sent_when_smtp_ready(self):
        with mock.patch("app.team.notify_by_email", return_value=True) as notify:
            self.client.post("/team/invite", data={"email": "x@example.com", "role": "employee"})
        self.assertIn("/team/join/", notify.call_args.args[2])
        self.assertNotIn("Send this link", self.client.get("/team/").get_data(as_text=True))


class EmailNoticeTests(Base):
    def test_assignment_ready_email(self):
        from app.workforce.team_execution import _email_task_owner
        task = WorkforceTask(tenant_id=self.tid, created_by_user_id=User.query.first().id, title="Plan",
                             instructions="x", status="completed", final_output="ok")
        db.session.add(task); db.session.commit()
        with mock.patch("app.security_service.notify_by_email") as notify:
            _email_task_owner(task, ready=True)
        to, subject, body = notify.call_args.args
        self.assertEqual(to, "owner@example.com"); self.assertIn("Ready for you: Plan", subject)
        self.assertIn(f"https://app.example.test/workforce/tasks/{task.id}", body)


if __name__ == "__main__":
    unittest.main()
