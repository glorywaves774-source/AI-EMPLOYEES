# Gate 2D — Workflow Reliability & Human Review

## Human review workflow

1. The Team Coordinator may finish an assignment with `needs_review` when it identifies a high-impact decision, unresolved contradiction, uncertainty, or incomplete specialist work.
2. The Approvals Centre lists those deliverables. Opening one shows the original brief, consolidated output, specialist plan, individual contributions, errors and usage.
3. Workspace owners and administrators can approve or reject the AI deliverable. Rejection requires a reason; an optional note can accompany approval.
4. The decision is written once using a conditional update, with reviewer, timestamp, decision and note persisted on the team execution. The audit log records the decision and a notification is sent to the requester when another person reviews it.
5. A second decision attempt receives a conflict response; it cannot silently overwrite the first decision.

This is a human review of generated work, not an external-action approval. An approved deliverable does not send an email, make a payment, publish content, change a record or invoke an integration. Those actions require a separate, explicitly authorised execution service with action-specific permission and parameter checks.

## Bounded manual recovery

A workspace owner, administrator or manager can request recovery for an assignment whose team execution is `failed`. The service selects only failed or blocked specialist steps below the three-total-attempt ceiling. It returns those steps to the queue, preserves completed specialist results, records the actor and step keys in the audit log, and enqueues `workforce.resume_team_orchestration`. The existing dependency scheduler releases work only when prerequisites are complete.

If the queue submission fails, the assignment remains marked failed and can be retried after the queue is restored. Completed work is not reset. Planning failures with no persisted specialist steps are not eligible for this recovery action.

## Migration

Revision chain:

```text
0001_initial
  └── 0002_team_orchestration
        └── 0003_team_execution_steps
              └── 0004_review_recovery_controls
```

For an existing installation already at `0003_team_execution_steps`, back up the database and apply the new revision with the normal Flask-Migrate command. Verify Alembic reports `0004_review_recovery_controls`. New installations apply the full chain. Never edit already-deployed revisions.

## Permissions and tenant boundaries

- Review decisions are restricted to `owner` and `admin`.
- Manual failed-step recovery is restricted to `owner`, `admin` and `manager`.
- Every task and execution lookup is scoped to the active tenant.
- Review state updates require `needs_review` and `reviewed_at IS NULL`, preventing repeat decisions.
- Recovery does not reset completed steps and is bounded by a total step-attempt limit.

## Known limitations

This gate does not add automatic Redis outage recovery, workflow leases, a dead-letter queue, Celery chord-result repair, provider cost reconciliation, or an external-action execution engine. A worker killed at the wrong point can still require operational intervention. Live PostgreSQL, Redis/Celery, OpenAI and Render tests remain required.

## Staging checklist

- Verify a fresh database can apply all migrations and an existing database at revision 0003 can apply 0004.
- Verify owner/admin can approve and reject; manager/employee cannot review.
- Verify rejection requires a note and repeat decisions are rejected.
- Verify requester notifications and audit events are written.
- Verify one tenant cannot view or review another tenant's execution.
- Verify a failed specialist can be retried and a completed specialist is not re-run.
- Verify recovery fails safely when Redis is unavailable.
- Verify review approval does not trigger any external action.
