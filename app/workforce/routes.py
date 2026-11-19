from flask import abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app.extensions import db
from app.models import WorkforceTask, AgentRun, AuditLog, TeamExecution, TeamExecutionStep, Notification
from app.security import roles_required, active_membership_required
from app.models import AIEmployee
from app.billing.services import can_create_task
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
    return render_template("workforce/task_detail.html", task=task, runs=runs, execution=execution, steps=steps)


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
