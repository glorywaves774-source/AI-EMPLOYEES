# Gate 2C — AI Team Orchestration

## What this increment adds

Gate 2C wires the Gate 2B team-execution foundation into the live assignment queue. It keeps the existing Flask application and tenant model; complex assignments are not run inside the web request.

- The web route now queues `workforce.start_team_orchestration`.
- The Team Coordinator creates a bounded JSON plan using only active specialist employees in the current tenant.
- Plans are validated before dispatch: employee IDs must be active and tenant-local, step count is capped at eight, instruction length is bounded, dependencies must reference valid steps, and cycles are rejected.
- Each specialist step is persisted in `team_execution_steps` before queue dispatch.
- Independent steps are dispatched as a Celery chord, bounded by the configured maximum parallelism. A chord callback advances the next dependency wave.
- Dependent specialists receive the completed outputs of their prerequisite steps as shared reference context.
- Specialist outputs, model usage, failures, attempts, and progress are recorded. Transient specialist exceptions are retried up to two times; budget exhaustion is not retried. The task detail page shows the plan, status, token usage, and contribution output.
- The coordinator consolidates completed contributions and must identify incomplete/failed work. A structured review decision sets the execution to `needs_review` when human review is indicated or specialist work remains outstanding.
- Cancellation is checked between specialist operations. A worker that fails to persist a result is treated as an incomplete step when its chord callback advances.
- The existing single-agent task worker remains registered so already-queued messages from an earlier deployment can still be consumed.

## New migration

Revision chain:

```text
0001_initial
    └── 0002_team_orchestration
          └── 0003_team_execution_steps
```

`0003_team_execution_steps` adds the durable specialist-step table and the composite `(tenant_id, id)` key on `team_executions` used by the tenant-scoped foreign key. The migration has an explicit downgrade. It must be rehearsed against a current PostgreSQL staging backup before production.

For an installation already at `0002_team_orchestration`, apply the new revision with the normal migration command and confirm Alembic reports `0003_team_execution_steps`.

## Configuration

```dotenv
TEAM_EXECUTION_TOKEN_BUDGET=12000
TEAM_EXECUTION_MAX_PARALLELISM=3
TEAM_EXECUTION_COST_BUDGET_USD=
ESTIMATED_INPUT_USD_PER_MILLION=0
ESTIMATED_OUTPUT_USD_PER_MILLION=0
```

Parallelism is clamped to 1–4. Token usage is reserved atomically against the tenant execution record after each model response. If a cost budget is configured, non-zero model-specific input and output estimates must also be configured; the workflow then reserves estimated cost from those rates. These are estimates, not a provider invoice reconciliation. Model usage is known only after the provider responds, so a request may already have incurred provider usage before an over-budget result is rejected. Configure conservative limits and monitor provider billing.

## Reliability and safety boundaries

- Celery chords require a functioning result backend as well as a broker. This project configures Redis for both; production Redis availability and chord behavior must be verified in staging.
- The planner has a conservative fallback: if its plan cannot be validated, the existing transparent specialist selector delegates a small set of active specialists without inventing employee identities.
- Specialist agents still have no external tools or permission to send messages, execute payments, publish content, or modify external systems.
- Shared context consists of completed prerequisite contributions plus authorised knowledge retrieval for the assigned employee. It is reference data, not trusted instructions.
- A `needs_review` status is an escalation marker; it is not an approval workflow or a claim that a human has reviewed the output.
- This gate does not yet provide automatic recovery of a Redis outage, distributed workflow leases, provider cost reconciliation, or a full human approval UI.

## Validation performed

- Pure team-plan tests cover valid dependency mapping, inactive/unknown employee rejection, cycle rejection, and readiness selection.
- SQLite Alembic contract test applies the frozen baseline and revisions 0002 and 0003, checks the new table and composite tenant foreign key, then downgrades 0003 and 0002.
- Python compilation and AST parsing are run on the changed source.
- Full Flask startup, PostgreSQL, Redis, Celery chord execution, OpenAI API calls, and Render deployment are not validated in this build environment because Flask/Celery runtime dependencies and live service credentials are unavailable. Do not treat source-level validation as a live integration test.
