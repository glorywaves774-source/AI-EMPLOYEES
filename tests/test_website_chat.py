"""Customer chatbot for business websites (AI mocked)."""
import os
import tempfile
import unittest
from unittest import mock

from app import create_app
from app.extensions import db
from app.models import ChatWidget, TenantSubscription, WidgetMessage

SITE = "https://www.shop.example"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()

        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = True; RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"; PUBLIC_BASE_URL = "https://app.example.test"; STORAGE_BACKEND = "local"
            WIDGET_TRIAL_DAILY_LIMIT = 3
        self.app = create_app(C); self.client = self.app.test_client()
        from flask import g as _g
        def _fresh():
            for k in ("_login_user", "active_tenant_id", "active_tenant", "membership"):
                _g.pop(k, None)
        self.app.before_request_funcs.setdefault(None, []).insert(0, _fresh)
        with self.app.app_context():
            db.create_all()
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client.post("/auth/register", data={"full_name": "Ama", "email": "o@example.com", "business_name": "Ama Shop",
                                                 "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client.get("/website-chat")
        self.client.post("/website-chat", data={"bot_name": "Ama Helper", "greeting": "Hi!", "contact_note": "Call 0539926867",
                                                "brand_color": "#0f9d8a", "allowed_origins": "shop.example", "action": "enable"})
        self.w = ChatWidget.query.one()
        self.app.config["WTF_CSRF_ENABLED"] = True  # the public API must work without a CSRF token
        self.public = self.app.test_client()

    def tearDown(self):
        db.session.remove(); self.ctx.pop()
        with self.app.app_context():
            db.drop_all()
        os.unlink(self.tmp.name)

    def chat(self, msg="What are your opening hours?", origin=SITE):
        return self.public.post(f"/w/{self.w.public_key}/chat", json={"message": msg, "session": "abc"},
                                headers={"Origin": origin})


class WidgetTests(Base):
    def test_settings_saved_and_code_shown(self):
        self.assertTrue(self.w.enabled)
        self.assertEqual(self.w.allowed_origins, "https://shop.example")
        page = self.client.get("/website-chat").get_data(as_text=True)
        self.assertIn(self.w.public_key, page)
        self.assertIn("https://app.example.test/static/js/chat-widget.js", page)

    def test_config_for_allowed_site_only(self):
        r = self.public.get(f"/w/{self.w.public_key}/config", headers={"Origin": SITE})  # www. variant allowed
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["Access-Control-Allow-Origin"], SITE)
        self.assertEqual(r.get_json()["name"], "Ama Helper")
        self.assertEqual(self.public.get(f"/w/{self.w.public_key}/config", headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.public.get(f"/w/{self.w.public_key}/config").status_code, 403)
        self.assertEqual(self.public.get("/w/wrong-key/config", headers={"Origin": SITE}).status_code, 404)

    def test_preflight(self):
        r = self.public.open(f"/w/{self.w.public_key}/chat", method="OPTIONS", headers={"Origin": SITE})
        self.assertEqual(r.status_code, 204); self.assertIn("POST", r.headers["Access-Control-Allow-Methods"])

    def test_answers_from_knowledge_and_logs(self):
        with mock.patch("app.knowledge.services.retrieve_employee_knowledge", return_value="Open 8am-6pm Mon-Sat.") as k, \
                mock.patch("app.ai_providers.complete", return_value=("We're open 8am to 6pm, Monday to Saturday.", "m", 50, 20)) as ai:
            r = self.chat()
        self.assertEqual(r.status_code, 200)
        self.assertIn("8am", r.get_json()["answer"])
        system, prompt = ai.call_args.args[:2]
        self.assertIn("ONLY the business information", system); self.assertIn("Call 0539926867", system)
        self.assertIn("Open 8am-6pm", prompt)
        self.assertTrue(ai.call_args.kwargs["trial"])
        m = WidgetMessage.query.one()
        self.assertEqual((m.origin, m.input_tokens), (SITE, 50))
        self.assertIn("opening hours", self.client.get("/website-chat").get_data(as_text=True))

    def test_daily_limit_and_ai_outage_give_contact_details(self):
        from app.ai_providers import AIServiceUnavailable
        with mock.patch("app.ai_providers.complete", side_effect=AIServiceUnavailable("x")):
            self.assertIn("Call 0539926867", self.chat().get_json()["answer"])
        with mock.patch("app.ai_providers.complete", return_value=("ok", "m", 1, 1)) as ai:
            self.chat(); self.chat()
            busy = self.chat().get_json()["answer"]
        self.assertIn("busy", busy); self.assertEqual(ai.call_count, 2)

    def test_disabled_widget_hidden_but_preview_works(self):
        self.w.enabled = False; db.session.commit()
        self.assertEqual(self.chat().status_code, 404)
        with mock.patch("app.ai_providers.complete", return_value=("hi", "m", 1, 1)):
            self.assertEqual(self.chat(origin="https://app.example.test").status_code, 200)
        self.assertIn("chat-widget.js", self.client.get("/website-chat/preview").get_data(as_text=True))

    def test_expired_subscription(self):
        TenantSubscription.query.update({"status": "expired"}); db.session.commit()
        with mock.patch("app.ai_providers.complete") as ai:
            self.assertIn("not available", self.chat().get_json()["answer"])
        ai.assert_not_called()

    def test_new_code_stops_old_one(self):
        old = self.w.public_key
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client.post("/website-chat", data={"bot_name": "Ama Helper", "allowed_origins": "shop.example", "action": "new_key"})
        self.assertEqual(self.public.get(f"/w/{old}/config", headers={"Origin": SITE}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
