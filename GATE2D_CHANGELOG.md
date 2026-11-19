# Gate 2D Change Log — Workflow Reliability & Human Review

## Added

- Migration `0004_review_recovery_controls` adds reviewer identity, decision, timestamp, decision note and recovery counter fields to team executions.
- Tenant-scoped human review for consolidated AI deliverables. Only workspace owners and administrators can approve or reject; rejection requires a reason.
- Review decisions are conditionally updated to prevent duplicate decisions and are written to the audit log. The requester receives a notification when another authorised reviewer decides.
- The Approvals Centre now lists AI deliverables awaiting review and links to their specialist evidence and consolidated output.
- Bounded manual recovery for failed/blocked specialist steps. Completed specialist work is preserved; no more than three total attempts per step are allowed.
- Recovery request and review decision audit events.
- Pure policy tests for review decisions and retry eligibility.

## Safety boundaries

- Human review records a decision about the AI deliverable only. It does not execute a payment, send an email, publish content, change company records, or authorise an external integration.
- Rejected deliverables remain available with their decision note for audit; no destructive deletion occurs.
- Recovery is manual and limited to failed/blocked steps. It is not automatic Redis outage recovery, a distributed lease system, or guaranteed replay after a worker is killed before Celery records its chord result.
- Review is restricted to owner/admin roles. Existing task cancellation and tenant scoping remain in place.

## Validation

- Focused tests: **12 passed** (`test_team_reliability.py`, `test_migration_contract.py`, `test_team_plan.py`, `test_dependency_graph.py`).
- SQLite migration contract applies revisions 0001 through 0004, inspects review fields and reviewer foreign key, then downgrades through 0004 to 0001: passed.
- Python compilation: passed.
- Full Flask test suite, PostgreSQL, Redis/Celery, OpenAI API, and Render deployment: not verified in this environment.

## Deployment

Back up the database, rehearse all outstanding migrations against PostgreSQL staging, then apply `0004_review_recovery_controls` after `0003_team_execution_steps`. Deploy web and worker code together. Test approval/rejection with owner/admin accounts, verify employee/manager access is denied for review, test tenant isolation, and exercise manual recovery using a deliberately failed specialist step before production rollout.
