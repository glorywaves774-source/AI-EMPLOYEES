from datetime import datetime, timezone
from celery.exceptions import SoftTimeLimitExceeded
from app.extensions import db
from app.models import WorkforceTask, AuditLog, Notification
from app.ai_engine import AIServiceUnavailable, execute_coordinated_task
from app.billing.services import process_subscription_expirations


def register_tasks(celery):
    @celery.task(bind=True, name="workforce.execute_assignment", autoretry_for=(Exception,), dont_autoretry_for=(AIServiceUnavailable,),
                 retry_backoff=True, retry_jitter=True, retry_kwargs={"max_retries": 2})
    def execute_assignment(self, task_id, tenant_id, user_id, title, instructions):
        task = WorkforceTask.query.filter_by(id=task_id, tenant_id=tenant_id).first()
        if task is None:
            return {"status": "missing", "task_id": task_id}
        if task.status in {"cancelled", "cancel_requested"}:
            if task.status == "cancel_requested":
                task.status = "cancelled"
                task.error_message = "Cancelled before execution started."
                task.completed_at = datetime.now(timezone.utc)
                db.session.add(AuditLog(
                    tenant_id=tenant_id, actor_user_id=user_id,
                    action="workforce_task.cancelled", target_type="workforce_task", target_id=str(task.id),
                ))
                db.session.commit()
            return {"status": task.status, "task_id": task.id}
        try:
            completed = execute_coordinated_task(
                tenant_id, user_id, title, instructions, existing_task_id=task_id
            )
            if completed.status != "completed":
                return {"status": completed.status, "task_id": completed.id}
            if completed.created_by_user_id:
                db.session.add(Notification(
                    tenant_id=tenant_id,
                    user_id=completed.created_by_user_id,
                    title="AI assignment completed",
                    message=f"{completed.title} is ready for review.",
                    category="task",
                ))
                db.session.commit()
            return {"status": completed.status, "task_id": completed.id}
        except SoftTimeLimitExceeded:
            db.session.rollback()
            task = WorkforceTask.query.filter_by(id=task_id, tenant_id=tenant_id).first()
            if task:
                task.status = "failed"
                task.error_message = "Assignment exceeded the maximum execution time (9 minutes)."
                task.completed_at = datetime.now(timezone.utc)
                db.session.add(AuditLog(
                    tenant_id=tenant_id, actor_user_id=user_id,
                    action="workforce_task.timed_out", target_type="workforce_task", target_id=str(task.id),
                ))
                db.session.commit()
            return {"status": "failed", "task_id": task_id, "reason": "timeout"}
        except Exception as exc:
            db.session.rollback()
            task = WorkforceTask.query.filter_by(id=task_id, tenant_id=tenant_id).first()
            if task:
                task.status = ("queued" if self.request.retries < self.max_retries
                               and not isinstance(exc, AIServiceUnavailable) else "failed")
                task.error_message = str(exc)[:500]
                if task.status == "failed":
                    task.completed_at = datetime.now(timezone.utc)
                    db.session.add(AuditLog(
                        tenant_id=tenant_id, actor_user_id=user_id,
                        action="workforce_task.failed", target_type="workforce_task",
                        target_id=str(task.id),
                    ))
                db.session.commit()
            raise
    @celery.task(name="workforce.start_team_orchestration")
    def start_team_orchestration(task_id, tenant_id, user_id, title, instructions):
        from app.workforce.team_execution import create_team_plan, dispatch_ready_wave
        try:
            execution_id = create_team_plan(tenant_id, task_id, user_id)
            if execution_id is None:
                return {"status": "cancelled_or_missing", "task_id": task_id}
            return dispatch_ready_wave(celery, tenant_id, execution_id)
        except Exception as exc:
            db.session.rollback()
            task = WorkforceTask.query.filter_by(id=task_id, tenant_id=tenant_id).first()
            if task:
                task.status = "failed"
                task.error_message = str(exc)[:500]
                task.completed_at = datetime.now(timezone.utc)
                db.session.add(AuditLog(tenant_id=tenant_id, actor_user_id=user_id,
                    action="workforce_team.planning_failed", target_type="workforce_task",
                    target_id=str(task_id), details_json={"error": str(exc)[:250]}))
                db.session.commit()
            return {"status": "failed", "task_id": task_id, "reason": "planning_failed"}

    @celery.task(bind=True, name="workforce.execute_team_step", max_retries=2)
    def execute_team_step(self, tenant_id, execution_id, step_key):
        from app.workforce.team_execution import execute_step
        try:
            return execute_step(tenant_id, execution_id, step_key)
        except Exception as exc:
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc, countdown=min(2 ** self.request.retries, 30))
            return {"status": "failed", "step_key": step_key, "error": str(exc)[:200]}

    @celery.task(name="workforce.advance_team_execution")
    def advance_team_execution(_wave_results, tenant_id, execution_id):
        from app.workforce.team_execution import dispatch_ready_wave, mark_orphaned_wave_steps_failed
        mark_orphaned_wave_steps_failed(tenant_id, execution_id)
        return dispatch_ready_wave(celery, tenant_id, execution_id)

    @celery.task(name="workforce.resume_team_orchestration")
    def resume_team_orchestration(tenant_id, execution_id):
        from app.workforce.team_execution import dispatch_ready_wave
        return dispatch_ready_wave(celery, tenant_id, execution_id)

    @celery.task(name="billing.process_subscription_expirations")
    def billing_expiry_task():
        return {"expired": process_subscription_expirations()}

    @celery.task(name="ops.ping")
    def ops_ping():
        """No-side-effect worker probe used by post-deployment smoke checks."""
        return {"status": "ok", "service": "ai-workforce-worker"}

    return execute_assignment

