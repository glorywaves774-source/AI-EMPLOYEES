"""Video studio jobs, allowances and add-on packs."""
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models import TenantSubscription, User, VideoCredit, VideoOutput, VideoProject

PLATFORM_LABEL = {"vertical": "TikTok · Reels · Shorts", "youtube": "YouTube", "generated": "AI-generated clip"}
ASPECTS = {"9:16": "Upright (TikTok, Reels, Shorts)", "16:9": "Wide (YouTube, websites)"}


def _cfg(name, default):
    value = current_app.config.get(name)
    return default if value in (None, "") else value


# ---------------------------------------------------------------- allowances
def _sub(tenant_id):
    return TenantSubscription.query.filter_by(tenant_id=tenant_id).first()


def _plan_key(sub):
    if sub is None:
        return None
    if sub.status == "trialing":
        return "TRIAL"
    return (sub.plan.code if sub.plan else "starter").upper()


EDIT_DEFAULTS = {"TRIAL": 1, "STARTER": 5, "GROWTH": 30, "BUSINESS": 150}
CLIP_DEFAULTS = {"TRIAL": 0, "STARTER": 0, "GROWTH": 20, "BUSINESS": 100}


def plan_allowance(sub, mode):
    key = _plan_key(sub)
    if key is None:
        return 0
    if mode == "edit":
        return int(_cfg(f"VIDEO_EDITS_{key}", EDIT_DEFAULTS.get(key, 0)))
    return int(_cfg(f"VIDEO_CLIPS_{key}", CLIP_DEFAULTS.get(key, 0)))


def _period(sub):
    from app.billing.services import as_utc
    start = as_utc(sub.current_period_start) if sub and sub.current_period_start else None
    end = as_utc(sub.current_period_end) if sub and sub.current_period_end else None
    return start, end


def used_this_period(tenant_id, mode):
    sub = _sub(tenant_id)
    q = VideoProject.query.filter(VideoProject.tenant_id == tenant_id, VideoProject.mode == mode,
                                  VideoProject.status != "failed", VideoProject.uses_pack.is_(False))
    start, end = _period(sub)
    if start:
        q = q.filter(VideoProject.created_at >= start)
    if end:
        q = q.filter(VideoProject.created_at < end)
    return q.count()


def pack_balance(tenant_id):
    bought = db.session.query(db.func.coalesce(db.func.sum(VideoCredit.clips), 0)).filter(
        VideoCredit.tenant_id == tenant_id).scalar() or 0
    spent = VideoProject.query.filter(VideoProject.tenant_id == tenant_id, VideoProject.uses_pack.is_(True),
                                      VideoProject.status != "failed").count()
    return max(0, int(bought) - spent)


def allowance_summary(tenant_id):
    sub = _sub(tenant_id)
    return {mode: {"allowed": plan_allowance(sub, mode), "used": used_this_period(tenant_id, mode)}
            for mode in ("edit", "generate")} | {"pack": pack_balance(tenant_id),
                                                  "plan": _plan_key(sub) or "", "status": sub.status if sub else ""}


def can_start(tenant_id, mode):
    """(allowed, message, uses_pack)"""
    sub = _sub(tenant_id)
    if not sub or sub.status not in {"trialing", "active"}:
        return False, "Your subscription is not active. Choose a plan to continue.", False
    allowed, used = plan_allowance(sub, mode), used_this_period(tenant_id, mode)
    if used < allowed:
        return True, "", False
    if mode == "generate":
        if sub.status == "active" and _plan_key(sub) in {"GROWTH", "BUSINESS"} and pack_balance(tenant_id) > 0:
            return True, "", True
        if _plan_key(sub) in {"TRIAL", "STARTER"}:
            return False, "AI video generation is included in the Growth and Business plans.", False
        return False, ("You've used this month's AI video clips. Buy an extra pack on the Billing page, "
                       "or wait for your next billing period."), False
    return False, (f"You've used this period's {allowed} video edit{'s' if allowed != 1 else ''}. "
                   "Upgrade your plan for more."), False


# ---------------------------------------------------------------- jobs
def _set(project, **fields):
    for k, v in fields.items():
        setattr(project, k, v)
    db.session.commit()


def _new_key():
    return uuid.uuid4().hex


def _save_output(project, path, platform, title, post_text="", start=0.0, duration=0.0):
    from app.video import storage
    key = _new_key()
    storage.put_path(key, path)
    out = VideoOutput(tenant_id=project.tenant_id, project_id=project.id, platform=platform, title=title[:200],
                      post_text=post_text, start_seconds=start, duration_seconds=duration, storage_key=key,
                      size_bytes=Path(path).stat().st_size)
    db.session.add(out)
    db.session.commit()
    return out


def _is_trial(tenant_id):
    sub = _sub(tenant_id)
    return bool(sub and sub.status == "trialing")


def _notify(project, ok):
    from app.security_service import notify_by_email
    user = db.session.get(User, project.created_by_user_id) if project.created_by_user_id else None
    if not user:
        return
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    link = f"{base}/video/{project.id}"
    if ok:
        notify_by_email(user.email, f"Your videos are ready: {project.title}",
                        f"Hello {user.full_name or ''},\n\nYour videos for \"{project.title}\" are ready to review "
                        f"and download:\n{link}\n\n— AI Workforce by Kayron Global Tech Services")
    else:
        notify_by_email(user.email, f"Video couldn't be finished: {project.title}",
                        f"Hello {user.full_name or ''},\n\nWe couldn't finish \"{project.title}\".\n"
                        f"Reason: {project.error_message}\n\n{link}\n\n— AI Workforce by Kayron Global Tech Services")


def run_project(tenant_id, project_id):
    """Worker entry point. Records expected failures on the project instead of raising."""
    from app.ai_providers import AIServiceUnavailable
    project = VideoProject.query.filter_by(id=project_id, tenant_id=tenant_id, status="queued").first()
    if not project:
        return {"status": "skipped"}
    _set(project, status="running", progress="Starting…")
    workdir = Path(tempfile.mkdtemp(prefix="aw-video-"))
    try:
        if project.mode == "edit":
            _run_edit(project, workdir)
        else:
            _run_generate(project, workdir)
        _set(project, status="ready", progress="Done", completed_at=datetime.now(timezone.utc))
        _notify(project, True)
        return {"status": "ready", "project_id": project.id}
    except (AIServiceUnavailable, ValueError) as exc:
        message = str(exc)
    except Exception as exc:
        current_app.logger.exception("Video project %s failed", project_id)
        message = "Something went wrong while making this video. Please try again."
        if "Video processing failed" in str(exc):
            message = "This video file couldn't be processed. Try exporting it as MP4 (H.264) and uploading again."
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    db.session.rollback()
    project = db.session.get(VideoProject, project_id)
    _set(project, status="failed", error_message=message[:500], progress="", completed_at=datetime.now(timezone.utc))
    _notify(project, False)
    return {"status": "failed", "project_id": project_id}


def _run_edit(project, workdir):
    from app.video import media, storage
    from app.video.ai import plan_clips, transcribe
    opts = project.options_json or {}
    platforms = [p for p in opts.get("platforms", ["vertical"]) if p in media.FORMATS] or ["vertical"]
    n_clips = max(1, min(5, int(opts.get("clips", 3))))
    max_len = max(15, min(90, int(opts.get("max_seconds", 45))))
    captions = bool(opts.get("captions", True))

    src = workdir / "source"
    _set(project, progress="Getting your video ready…")
    storage.get_path(project.source_key, src)
    duration, has_video, has_audio, _w, _h = media.probe(src)
    if not has_video or duration <= 0:
        raise ValueError("This file doesn't look like a video we can read. Please upload an MP4 or MOV file.")
    limit = int(_cfg("VIDEO_MAX_MINUTES", 15)) * 60
    if duration > limit + 5:
        raise ValueError(f"Videos can be up to {limit // 60} minutes long. Please trim it and upload again.")
    project.duration_seconds = duration
    db.session.commit()

    segments = []
    if has_audio:
        _set(project, progress="Listening to what's said…")
        audio = workdir / "audio.mp3"
        media.extract_audio(src, audio)
        segments = transcribe(audio, duration)

    if segments:
        _set(project, progress="Choosing the best moments…")
        clips, _tin, _tout = plan_clips(segments, duration, project.brief, n_clips, max_len, platforms,
                                        trial=_is_trial(project.tenant_id))
    else:
        clips = []
    if not clips:  # no speech: take the opening as one clip
        clips = [{"start": 0.0, "end": min(duration, float(max_len)), "title": project.title or "Clip", "post_text": ""}]
        captions = False

    total = len(clips) * len(platforms)
    done = 0
    for i, clip in enumerate(clips, start=1):
        for fmt in platforms:
            done += 1
            _set(project, progress=f"Making video {done} of {total}…")
            out = workdir / f"clip{i}-{fmt}.mp4"
            cap = None
            if captions:
                w, h = media.FORMATS[fmt][:2]
                cap = workdir / f"clip{i}-{fmt}.ass"
                media.write_captions(segments, clip["start"], clip["end"], cap, w, h)
            media.render_clip(src, out, clip["start"], clip["end"], fmt, cap)
            _save_output(project, out, fmt, clip["title"], clip["post_text"], clip["start"], clip["end"] - clip["start"])
    # The original upload is no longer needed once the clips are made.
    storage.delete(project.source_key)
    project.source_key = None
    db.session.commit()


def _run_generate(project, workdir):
    from app.video import media
    from app.video.ai import generate_video, video_prompt
    aspect = (project.options_json or {}).get("aspect", "9:16")
    _set(project, progress="Planning the scene…")
    title, prompt, _tin, _tout = video_prompt(project.brief, aspect, trial=_is_trial(project.tenant_id))
    project.title = project.title or title
    opts = dict(project.options_json or {})
    opts["prompt"] = prompt
    project.options_json = opts
    _set(project, progress="Creating the video (this can take a few minutes)…")
    out = workdir / "generated.mp4"
    generate_video(prompt, aspect, out)
    duration = media.probe(out)[0]
    _save_output(project, out, "generated", title, "", 0.0, duration)


def add_pack(payment):
    clips = int((payment.metadata_json or {}).get("clips") or _cfg("VIDEO_PACK_CLIPS", 10))
    db.session.add(VideoCredit(tenant_id=payment.tenant_id, clips=clips, payment_id=payment.id))
