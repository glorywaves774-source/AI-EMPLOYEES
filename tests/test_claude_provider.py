"""Claude as an AI provider, with automatic switch-over to OpenAI and back."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from app import create_app
from app.extensions import bcrypt, db
from app.models import AgentRun, PlatformAdmin, TenantSubscription, WorkforceTask
from app import ai_providers
from app.ai_providers import AIServiceUnavailable, complete
from scripts.production_check import validate_environment


class _Err(Exception):
    pass


def claude_error(name, msg="refused"):
    return type(name, (_Err,), {})(msg)


def claude_reply(text="Claude answer", tin=11, tout=7):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=tin, output_tokens=tout))


def openai_reply(text="OpenAI answer"):
    return SimpleNamespace(output_text=text, usage=SimpleNamespace(input_tokens=5, output_tokens=3))


class ProviderTests(unittest.TestCase):
    keys = {"ANTHROPIC_API_KEY": "sk-ant-test", "OPENAI_API_KEY": "sk-test"}
    extra = {}

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()
        keys, extra = self.keys, self.extra

        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False; RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"; PUBLIC_BASE_URL = "http://localhost"; STORAGE_BACKEND = "local"
            OPENAI_MODEL = "gpt-test"; CLAUDE_MODEL = "claude-sonnet-5-5"; TRIAL_CLAUDE_MODEL = "claude-haiku-5-5"
            ANTHROPIC_API_KEY = None; OPENAI_API_KEY = None
        for k, v in {**keys, **extra}.items():
            setattr(C, k, v)
        self.env = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": ""})
        self.env.start()
        self.app = create_app(C); self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
        self.client.post("/auth/register", data={"full_name": "Owner", "email": "o@example.com",
            "business_name": "Example Ltd", "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.tid = TenantSubscription.query.first().tenant_id
        self.claude = mock.Mock(); self.openai = mock.Mock()
        self.p1 = mock.patch.object(ai_providers, "claude_client", return_value=self.claude); self.p1.start()
        self.p2 = mock.patch.object(ai_providers, "openai_client", return_value=self.openai); self.p2.start()

    def tearDown(self):
        self.p1.stop(); self.p2.stop()
        db.session.remove(); self.ctx.pop()
        with self.app.app_context():
            db.drop_all()
        self.env.stop()
        os.unlink(self.tmp.name)


class ClaudeFirstTests(ProviderTests):
    def test_claude_is_used_first_with_sonnet_for_paying_and_haiku_for_trial(self):
        self.claude.messages.create.return_value = claude_reply()
        self.assertEqual(complete("sys", "hello"), ("Claude answer", "claude-sonnet-5-5", 11, 7))
        kwargs = self.claude.messages.create.call_args.kwargs
        self.assertEqual(kwargs["system"], "sys")
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(complete("sys", "hi", trial=True)[1], "claude-haiku-5-5")
        self.openai.responses.create.assert_not_called()

    def test_workspace_trial_status_picks_the_model(self):
        from app.ai_engine import _call_model, model_for_tenant
        self.claude.messages.create.return_value = claude_reply()
        self.assertEqual(model_for_tenant(self.tid), "claude-haiku-5-5")  # new workspaces are on trial
        self.assertEqual(_call_model("i", "x", tenant_id=self.tid)[1], "claude-haiku-5-5")
        TenantSubscription.query.update({"status": "active"}); db.session.commit()
        self.assertEqual(_call_model("i", "x", tenant_id=self.tid)[1], "claude-sonnet-5-5")

    def test_switches_to_openai_when_claude_has_no_credit(self):
        self.claude.messages.create.side_effect = claude_error(
            "BadRequestError", "Your credit balance is too low to access the Anthropic API.")
        self.openai.responses.create.return_value = openai_reply()
        text, model, _, _ = complete("sys", "hello")
        self.assertEqual((text, model), ("OpenAI answer", "gpt-test"))

    def test_switches_when_claude_overloaded(self):
        self.claude.messages.create.side_effect = claude_error("OverloadedError")
        self.openai.responses.create.return_value = openai_reply()
        self.assertEqual(complete("s", "x")[0], "OpenAI answer")

    def test_both_refuse_gives_clear_uncounted_error_with_refs(self):
        self.claude.messages.create.side_effect = claude_error("AuthenticationError")
        self.openai.responses.create.side_effect = Exception("429 insufficient_quota credit_balance_exhausted")
        with self.assertRaises(AIServiceUnavailable) as cm:
            complete("s", "x")
        self.assertEqual(cm.exception.refs, ["claude-key", "openai-credit"])
        self.assertIn("(ref: claude-key, openai-credit)", str(cm.exception))
        self.assertTrue(str(cm.exception).startswith("The AI service is temporarily unavailable"))

    def test_ordinary_errors_are_not_hidden(self):
        self.claude.messages.create.side_effect = TimeoutError("slow")
        with self.assertRaises(TimeoutError):
            complete("s", "x")
        self.openai.responses.create.assert_not_called()

    def test_platform_warning_names_the_provider(self):
        db.session.add(PlatformAdmin(email="admin@example.com", full_name="Admin", is_active=True,
                                     password_hash=bcrypt.generate_password_hash("admin-password-123456").decode()))
        task = WorkforceTask(tenant_id=self.tid, title="t", instructions="x", status="failed",
                             error_message="The AI service is temporarily unavailable. (ref: claude-credit, openai-credit)")
        db.session.add(task); db.session.commit()
        with self.client.session_transaction() as s:
            s["platform_admin_id"] = PlatformAdmin.query.first().id
        html = self.client.get("/platform/").get_data(as_text=True)
        self.assertIn("Claude (Anthropic) account has run out of credit", html)
        self.assertIn("OpenAI account has run out of credit", html)

    def test_kombian_answers_with_claude(self):
        self.claude.messages.create.return_value = claude_reply("Open **Billing** to change plan.")
        r = self.client.post("/help/ask", json={"question": "How do I change plan?", "context": "workspace"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["source"], "ai")
        self.assertEqual(self.claude.messages.create.call_args.kwargs["max_tokens"], 900)


class WorkspaceTests(ProviderTests):
    def test_unscoped_key_error_is_explained_and_workspace_header_supported(self):
        self.p1.stop()
        self.claude.messages.create.side_effect = claude_error(
            "BadRequestError", "This API key is not scoped to a workspace, so this request must include the anthropic-workspace-id header")
        self.assertEqual(ai_providers._classify("claude", self.claude.messages.create.side_effect), "claude-key")
        self.app.config["ANTHROPIC_WORKSPACE_ID"] = "wrkspc_123"
        client = ai_providers.claude_client()
        self.assertEqual(client._custom_headers.get("anthropic-workspace-id"), "wrkspc_123")
        self.p1.start()


class PreferOpenAITests(ProviderTests):
    extra = {"AI_PROVIDER": "openai"}

    def test_ai_provider_setting_puts_openai_first_and_claude_as_backup(self):
        self.openai.responses.create.side_effect = Exception("insufficient_quota")
        self.claude.messages.create.return_value = claude_reply()
        self.assertEqual(complete("s", "x")[1], "claude-sonnet-5-5")
        self.openai.responses.create.assert_called_once()


class ClaudeOnlyTests(ProviderTests):
    keys = {"ANTHROPIC_API_KEY": "sk-ant-test"}

    def test_claude_alone_is_enough(self):
        self.claude.messages.create.return_value = claude_reply()
        self.assertEqual(ai_providers.provider_order(), ["claude"])
        self.assertEqual(complete("s", "x")[0], "Claude answer")


class NoProviderTests(ProviderTests):
    keys = {}

    def test_no_keys_gives_clear_message(self):
        with self.assertRaises(AIServiceUnavailable) as cm:
            complete("s", "x")
        self.assertEqual(cm.exception.refs, ["no-provider"])


class PreflightTests(unittest.TestCase):
    def test_either_key_satisfies_production_check(self):
        base = {"ENVIRONMENT": "production"}
        self.assertTrue(any("ANTHROPIC_API_KEY" in e for e in validate_environment(base)))
        self.assertFalse(any("ANTHROPIC_API_KEY" in e for e in validate_environment({**base, "ANTHROPIC_API_KEY": "x"})))
        self.assertFalse(any("ANTHROPIC_API_KEY" in e for e in validate_environment({**base, "OPENAI_API_KEY": "x"})))


if __name__ == "__main__":
    unittest.main()
