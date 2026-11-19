"""Persistence services for durable, tenant-scoped AI team orchestration.

This module establishes the database and validation layer. Queue fan-out and
parallel specialist execution are added in a later gate after these contracts
are migrated and verified in the target PostgreSQL/Redis environment.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_

from app.extensions import db
from app.models import TeamExecution, WorkforceTask, WorkforceTaskDependency
from .dependency_graph import ready_task_ids, would_create_cycle

MAX_PARALLELISM = 4
MAX_TOKEN_BUDGET = 100_000


def create_team_execution(tenant_id, task_id, plan=None, max_parallelism=3,
                          token_budget=12_000, cost_budget_usd=None):
    """Create one durable orchestration record for a parent task."""
    if not 1 <= int(max_parallelism) <= MAX_PARALLELISM:
        raise ValueError(f"max_parallelism must be between 1 and {MAX_PARALLELISM}.")
    if not 1 <= int(token_budget) <= MAX_TOKEN_BUDGET:
        raise ValueError(f"token_budget must be between 1 and {MAX_TOKEN_BUDGET}.")

    task = WorkforceTask.query.filter_by(id=task_id, tenant_id=tenant_id).first()
    if task is None:
        raise LookupError("Parent assignment was not found in this business workspace.")
    if TeamExecution.query.filter_by(tenant_id=tenant_id, task_id=task_id).first():
        raise ValueError("An orchestration record already exists for this assignment.")

    cost_budget = None
    if cost_budget_usd is not None:
        try:
            cost_budget = Decimal(str(cost_budget_usd))
        except (InvalidOperation, TypeError):
            raise ValueError("cost_budget_usd must be a valid non-negative amount.")
        if not cost_budget.is_finite() or cost_budget < 0:
            raise ValueError("cost_budget_usd must be a valid non-negative amount.")

    execution = TeamExecution(
        tenant_id=tenant_id,
        task_id=task_id,
        status="planned",
        plan_json=plan if isinstance(plan, dict) else {},
        max_parallelism=int(max_parallelism),
        token_budget=int(token_budget),
        cost_budget_usd=cost_budget,
        cost_used_usd=Decimal("0"),
    )
    db.session.add(execution)
    db.session.commit()
    return execution


def add_task_dependency(tenant_id, task_id, depends_on_task_id):
    """Add a same-tenant prerequisite edge, rejecting duplicates and cycles."""
    if int(task_id) == int(depends_on_task_id):
        raise ValueError("An assignment cannot depend on itself.")
    task_ids = {int(task_id), int(depends_on_task_id)}
    locked_tasks = WorkforceTask.query.filter(
        WorkforceTask.tenant_id == tenant_id, WorkforceTask.id.in_(task_ids)
    ).order_by(WorkforceTask.id.asc()).with_for_update().all()
    found = {row.id for row in locked_tasks}
    if found != task_ids:
        raise LookupError("Both assignments must belong to the active business workspace.")

    edges = WorkforceTaskDependency.query.filter_by(tenant_id=tenant_id).with_entities(
        WorkforceTaskDependency.task_id, WorkforceTaskDependency.depends_on_task_id
    ).all()
    if would_create_cycle(edges, task_id, depends_on_task_id):
        raise ValueError("This dependency would create a cycle in the assignment plan.")
    if (int(task_id), int(depends_on_task_id)) in {(int(a), int(b)) for a, b in edges}:
        raise ValueError("This assignment dependency already exists.")

    edge = WorkforceTaskDependency(
        tenant_id=tenant_id, task_id=task_id, depends_on_task_id=depends_on_task_id
    )
    db.session.add(edge)
    db.session.commit()
    return edge


def get_ready_task_ids(tenant_id, candidate_ids):
    """Return candidate tasks whose prerequisites have completed successfully."""
    candidate_ids = [int(value) for value in candidate_ids]
    if not candidate_ids:
        return []
    candidates = WorkforceTask.query.filter(
        WorkforceTask.tenant_id == tenant_id,
        WorkforceTask.id.in_(candidate_ids),
    ).all()
    candidate_ids = [task.id for task in candidates if task.status in {"queued", "planned"}]
    edges = WorkforceTaskDependency.query.filter_by(tenant_id=tenant_id).with_entities(
        WorkforceTaskDependency.task_id, WorkforceTaskDependency.depends_on_task_id
    ).all()
    completed_ids = {
        task.id for task in WorkforceTask.query.filter_by(tenant_id=tenant_id, status="completed").all()
    }
    return ready_task_ids(candidate_ids, edges, completed_ids)


def start_team_execution(tenant_id, execution_id):
    """Atomically transition a planned orchestration record to running."""
    now = datetime.now(timezone.utc)
    changed = TeamExecution.query.filter_by(
        id=execution_id, tenant_id=tenant_id, status="planned"
    ).update({"status": "running", "started_at": now}, synchronize_session=False)
    if changed:
        db.session.commit()
    else:
        db.session.rollback()
    return changed == 1


def reserve_execution_usage(tenant_id, execution_id, token_count, cost_usd=0):
    """Atomically reserve token/cost usage without exceeding configured budgets."""
    try:
        token_count = int(token_count)
        cost = Decimal(str(cost_usd))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("Usage values must be valid non-negative numbers.")
    if token_count < 0 or not cost.is_finite() or cost < 0:
        raise ValueError("Usage values must be valid non-negative numbers.")

    changed = TeamExecution.query.filter(
        TeamExecution.id == execution_id,
        TeamExecution.tenant_id == tenant_id,
        TeamExecution.status == "running",
        TeamExecution.tokens_used + token_count <= TeamExecution.token_budget,
        or_(
            TeamExecution.cost_budget_usd.is_(None),
            TeamExecution.cost_used_usd + cost <= TeamExecution.cost_budget_usd,
        ),
    ).update({
        "tokens_used": TeamExecution.tokens_used + token_count,
        "cost_used_usd": TeamExecution.cost_used_usd + cost,
    }, synchronize_session=False)
    if changed:
        db.session.commit()
    else:
        db.session.rollback()
    return changed == 1


def finish_team_execution(tenant_id, execution_id, status="completed", error_message=""):
    """Close an orchestration record without allowing arbitrary status values."""
    if status not in {"completed", "failed", "cancelled", "needs_review"}:
        raise ValueError("Unsupported final orchestration status.")
    changed = TeamExecution.query.filter_by(
        id=execution_id, tenant_id=tenant_id, status="running"
    ).update({
        "status": status,
        "error_message": (error_message or "")[:500],
        "completed_at": datetime.now(timezone.utc),
    }, synchronize_session=False)
    if changed:
        db.session.commit()
    else:
        db.session.rollback()
    return changed == 1
