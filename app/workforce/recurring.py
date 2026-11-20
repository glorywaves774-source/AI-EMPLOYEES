"""Recurring assignments: the hourly job starts any that are due."""
import calendar
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.extensions import db
from app.models import AIEmployee, AuditLog, RecurringAssignment, WorkforceTask

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_PER_WORKSPACE = 10


def _as_utc(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def next_run(r, after):
    """First scheduled time strictly after `after`."""
    after = _as_utc(after)
    base = after.replace(minute=0, second=0, microsecond=0)
    if r.frequency == "daily":
        candidate = base.replace(hour=r.hour)
        return candidate if candidate > after else candidate + timedelta(days=1)
    if r.frequency == "weekly":
        candidate = base.replace(hour=r.hour) + timedelta(days=(r.weekday - base.weekday()) % 7)
        return candidate if candidate > after else candidate + timedelta(days=7)
    day = max(1, min(28, r.day_of_month))
    candidate = base.replace(day=day, hour=r.hour)
    if candidate > after:
        return candidate
    year, month = (base.year + 1, 1) if base.month == 12 else (base.year, base.month + 1)
    return candidate.replace(year=year, month=month, day=min(day, calendar.monthrange(year, month)[1]))


def describe(r):
    at = f"{r.hour:02d}:00"
    if r.frequency == "daily":
        return f"Every day at {at}"
    if r.frequency == "weekly":
        return f"Every {WEEKDAYS[r.weekday]} at {at}"
    return f"Every month on day {r.day_of_month} at {at}"


def run_due(now=None):
    """Start every due, active recurring assignment. Returns (started, skipped)."""
    from app.billing.services import can_create_task
    now = _as_utc(now or datetime.now(timezone.utc))
    started = skipped = 0
    due = (RecurringAssignment.query.filter(RecurringAssignment.active.is_(True),
                                            RecurringAssignment.next_run_at <= now)
           .order_by(RecurringAssignment.next_run_at.asc()).limit(500).all())
    for r in due:
        r.next_run_at = next_run(r, now)  # always move on, so a problem never repeats every hour
        r.last_run_at = now
        allowed, message = can_create_task(r.tenant_id)
        active = AIEmployee.query.filter_by(tenant_id=r.tenant_id, status="active").count()
        if not allowed or active < 2:
            r.last_error = (message or "Activate the Team Coordinator and at least one specialist.")[:300]
            skipped += 1
            db.session.commit()
            continue
        task = WorkforceTask(tenant_id=r.tenant_id, created_by_user_id=r.created_by_user_id,
                             title=f"{r.title} ({now:%d %b %Y})"[:180], instructions=r.instructions, status="queued")
        db.session.add(task)
        db.session.flush()
        db.session.add(AuditLog(tenant_id=r.tenant_id, actor_user_id=None, action="recurring_assignment.started",
                                target_type="workforce_task", target_id=str(task.id), details_json={"recurring_id": r.id}))
        r.last_task_id, r.last_error = task.id, ""
        db.session.commit()
        try:
            current_app.extensions["celery"].send_task(
                "workforce.start_team_orchestration",
                args=[task.id, r.tenant_id, r.created_by_user_id, task.title, task.instructions])
            started += 1
        except Exception:
            current_app.logger.exception("Could not queue recurring assignment %s", r.id)
            task.status, task.error_message = "failed", "The background queue was unavailable at the scheduled time."
            r.last_error = "The background queue was unavailable at the scheduled time."
            db.session.commit()
            skipped += 1
    return started, skipped
