# Gate 2B — Frozen Migration Baseline & Team Orchestration Foundation

## Scope

Gate 2B continues from Milestone 12 and Gate 2A. It does not replace the Flask application or change the existing tenant, authentication, billing, knowledge, or task modules.

This increment establishes the database foundation for Stage 4 team orchestration:

- Replaces the metadata-driven `0001_initial` upgrade with a fixed, explicit snapshot of the 28 tables present in the Gate 2A codebase.
- Adds `team_executions`, one durable coordinator-level execution record per parent assignment.
- Adds `workforce_task_dependencies`, a directed prerequisite graph between assignments.
- Adds a composite unique key on `(tenant_id, id)` for workforce tasks and composite foreign keys from orchestration records. This prevents a dependency edge or execution record from referencing a task in a different tenant.
- Adds cycle detection, readiness evaluation, atomic execution start, atomic token/cost budget reservation, and final-state helpers.

## Migration behavior

Revision chain:

```text
0001_initial
    └── 0002_team_orchestration
          └── 0003_team_execution_steps (Gate 2C)
```

`0001_initial` is now a frozen schema snapshot. It contains no application imports and does not call `metadata.create_all()`. Future model changes must be represented by new revision files; never edit a revision that has already been deployed.

`0002_team_orchestration` adds the two orchestration tables and the composite task key. Its upgrade and downgrade operations were exercised against an in-memory SQLite database. PostgreSQL deployment still requires a staging migration rehearsal with a current database backup.

### Existing installation already stamped at 0001

1. Take and verify a PostgreSQL backup.
2. Deploy the Gate 2B source package.
3. Run `flask --app run.py db upgrade` once.
4. Confirm `flask db current` reports `0002_team_orchestration` and confirm both new tables exist.
5. Verify tenant task records and existing task history remain intact.

An installation already stamped at `0001_initial` will not rerun the changed `0001` file. It will apply only the new `0002` revision.

### New database

Run the normal deployment migration command. Alembic applies the frozen `0001_initial` snapshot followed by `0002_team_orchestration`.

Do not run `db.create_all()` in production and do not manually stamp a database to skip migrations. If the migration history is missing or inconsistent, stop and reconcile it against a verified backup before proceeding.

## Orchestration contracts

### Team execution

`team_executions` stores:

- Tenant and parent task identity.
- Status (`planned`, `running`, `completed`, `failed`, `cancelled`, `needs_review`).
- A JSON execution plan.
- Maximum parallelism (1–4).
- Token budget and consumed tokens.
- Optional USD cost budget and consumed cost.
- Start/completion timestamps and bounded error text.

A unique `(tenant_id, task_id)` constraint prevents duplicate coordinator execution records for the same parent assignment.

### Task dependencies

`workforce_task_dependencies` stores edges where `task_id` is the dependent assignment and `depends_on_task_id` is its prerequisite. The schema prevents self-dependencies and duplicate edges. Both composite foreign keys include `tenant_id`, so the database itself rejects cross-tenant dependency references.

The service rejects transitive cycles before writing an edge. It locks both involved task rows in deterministic ID order while validating and writing the edge. A cycle would make the execution plan impossible to schedule.

### Budget reservation

`reserve_execution_usage()` performs one conditional database update. A reservation succeeds only while the execution is running and both configured budgets remain within limits. Competing worker reservations cannot each independently consume the same remaining budget.

The caller must provide a defensible cost estimate from the selected model's actual pricing configuration. This increment does not invent model prices or claim that provider charges are reconciled.

## Important implementation boundary

Gate 2B established only the persistence foundation. Gate 2C adds the queue-backed specialist workflow and migration `0003_team_execution_steps`; see `docs/GATE2C_TEAM_ORCHESTRATION.md` for its behavior and validation limits. PostgreSQL migration and Redis/Celery chord integration still require staging verification.

## Validation performed

- Python compilation and AST parsing.
- Four pure dependency graph tests.
- The Gate 2B SQLite Alembic contract test applied `0001_initial` and `0002_team_orchestration`; Gate 2C extends the contract test through `0003_team_execution_steps`.
- PostgreSQL, Flask application startup, Redis/Celery worker execution, and live Render deployment were not run in this environment.
