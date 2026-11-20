"""Video studio: social media editor (real ffmpeg, AI mocked), AI video generation, allowances, packs."""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from app import create_app
from app.extensions import db
from app.models import Payment, SubscriptionPlan, TenantSubscription, VideoCredit, VideoOutput, VideoProject
from app.video import media, service

FF = media.ffmpeg()


def make_test_video(path, seconds=20, size="640x360"):
    subprocess.run([FF, "-hide_banner", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=25:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)], check=True, capture_output=True)


SEGMENTS = [{"start": 0.5, "end": 4.0, "text": "Welcome to Kayron Global Tech Services in Saboba"},
            {"start": 4.0, "end": 9.0, "text": "Today we show you how AI employees help small businesses grow"},
            {"start": 9.0, "end": 15.0, "text": "Plans start from four hundred and fifty cedis a month"}]
CLIPS = [{"start": 0.5, "end": 9.0, "title": "AI employees for small businesses", "post_text": "Meet your AI team.\n\n#AI #Ghana"},
         {"start": 9.0, "end": 15.0, "title": "Plans from GHS 450", "post_text": "Affordable plans.\n\n#Business"}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()
        self.files = tempfile.mkdtemp()
        files = self.files

        class C:
            SECRET_KEY = "test-secret-key-that-is-long-enough"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.tmp.name
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            WTF_CSRF_ENABLED = False; RATELIMIT_ENABLED = False
            CELERY_BROKER_URL = "memory://"; CELERY_RESULT_BACKEND = "cache+memory://"
            RATELIMIT_STORAGE_URI = "memory://"; PUBLIC_BASE_URL = "https://app.example.test"
            STORAGE_BACKEND = "local"; PRIVATE_UPLOAD_ROOT = files
            GEMINI_API_KEY = "test-gemini"; PAYSTACK_SECRET_KEY = "sk_test"
        self.app = create_app(C); self.client = self.app.test_client()
        from flask import g as _g
        def _fresh():
            for k in ("_login_user", "active_tenant_id", "active_tenant", "membership"):
                _g.pop(k, None)
        self.app.before_request_funcs.setdefault(None, []).insert(1, _fresh)
        with self.app.app_context():
            db.create_all()
        self.client.post("/auth/register", data={"full_name": "Ama", "email": "o@example.com", "business_name": "Ama Media",
                                                 "password": "a-very-strong-password-123", "accept_terms": "yes"})
        self.ctx = self.app.app_context(); self.ctx.push()
        self.tid = TenantSubscription.query.first().tenant_id
        self.send = mock.patch.object(self.app.extensions["celery"], "send_task"); self.sent = self.send.start()

    def tearDown(self):
        self.send.stop(); db.session.remove(); self.ctx.pop()
        with self.app.app_context():
            db.drop_all()
        os.unlink(self.tmp.name); shutil.rmtree(self.files, ignore_errors=True)

    def set_plan(self, code, status="active"):
        self.client.get("/billing/")  # makes sure default plans exist
        plan = SubscriptionPlan.query.filter_by(code=code).first()
        sub = TenantSubscription.query.first()
        sub.plan_id, sub.status = plan.id, status
        db.session.commit()

    def upload(self, path, **form):
        with open(path, "rb") as fh:
            return self.client.post("/video/edit", data={"video": (fh, "talk.mp4"), "platforms": ["vertical", "youtube"],
                                                         "clips": "2", "max_seconds": "15", "captions": "yes", **form},
                                    content_type="multipart/form-data")


class EditorTests(Base):
    def test_upload_transcribe_plan_render_captions_and_cleanup(self):
        src = os.path.join(self.files, "talk.mp4"); make_test_video(src)
        r = self.upload(src, title="Launch talk", brief="the business benefits")
        self.assertEqual(r.status_code, 302)
        p = VideoProject.query.one()
        self.assertEqual(self.sent.call_args.args[0], "video.run_project")
        with mock.patch("app.video.ai.transcribe", return_value=SEGMENTS) as tr, \
                mock.patch("app.video.ai.plan_clips", return_value=(CLIPS, 100, 50)) as pl:
            result = service.run_project(self.tid, p.id)
        self.assertEqual(result["status"], "ready", VideoProject.query.one().error_message)
        args = pl.call_args.args
        self.assertEqual(args[3:6], (2, 15, ["vertical", "youtube"]))
        outs = VideoOutput.query.order_by(VideoOutput.id).all()
        self.assertEqual(len(outs), 4)  # 2 clips x 2 formats
        # check real dimensions of rendered files
        from app.video import storage
        for o in outs:
            dest = os.path.join(self.files, f"o{o.id}.mp4"); storage.get_path(o.storage_key, dest)
            dur, has_v, has_a, w, h = media.probe(dest)
            self.assertTrue(has_v and has_a)
            self.assertEqual((w, h), (720, 1280) if o.platform == "vertical" else (1280, 720))
            self.assertAlmostEqual(dur, o.duration_seconds, delta=0.6)
        self.assertIn("#AI", outs[0].post_text)
        p = VideoProject.query.one()
        self.assertIsNone(p.source_key, "original upload deleted after processing")
        page = self.client.get(f"/video/{p.id}").get_data(as_text=True)
        self.assertIn("AI employees for small businesses", page); self.assertIn("Download MP4", page)
        f = self.client.get(f"/video/file/{outs[0].id}")
        self.assertEqual(f.status_code, 200); self.assertEqual(f.mimetype, "video/mp4")
        self.assertGreater(len(f.data), 10_000)

    def test_captions_file_is_valid(self):
        path = os.path.join(self.files, "c.ass")
        media.write_captions(SEGMENTS + [{"start": 2, "end": 3, "text": "Bad {\\an8} tags"}], 0.5, 9.0, path, 720, 1280)
        text = open(path).read()
        self.assertIn("Dialogue:", text); self.assertIn("Welcome to Kayron", text)
        self.assertNotIn("{\\an8}", text)
        self.assertNotIn("four hundred", text, "only lines inside the clip")

    def test_large_upload_allowed_beyond_app_limit(self):
        big = os.path.join(self.files, "big.mp4")
        with open(big, "wb") as fh:
            fh.write(os.urandom(14 * 1024 * 1024))
        self.assertEqual(self.upload(big).status_code, 302)
        self.assertEqual(VideoProject.query.count(), 1)
        # not a real video: the job fails with a clear message, and isn't counted
        service.run_project(self.tid, VideoProject.query.one().id)
        self.assertIn("MP4", VideoProject.query.one().error_message)
        self.assertEqual(service.used_this_period(self.tid, "edit"), 0)

    def test_rejects_non_video_extension_and_trial_limit(self):
        txt = os.path.join(self.files, "x.txt"); open(txt, "w").write("x" * 2000)
        with open(txt, "rb") as fh:
            self.client.post("/video/edit", data={"video": (fh, "notes.txt")}, content_type="multipart/form-data")
        self.assertEqual(VideoProject.query.count(), 0)
        src = os.path.join(self.files, "t.mp4"); make_test_video(src, seconds=3)
        self.upload(src); self.upload(src)  # trial includes 1 edit
        self.assertEqual(VideoProject.query.count(), 1)

    def test_no_speech_makes_one_clip_without_captions(self):
        src = os.path.join(self.files, "talk.mp4"); make_test_video(src, seconds=6)
        self.upload(src)
        with mock.patch("app.video.ai.transcribe", return_value=[]):
            self.assertEqual(service.run_project(self.tid, VideoProject.query.one().id)["status"], "ready")
        self.assertEqual(VideoOutput.query.count(), 2)

    def test_ai_outage_reported_and_not_counted(self):
        from app.ai_providers import AIServiceUnavailable
        src = os.path.join(self.files, "talk.mp4"); make_test_video(src, seconds=5)
        self.upload(src)
        with mock.patch("app.video.ai.transcribe", side_effect=AIServiceUnavailable("The AI service is temporarily unavailable. (ref: transcription)")):
            service.run_project(self.tid, VideoProject.query.one().id)
        self.assertIn("temporarily unavailable", VideoProject.query.one().error_message)
        self.assertEqual(service.used_this_period(self.tid, "edit"), 0)


class GenerateTests(Base):
    def gen(self, idea="Sunrise over Accra market"):
        return self.client.post("/video/generate", data={"idea": idea, "aspect": "9:16"})

    def test_not_on_trial_or_starter(self):
        self.gen(); self.assertEqual(VideoProject.query.count(), 0)
        self.set_plan("starter"); self.gen(); self.assertEqual(VideoProject.query.count(), 0)

    def test_growth_generates_and_counts(self):
        self.set_plan("growth")
        self.gen()
        p = VideoProject.query.one()
        def fake_generate(prompt, aspect, dest):
            make_test_video(dest, seconds=8, size="720x1280")
        with mock.patch("app.video.ai.video_prompt", return_value=("Market sunrise", "A calm sunrise...", 50, 30)), \
                mock.patch("app.video.ai.generate_video", side_effect=fake_generate) as gv:
            self.assertEqual(service.run_project(self.tid, p.id)["status"], "ready")
        self.assertEqual(gv.call_args.args[1], "9:16")
        out = VideoOutput.query.one()
        self.assertEqual(out.platform, "generated"); self.assertAlmostEqual(out.duration_seconds, 8, delta=0.5)
        self.assertEqual(service.allowance_summary(self.tid)["generate"], {"allowed": 20, "used": 1})

    def test_allowance_then_pack(self):
        self.set_plan("growth")
        for _ in range(20):
            db.session.add(VideoProject(tenant_id=self.tid, mode="generate", status="ready", options_json={}))
        db.session.commit()
        self.gen(); self.assertEqual(VideoProject.query.count(), 20)
        db.session.add(VideoCredit(tenant_id=self.tid, clips=10)); db.session.commit()
        self.gen()
        self.assertTrue(VideoProject.query.order_by(VideoProject.id.desc()).first().uses_pack)
        self.assertEqual(service.pack_balance(self.tid), 9)

    def test_pack_purchase_via_paystack(self):
        self.set_plan("growth")
        self.assertIn("Extra AI video clips", self.client.get("/billing/").get_data(as_text=True))
        with mock.patch("app.billing.services._http_json", return_value={"status": True, "data": {"authorization_url": "https://checkout.paystack.com/v"}}) as http:
            r = self.client.post("/billing/video-pack")
        self.assertEqual(r.headers["Location"], "https://checkout.paystack.com/v")
        self.assertEqual(http.call_args.args[2]["amount"], "30000")
        pay = Payment.query.one()
        ok = {"status": "success", "reference": pay.provider_reference, "amount": 30000, "currency": "GHS"}
        with mock.patch("app.billing.services._http_json", return_value={"status": True, "data": ok}):
            self.client.get(f"/billing/paystack/callback?reference={pay.provider_reference}")
        self.assertEqual(service.pack_balance(self.tid), 10)
        sub = TenantSubscription.query.first()
        self.assertEqual(sub.plan.code, "growth", "a pack must not change the plan")

    def test_safety_refusal_is_explained(self):
        self.set_plan("business")
        self.gen()
        with mock.patch("app.video.ai.video_prompt", return_value=("t", "p", 1, 1)), \
                mock.patch("app.video.ai.generate_video", side_effect=ValueError("The video service declined this idea for safety reasons. Try describing it differently.")):
            service.run_project(self.tid, VideoProject.query.one().id)
        self.assertIn("safety", VideoProject.query.one().error_message)


class ParsingTests(unittest.TestCase):
    def test_find_video_in_interaction_response(self):
        from app.video.ai import _find_video
        resp = {"id": "x", "status": "completed", "steps": [{"type": "thought"}, {"type": "model_output", "content": [
            {"type": "text", "text": "hi"}, {"type": "video", "mime_type": "video/mp4", "data": "AAAA"}]}]}
        self.assertEqual(_find_video(resp)["data"], "AAAA")
        self.assertIsNone(_find_video({"steps": []}))


if __name__ == "__main__":
    unittest.main()


class PlanningTests(Base):
    def test_plan_clips_validates_ai_output(self):
        from app.video.ai import plan_clips
        reply = ('{"clips": [{"start": 1, "end": 9, "title": "Good one", "caption": "Watch this", "hashtags": ["AI", "#Ghana!"]},'
                 '{"start": 5, "end": 12, "title": "Overlaps", "caption": "x", "hashtags": []},'
                 '{"start": 20, "end": 200, "title": "Too long", "caption": "y", "hashtags": []},'
                 '{"start": "bad", "end": 3}]}')
        with mock.patch("app.ai_providers.complete", return_value=(reply, "m", 10, 5)) as ai:
            clips, _, _ = plan_clips(SEGMENTS, 100.0, "benefits", 3, 30, ["vertical"])
        self.assertEqual([c["title"] for c in clips], ["Good one", "Too long"])
        self.assertEqual(clips[1]["end"], 50.0, "capped at max length")
        self.assertTrue(clips[0]["post_text"].endswith("#AI #Ghana"))
        self.assertIn("TikTok", ai.call_args.args[0])

    def test_clean_segments(self):
        from app.video.ai import _clean_segments
        out = _clean_segments([{"start": 5, "end": 7, "text": "b"}, {"start": 1, "end": 2, "text": "a"},
                               {"start": 3, "end": 2, "text": "bad"}, {"start": "x"}, {"start": 1, "end": 3, "text": ""}], 6)
        self.assertEqual([s["text"] for s in out], ["a", "b"]); self.assertEqual(out[1]["end"], 6)
