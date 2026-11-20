"""Video studio pages: upload-and-edit for social media, AI video generation, results."""
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import AuditLog, VideoOutput, VideoProject
from app.security import active_membership_required, roles_required
from app.video import service

video_bp = Blueprint("video", __name__, url_prefix="/video")
ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp"}


def _audit(action, target_id, details=None):
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id, action=action,
                            target_type="video_project", target_id=str(target_id), details_json=details or {}))


def _queue(project):
    try:
        current_app.extensions["celery"].send_task("video.run_project", args=[project.tenant_id, project.id])
        return True
    except Exception:
        current_app.logger.exception("Could not queue video project")
        project.status, project.error_message = "failed", "The background queue is unavailable. Please try again later."
        db.session.commit()
        return False


@video_bp.get("/")
@login_required
@active_membership_required
def index():
    from app.video.ai import gemini_configured
    projects = (VideoProject.query.filter_by(tenant_id=g.active_tenant_id)
                .order_by(VideoProject.created_at.desc()).limit(30).all())
    return render_template("video/index.html", projects=projects, allowance=service.allowance_summary(g.active_tenant_id),
                           generation_ready=gemini_configured(), aspects=service.ASPECTS,
                           max_mb=int(current_app.config.get("VIDEO_MAX_UPLOAD_MB") or 200),
                           max_minutes=int(current_app.config.get("VIDEO_MAX_MINUTES") or 15))


@video_bp.post("/edit")
@roles_required("owner", "admin", "manager")
def create_edit():
    max_mb = int(current_app.config.get("VIDEO_MAX_UPLOAD_MB") or 200)
    request.max_content_length = max_mb * 1024 * 1024  # larger than the app-wide limit, for this upload only
    ok, message, _pack = service.can_start(g.active_tenant_id, "edit")
    if not ok:
        flash(message, "error")
        return redirect(url_for("video.index"))
    upload = request.files.get("video")
    if not upload or not upload.filename:
        flash("Choose a video file to upload.", "error")
        return redirect(url_for("video.index"))
    ext = Path(upload.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        flash("Upload a video file (MP4, MOV, WebM, MKV, AVI or 3GP).", "error")
        return redirect(url_for("video.index"))
    platforms = [p for p in request.form.getlist("platforms") if p in {"vertical", "youtube"}] or ["vertical"]
    options = {"platforms": platforms, "clips": max(1, min(5, request.form.get("clips", 3, type=int) or 3)),
               "max_seconds": request.form.get("max_seconds", 45, type=int) if request.form.get("max_seconds", type=int) in {15, 30, 45, 60, 90} else 45,
               "captions": request.form.get("captions") == "yes"}
    key = uuid.uuid4().hex
    with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
        upload.save(tmp.name)
        size = Path(tmp.name).stat().st_size
        if size < 1024:
            flash("That file is empty or too small to be a video.", "error")
            return redirect(url_for("video.index"))
        from app.video import storage
        storage.put_path(key, tmp.name, content_type=upload.mimetype or "video/mp4")
    title = (request.form.get("title", "").strip() or Path(upload.filename).stem)[:180]
    project = VideoProject(tenant_id=g.active_tenant_id, created_by_user_id=current_user.id, mode="edit", title=title,
                           brief=request.form.get("brief", "").strip()[:2000], options_json=options, source_key=key,
                           source_filename=re.sub(r"[^\w\-. ]", "", upload.filename)[:200], source_bytes=size)
    db.session.add(project)
    db.session.flush()
    _audit("video.edit_requested", project.id, {"bytes": size, **options})
    db.session.commit()
    if _queue(project):
        flash("Uploaded. Your clips are being made; this usually takes a few minutes. We'll email you when they're ready.", "success")
    return redirect(url_for("video.project", project_id=project.id))


@video_bp.post("/generate")
@roles_required("owner", "admin", "manager")
def create_generate():
    from app.video.ai import gemini_configured
    idea = request.form.get("idea", "").strip()[:2000]
    aspect = request.form.get("aspect", "9:16")
    if not idea or aspect not in service.ASPECTS:
        flash("Describe the video you want.", "error")
        return redirect(url_for("video.index"))
    if not gemini_configured():
        flash("AI video generation isn't switched on yet. Kayron needs to add the Google video key.", "error")
        return redirect(url_for("video.index"))
    ok, message, uses_pack = service.can_start(g.active_tenant_id, "generate")
    if not ok:
        flash(message, "error")
        return redirect(url_for("video.index"))
    project = VideoProject(tenant_id=g.active_tenant_id, created_by_user_id=current_user.id, mode="generate",
                           title=request.form.get("title", "").strip()[:180], brief=idea,
                           options_json={"aspect": aspect}, uses_pack=uses_pack)
    db.session.add(project)
    db.session.flush()
    _audit("video.generate_requested", project.id, {"aspect": aspect, "uses_pack": uses_pack})
    db.session.commit()
    if _queue(project):
        flash("Your video is being created. This usually takes 1–5 minutes.", "success")
    return redirect(url_for("video.project", project_id=project.id))


@video_bp.get("/<int:project_id>")
@login_required
@active_membership_required
def project(project_id):
    p = VideoProject.query.filter_by(id=project_id, tenant_id=g.active_tenant_id).first_or_404()
    outputs = VideoOutput.query.filter_by(project_id=p.id, tenant_id=g.active_tenant_id).order_by(VideoOutput.id).all()
    return render_template("video/project.html", p=p, outputs=outputs, labels=service.PLATFORM_LABEL)


@video_bp.get("/file/<int:output_id>")
@login_required
@active_membership_required
def file(output_id):
    from app.video import storage
    out = VideoOutput.query.filter_by(id=output_id, tenant_id=g.active_tenant_id).first_or_404()
    chunks, size = storage.open_stream(out.storage_key)
    name = (re.sub(r"[^\w]+", "-", out.title.lower()).strip("-")[:50] or "video") + f"-{out.platform}.mp4"
    resp = Response(chunks, mimetype="video/mp4", direct_passthrough=True)
    if size:
        resp.headers["Content-Length"] = str(size)
    disposition = "attachment" if request.args.get("download") == "1" else "inline"
    resp.headers["Content-Disposition"] = f'{disposition}; filename="{name}"'
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@video_bp.post("/output/<int:output_id>/review")
@roles_required("owner", "admin")
def review(output_id):
    out = VideoOutput.query.filter_by(id=output_id, tenant_id=g.active_tenant_id).first_or_404()
    decision = request.form.get("decision")
    if decision not in {"approved", "rejected"}:
        abort(400)
    out.review_status, out.reviewed_by_user_id, out.reviewed_at = decision, current_user.id, datetime.now(timezone.utc)
    _audit(f"video.{decision}", out.project_id, {"output_id": out.id})
    db.session.commit()
    flash(f"Video {decision}. This records a decision only; nothing is posted.", "success")
    return redirect(url_for("video.project", project_id=out.project_id) + f"#out-{out.id}")
