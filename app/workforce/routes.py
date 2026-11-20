from flask import abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app.extensions import db
from app.models import WorkforceTask, AgentRun, AuditLog, TeamExecution, TeamExecutionStep, Notification
from app.security import roles_required, active_membership_required
from app.models import AIEmployee
from app.billing.services import can_create_task, can_create_visual
from app.workforce.exports import tables_in
from flask import current_app
from . import workforce_bp

@workforce_bp.post("/execute")
@roles_required("owner", "admin", "manager")
def execute():
    title = request.form.get("title", "").strip()
    instructions = request.form.get("instructions", "").strip()
    if not title or not instructions or len(instructions) > 8000:
        flash("Provide a title and assignment details (maximum 8,000 characters).", "error")
        return redirect(url_for("workspace.dashboard"))
    import re as _re
    if _re.search(r"\[[A-Za-z][^\]\n]{0,80}\](?!\()", title + "\n" + instructions):
        flash("Replace the parts in [square brackets] with your own details before sending.", "error")
        return redirect(url_for("workspace.dashboard"))
    allowed, message = can_create_task(g.active_tenant_id)
    if not allowed:
        flash(message, "error")
        return redirect(url_for("billing.index"))
    active = AIEmployee.query.filter_by(tenant_id=g.active_tenant_id, status="active").count()
    if active < 2:
        flash("Activate the Team Coordinator and at least one specialist before assigning work.", "error")
        return redirect(url_for("workspace.dashboard"))
    task = WorkforceTask(tenant_id=g.active_tenant_id, created_by_user_id=current_user.id,
                         title=title[:180], instructions=instructions, status="queued")
    db.session.add(task)
    db.session.commit()
    try:
        current_app.extensions["celery"].send_task(
            "workforce.start_team_orchestration",
            args=[task.id, g.active_tenant_id, current_user.id, task.title, task.instructions],
        )
    except Exception:
        task.status = "failed"
        task.error_message = "The background queue is unavailable. Please try again later."
        db.session.commit()
        flash("The task queue is unavailable. Check Redis and the worker service.", "error")
        return redirect(url_for("workspace.dashboard"))
    repeat = request.form.get("repeat", "none")
    if repeat in {"daily", "weekly", "monthly"}:
        from datetime import datetime, timezone
        from app.models import RecurringAssignment
        from app.workforce.recurring import MAX_PER_WORKSPACE, describe, next_run
        if RecurringAssignment.query.filter_by(tenant_id=g.active_tenant_id).count() >= MAX_PER_WORKSPACE:
            flash(f"Assignment queued, but it wasn't set to repeat: you already have {MAX_PER_WORKSPACE} repeating assignments.", "info")
            return redirect(url_for("workforce.task_detail", task_id=task.id))
        now = datetime.now(timezone.utc)
        hour = request.form.get("repeat_hour", type=int)
        r = RecurringAssignment(tenant_id=g.active_tenant_id, created_by_user_id=current_user.id, title=title[:180],
                                instructions=instructions, frequency=repeat, weekday=now.weekday(),
                                day_of_month=min(now.day, 28), hour=hour if hour is not None and 0 <= hour <= 23 else 8,
                                next_run_at=now)
        r.next_run_at = next_run(r, now)
        db.session.add(r)
        db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id, action="recurring_assignment.created",
                                target_type="recurring_assignment", target_id=title[:80]))
        db.session.commit()
        flash(f"Assignment queued. It will repeat: {describe(r).lower()} (Ghana time).", "success")
        return redirect(url_for("workforce.task_detail", task_id=task.id))
    flash("Assignment queued. You can monitor its progress in work history.", "success")
    return redirect(url_for("workforce.task_detail", task_id=task.id))

@workforce_bp.get("/tasks/<int:task_id>")
@login_required
@active_membership_required
def task_detail(task_id):
    task = WorkforceTask.query.filter_by(id=task_id, tenant_id=g.active_tenant_id).first_or_404()
    runs = AgentRun.query.filter_by(task_id=task.id, tenant_id=g.active_tenant_id).order_by(AgentRun.created_at.asc()).all()
    execution = TeamExecution.query.filter_by(task_id=task.id, tenant_id=g.active_tenant_id).first()
    steps = TeamExecutionStep.query.filter_by(team_execution_id=execution.id, tenant_id=g.active_tenant_id).order_by(TeamExecutionStep.id.asc()).all() if execution else []
    from app.models import GeneratedAsset
    assets = GeneratedAsset.query.filter_by(task_id=task.id, tenant_id=g.active_tenant_id).order_by(GeneratedAsset.id.asc()).all()
    photo_available = bool(current_app.config.get("OPENAI_API_KEY"))
    return render_template("workforce/task_detail.html", task=task, runs=runs, execution=execution, steps=steps,
                           assets=assets, photo_available=photo_available,
                           has_tables=bool(task.final_output and tables_in(task.final_output)),
                           assets_pending=any(a.status in ("queued", "running") for a in assets))


@workforce_bp.post("/tasks/<int:task_id>/cancel")
@roles_required("owner", "admin", "manager")
def cancel_task(task_id):
    """Request tenant-scoped cooperative cancellation of an assignment."""
    task = WorkforceTask.query.filter_by(id=task_id, tenant_id=g.active_tenant_id).first_or_404()
    if task.status == "queued":
        task.status = "cancelled"
        task.error_message = "Cancelled before execution started."
        from datetime import datetime, timezone
        task.completed_at = datetime.now(timezone.utc)
        db.session.add(AuditLog(
            tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
            action="workforce_task.cancelled", target_type="workforce_task", target_id=str(task.id),
        ))
        db.session.commit()
        flash("Assignment cancelled.", "success")
    elif task.status == "running":
        task.status = "cancel_requested"
        db.session.commit()
        flash("Cancellation requested. The current AI operation will finish before execution stops.", "info")
    else:
        flash("This assignment is no longer running and cannot be cancelled.", "info")
    return redirect(url_for("workforce.task_detail", task_id=task.id))


@workforce_bp.post("/tasks/<int:task_id>/review")
@roles_required("owner", "admin")
def review_team_deliverable(task_id):
    """Record an auditable human decision; this never performs external actions."""
    from datetime import datetime, timezone
    from .reliability import validate_review_decision
    task = WorkforceTask.query.filter_by(id=task_id, tenant_id=g.active_tenant_id).first_or_404()
    execution = TeamExecution.query.filter_by(task_id=task.id, tenant_id=g.active_tenant_id).first_or_404()
    decision = request.form.get("decision", "")
    note = request.form.get("review_note", "")
    try:
        decision, note = validate_review_decision(decision, note)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("workforce.task_detail", task_id=task.id))
    changed = TeamExecution.query.filter_by(
        id=execution.id, tenant_id=g.active_tenant_id, status="needs_review", reviewed_at=None
    ).update({
        "status": decision,
        "reviewed_by_user_id": current_user.id,
        "reviewed_at": datetime.now(timezone.utc),
        "review_decision": decision,
        "review_note": note,
        "updated_at": datetime.now(timezone.utc),
    }, synchronize_session=False)
    if changed != 1:
        db.session.rollback()
        abort(409, description="This deliverable has already been reviewed or is no longer awaiting review.")
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action=f"workforce_team.review_{decision}", target_type="team_execution", target_id=str(execution.id),
        details_json={"task_id": task.id, "note": note[:500]}))
    if task.created_by_user_id and task.created_by_user_id != current_user.id:
        db.session.add(Notification(tenant_id=g.active_tenant_id, user_id=task.created_by_user_id,
            title=f"AI deliverable {decision}", message=f"{task.title} was {decision} by an authorised reviewer.", category="approval"))
    db.session.commit()
    flash(f"AI deliverable {decision}. This records a review decision only; it does not execute external actions.", "success")
    return redirect(url_for("workforce.task_detail", task_id=task.id))


@workforce_bp.post("/tasks/<int:task_id>/retry-failed")
@roles_required("owner", "admin", "manager")
def retry_failed_team_steps(task_id):
    """Manually resume failed specialist work without re-running completed steps."""
    from datetime import datetime, timezone
    from .reliability import retryable_step_keys
    task = WorkforceTask.query.filter_by(id=task_id, tenant_id=g.active_tenant_id).first_or_404()
    execution = TeamExecution.query.filter_by(task_id=task.id, tenant_id=g.active_tenant_id).first_or_404()
    if execution.status != "failed" or task.status in {"cancelled", "cancel_requested"}:
        abort(409, description="Only a failed or interrupted assignment can be resumed.")
    steps = TeamExecutionStep.query.filter_by(tenant_id=g.active_tenant_id, team_execution_id=execution.id).all()
    retry_keys = retryable_step_keys(steps)
    if not retry_keys:
        flash("There are no failed specialist steps eligible for another attempt. Completed work was left unchanged.", "info")
        return redirect(url_for("workforce.task_detail", task_id=task.id))
    for step in steps:
        if step.step_key in retry_keys:
            step.status = "queued"
            step.error_message = ""
            step.completed_at = None
    execution.status = "running"
    execution.error_message = "Manual recovery requested by an authorised workspace user."
    execution.completed_at = None
    execution.recovery_count = int(execution.recovery_count or 0) + 1
    task.status = "running"
    task.error_message = ""
    task.completed_at = None
    task.final_output = ""
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="workforce_team.recovery_requested", target_type="team_execution", target_id=str(execution.id),
        details_json={"step_keys": retry_keys, "recovery_count": execution.recovery_count}))
    db.session.commit()
    try:
        current_app.extensions["celery"].send_task(
            "workforce.resume_team_orchestration", args=[g.active_tenant_id, execution.id]
        )
    except Exception:
        db.session.rollback()
        execution = TeamExecution.query.filter_by(id=execution.id, tenant_id=g.active_tenant_id).first()
        if execution:
            execution.status = "failed"
            execution.error_message = "Recovery could not be queued. Please try again when the worker queue is available."
            for step in TeamExecutionStep.query.filter_by(tenant_id=g.active_tenant_id, team_execution_id=execution.id, status="queued").all():
                step.status = "failed"
                step.error_message = "Recovery could not be queued."
                step.completed_at = datetime.now(timezone.utc)
            task.status = "failed"
            task.error_message = execution.error_message
            db.session.commit()
        flash("The queue is unavailable. The assignment remains failed and can be retried when service is restored.", "error")
        return redirect(url_for("workforce.task_detail", task_id=task.id))
    flash(f"Recovery queued for {len(retry_keys)} failed specialist step(s). Completed contributions were preserved.", "success")
    return redirect(url_for("workforce.task_detail", task_id=task.id))


# ---------------------------------------------------------------- charts, presentations, graphics
VISUAL_KINDS = {"chart", "presentation", "graphic"}


@workforce_bp.post("/tasks/<int:task_id>/visuals")
@roles_required("owner", "admin", "manager")
def create_visual(task_id):
    from app.models import GeneratedAsset
    task = WorkforceTask.query.filter_by(id=task_id, tenant_id=g.active_tenant_id).first_or_404()
    kind = request.form.get("kind", "")
    style = request.form.get("style", "design") if kind == "graphic" else ""
    brief = request.form.get("brief", "").strip()[:1000]
    if kind not in VISUAL_KINDS or style not in {"", "design", "photo"}:
        abort(400)
    back = redirect(url_for("workforce.task_detail", task_id=task.id) + "#visuals")
    if task.status != "completed" or not task.final_output:
        flash("Charts, presentations and graphics can be made once the assignment is completed.", "error")
        return back
    if style == "photo" and not current_app.config.get("OPENAI_API_KEY"):
        flash("Photo-style images need OpenAI, which isn't set up. Choose a design graphic instead.", "error")
        return back
    allowed, message = can_create_visual(g.active_tenant_id)
    if not allowed:
        flash(message, "error")
        return back
    asset = GeneratedAsset(tenant_id=g.active_tenant_id, task_id=task.id, kind=kind, style=style, brief=brief,
                           created_by_user_id=current_user.id, status="queued")
    db.session.add(asset)
    db.session.flush()
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id, action="visual.requested",
                            target_type="generated_asset", target_id=str(asset.id), details_json={"kind": kind, "style": style}))
    db.session.commit()
    try:
        current_app.extensions["celery"].send_task("visuals.generate_asset", args=[g.active_tenant_id, asset.id])
    except Exception:
        asset.status, asset.error_message = "failed", "The background queue is unavailable. Please try again later."
        db.session.commit()
        flash("The background queue is unavailable. Please try again later.", "error")
        return back
    label = {"chart": "Charts are", "presentation": "Your presentation is", "graphic": "Your graphic is"}[kind]
    flash(f"{label} being made. This usually takes under a minute; refresh this page to see it.", "success")
    return back


@workforce_bp.get("/visuals/<int:asset_id>/file")
@login_required
@active_membership_required
def visual_file(asset_id):
    from flask import Response
    from app.models import GeneratedAsset
    from app.knowledge.storage import read_file
    asset = GeneratedAsset.query.filter_by(id=asset_id, tenant_id=g.active_tenant_id, status="ready").first_or_404()
    data = read_file(asset.storage_key)
    download = request.args.get("download") == "1" or not asset.mime_type.startswith("image/")
    response = Response(data, mimetype=asset.mime_type)
    response.headers["Content-Disposition"] = ("attachment" if download else "inline") + f'; filename="{asset.filename}"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    # SVGs are sanitised already; this blocks scripts even if one slipped through.
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"
    return response


@workforce_bp.post("/visuals/<int:asset_id>/review")
@roles_required("owner", "admin")
def review_visual(asset_id):
    from datetime import datetime, timezone
    from app.models import GeneratedAsset
    asset = GeneratedAsset.query.filter_by(id=asset_id, tenant_id=g.active_tenant_id, status="ready").first_or_404()
    decision = request.form.get("decision")
    if decision not in {"approved", "rejected"}:
        abort(400)
    asset.review_status, asset.reviewed_by_user_id = decision, current_user.id
    asset.reviewed_at = datetime.now(timezone.utc)
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id, action=f"visual.{decision}",
                            target_type="generated_asset", target_id=str(asset.id)))
    db.session.commit()
    flash(f"{asset.title} {decision}. This records a decision only; nothing is published.", "success")
    return redirect(url_for("workforce.task_detail", task_id=asset.task_id) + "#visuals")


# ---------------------------------------------------------------- Word / Excel downloads
@workforce_bp.get("/tasks/<int:task_id>/download/<fmt>")
@login_required
@active_membership_required
def download_task(task_id, fmt):
    import re as _re
    from flask import Response
    from app.models import Tenant
    from app.workforce.exports import tables_in, to_docx, to_xlsx
    task = WorkforceTask.query.filter_by(id=task_id, tenant_id=g.active_tenant_id).first_or_404()
    if task.status != "completed" or not task.final_output or fmt not in {"docx", "xlsx"}:
        abort(404)
    business = db.session.get(Tenant, g.active_tenant_id).name
    name = (_re.sub(r"[^\w]+", "-", task.title.lower()).strip("-")[:60] or "assignment")
    if fmt == "docx":
        data, mime = to_docx(task, business), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        if not tables_in(task.final_output):
            abort(404)
        data, mime = to_xlsx(task, business), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id, action=f"workforce_task.downloaded_{fmt}",
                            target_type="workforce_task", target_id=str(task.id)))
    db.session.commit()
    response = Response(data, mimetype=mime)
    response.headers["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
    response.headers["Cache-Control"] = "private, no-store"
    return response


# ---------------------------------------------------------------- recurring assignments
@workforce_bp.get("/recurring")
@login_required
@active_membership_required
def recurring_list():
    from app.models import RecurringAssignment
    from app.workforce.recurring import describe
    items = RecurringAssignment.query.filter_by(tenant_id=g.active_tenant_id).order_by(RecurringAssignment.created_at.desc()).all()
    return render_template("workforce/recurring.html", items=items, describe=describe)


@workforce_bp.post("/recurring/<int:item_id>/<action>")
@roles_required("owner", "admin", "manager")
def recurring_action(item_id, action):
    from datetime import datetime, timezone
    from app.models import RecurringAssignment
    from app.workforce.recurring import next_run
    r = RecurringAssignment.query.filter_by(id=item_id, tenant_id=g.active_tenant_id).first_or_404()
    if action == "pause":
        r.active = False; message = "Paused. It won't run until you resume it."
    elif action == "resume":
        r.active = True; r.next_run_at = next_run(r, datetime.now(timezone.utc)); message = "Resumed."
    elif action == "delete":
        db.session.delete(r); message = "Repeating assignment deleted. Past results are kept."
    else:
        abort(400)
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id, action=f"recurring_assignment.{action}",
                            target_type="recurring_assignment", target_id=str(item_id)))
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("workforce.recurring_list"))
