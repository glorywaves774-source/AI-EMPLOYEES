"""Charts, presentations and graphics made from finished assignments (AI mocked)."""
import io
import json
import os
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest import mock

from cryptography.fernet import Fernet

from app import create_app
from app.extensions import db
from app.models import GeneratedAsset, TenantSubscription, WorkforceTask
from app.workforce import visuals
from app.workforce.visuals import build_pptx, render_chart_png, sanitize_svg

PNG = b"\\x89PNG"[:0] + b"\x89PNG"

CHART = {"title": "Monthly budget (GHS)", "type": "bar", "unit": "GHS",
         "labels": ["Ads", "Events", "Content"], "series": [{"name": "Month 1", "values": [1200, 800, "450"]}]}


class UnitTests(unittest.TestCase):
    def test_charts_render_as_png(self):
        for kind in ("bar", "line", "pie"):
            spec = visuals._clean_chart({**CHART, "type": kind})
            self.assertTrue(render_chart_png(spec).startswith(PNG), kind)

    def test_multi_series_and_bad_values(self):
        spec = visuals._clean_chart({"title": "T", "type": "line", "labels": ["Jan", "Feb"],
                                     "series": [{"name": "A", "values": [1, "x"]}, {"name": "B", "values": [3, 4]}]})
        self.assertEqual(spec["series"][0]["values"], [1.0, 0.0])
        with self.assertRaises(ValueError):
            visuals._clean_chart({"title": "T", "labels": ["only one"], "series": [{"values": [1]}]})

    def test_presentation_builds_valid_pptx_with_notes_and_chart(self):
        deck = visuals._clean_deck({"title": "Launch plan", "subtitle": "Q1", "slides": [
            {"title": "Why now", "bullets": ["SMEs need help", "Low cost"], "notes": "Say this."},
            {"title": "Budget", "bullets": ["GHS 2,450 a month"], "notes": "", "chart": CHART}]})
        data = build_pptx(deck, "Kayron")
        from pptx import Presentation
        prs = Presentation(io.BytesIO(data))
        self.assertEqual(len(prs.slides), 3)
        self.assertEqual(prs.slides[1].notes_slide.notes_text_frame.text, "Say this.")
        self.assertTrue(any(sh.shape_type == 13 for sh in prs.slides[2].shapes), "chart picture on slide")
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))

    def test_svg_sanitiser_removes_anything_active(self):
        dirty = ('Here you go: <svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" onload="alert(1)">'
                 '<script>alert(1)</script><foreignObject><div>x</div></foreignObject>'
                 '<a href="https://evil.example"><rect width="10" height="10"/></a>'
                 '<rect width="100" height="50" fill="url(#g)" style="fill:url(https://evil.example/x)"/>'
                 '<image href="https://evil.example/i.png"/><use href="https://evil.example#x"/>'
                 '<text x="5" y="30" font-size="20" onclick="x()">Hello</text></svg> thanks')
        out = sanitize_svg(dirty).decode()
        for bad in ("script", "onload", "onclick", "foreignObject", "evil.example", "<a", "<image"):
            self.assertNotIn(bad, out)
        self.assertIn("Hello", out); self.assertIn('fill="url(#g)"', out); self.assertIn("viewBox", out)

    def test_svg_with_entities_rejected(self):
        with self.assertRaises(ValueError):
            sanitize_svg('<!DOCTYPE svg [<!ENTITY a "x">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>')
        with self.assertRaises(ValueError):
            sanitize_svg("no graphic here")


class Base(unittest.TestCase):
    extra = {"OPENAI_API_KEY": "sk-test"}

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()
        self.files = tempfile.mkdtemp()
        extra, files = self.extra, self.files

        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False; RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"; PUBLIC_BASE_URL = "http://localhost"
            STORAGE_BACKEND = "local"; PRIVATE_UPLOAD_ROOT = files
            FILE_ENCRYPTION_KEY = Fernet.generate_key().decode()
            ANTHROPIC_API_KEY = "sk-ant-test"; OPENAI_API_KEY = None
            TRIAL_DAILY_VISUAL_LIMIT = 5
        for k, v in extra.items():
            setattr(C, k, v)
        self.app = create_app(C); self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
        self.client.post("/auth/register", data={"full_name": "Owner", "email": "o@example.com",
            "business_name": "Example Ltd", "password": "a-very-strong-password-123"})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.tid = TenantSubscription.query.first().tenant_id
        self.task = WorkforceTask(tenant_id=self.tid, title="Launch plan", instructions="x", status="completed",
                                  final_output="Ads GHS 1,200; Events GHS 800; Content GHS 450 per month.")
        db.session.add(self.task); db.session.commit()
        self.send = mock.patch.object(self.app.extensions["celery"], "send_task"); self.sent = self.send.start()

    def tearDown(self):
        self.send.stop(); db.session.remove(); self.ctx.pop()
        with self.app.app_context():
            db.drop_all()
        os.unlink(self.tmp.name)

    def ai(self, payload):
        return mock.patch("app.ai_providers.complete", return_value=(json.dumps(payload), "claude-haiku-5-5", 100, 50))

    def request(self, kind, **form):
        return self.client.post(f"/workforce/tasks/{self.task.id}/visuals", data={"kind": kind, **form})

    def run_last(self):
        asset = GeneratedAsset.query.order_by(GeneratedAsset.id.desc()).first()
        return visuals.generate_asset(self.tid, asset.id), asset.id


class FlowTests(Base):
    def test_chart_request_makes_one_asset_per_chart(self):
        r = self.request("chart", brief="costs")
        self.assertEqual(r.status_code, 302)
        self.sent.assert_called_once()
        with self.ai({"charts": [CHART, {**CHART, "type": "pie", "title": "Share"}]}):
            result, _ = self.run_last()
        self.assertEqual(result["status"], "ready")
        assets = GeneratedAsset.query.filter_by(task_id=self.task.id, status="ready").all()
        self.assertEqual(len(assets), 2)
        f = self.client.get(f"/workforce/visuals/{assets[0].id}/file")
        self.assertEqual(f.status_code, 200); self.assertTrue(f.data.startswith(PNG))
        self.assertIn("inline", f.headers["Content-Disposition"])
        self.assertIn("sandbox", f.headers["Content-Security-Policy"])
        page = self.client.get(f"/workforce/tasks/{self.task.id}").get_data(as_text=True)
        self.assertIn("Monthly budget (GHS)", page); self.assertIn("Download PNG", page)
        # stored encrypted, not as a plain PNG
        stored = open(os.path.join(self.files, assets[0].storage_key + ".enc"), "rb").read()
        self.assertFalse(stored.startswith(PNG))

    def test_presentation_download(self):
        self.request("presentation")
        with self.ai({"title": "Launch", "subtitle": "", "slides": [{"title": "One", "bullets": ["a", "b"], "notes": "n"}]}):
            self.assertEqual(self.run_last()[0]["status"], "ready")
        asset = GeneratedAsset.query.filter_by(kind="presentation").one()
        f = self.client.get(f"/workforce/visuals/{asset.id}/file")
        self.assertIn("attachment", f.headers["Content-Disposition"]); self.assertTrue(f.data.startswith(b"PK"))

    def test_design_graphic_is_sanitised_svg(self):
        self.request("graphic", style="design", brief="Instagram post")
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1080"><script>x</script><text x="1" y="2">Launch</text></svg>'
        with self.ai({"title": "Launch post", "svg": svg}):
            self.assertEqual(self.run_last()[0]["status"], "ready")
        asset = GeneratedAsset.query.filter_by(kind="graphic").one()
        body = self.client.get(f"/workforce/visuals/{asset.id}/file").data.decode()
        self.assertIn("Launch", body); self.assertNotIn("script", body)

    def test_photo_graphic_uses_openai_images(self):
        self.request("graphic", style="photo")
        img = SimpleNamespace(data=[SimpleNamespace(b64_json=__import__("base64").b64encode(PNG + b"data").decode())])
        client = mock.Mock(); client.images.generate.return_value = img
        with self.ai({"title": "Office", "prompt": "A modern office"}), \
                mock.patch("app.ai_providers.openai_client", return_value=client):
            self.assertEqual(self.run_last()[0]["status"], "ready")
        self.assertEqual(client.images.generate.call_args.kwargs["model"], "gpt-image-2.5-flare")

    def test_no_figures_gives_helpful_failure(self):
        self.request("chart")
        with self.ai({"charts": []}):
            self.assertEqual(self.run_last()[0]["status"], "failed")
        self.assertIn("no figures", GeneratedAsset.query.one().error_message)

    def test_ai_outage_is_reported_plainly(self):
        from app.ai_providers import AIServiceUnavailable
        self.request("presentation")
        with mock.patch("app.ai_providers.complete", side_effect=AIServiceUnavailable(
                "The AI service is temporarily unavailable. (ref: claude-credit)", ["claude-credit"])):
            self.run_last()
        self.assertIn("temporarily unavailable", GeneratedAsset.query.one().error_message)

    def test_review_records_decision(self):
        self.request("chart")
        with self.ai({"charts": [CHART]}):
            _, aid = self.run_last()
        self.client.post(f"/workforce/visuals/{aid}/review", data={"decision": "approved"})
        self.assertEqual(db.session.get(GeneratedAsset, aid).review_status, "approved")


class GuardTests(Base):
    extra = {"OPENAI_API_KEY": None}

    def test_only_completed_assignments(self):
        self.task.status = "running"; db.session.commit()
        self.request("chart")
        self.assertEqual(GeneratedAsset.query.count(), 0)

    def test_photo_needs_openai(self):
        self.request("graphic", style="photo")
        self.assertEqual(GeneratedAsset.query.count(), 0)
        page = self.client.get(f"/workforce/tasks/{self.task.id}").get_data(as_text=True)
        self.assertIn("needs OpenAI", page)

    def test_trial_daily_limit(self):
        for _ in range(5):
            self.request("chart")
        self.request("chart")
        self.assertEqual(GeneratedAsset.query.count(), 5)

    def test_bad_kind_rejected(self):
        self.assertEqual(self.request("video").status_code, 400)

    def test_other_workspace_cannot_open_file(self):
        asset = GeneratedAsset(tenant_id=999, task_id=self.task.id, kind="chart", status="ready",
                               storage_key="a" * 32, mime_type="image/png", filename="x.png")
        db.session.add(asset); db.session.commit()
        self.assertEqual(self.client.get(f"/workforce/visuals/{asset.id}/file").status_code, 404)


if __name__ == "__main__":
    unittest.main()
