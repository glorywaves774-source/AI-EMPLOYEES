# AI Workforce — Gate 2A Change Log

## Scope
Continue from Milestone 12; implement the first safe Stage 4 task execution control increment without adding database tables.

## Changes
- Added tenant-scoped cancellation endpoint for queued/running workforce tasks.
- Added cooperative cancellation checkpoints before specialist work, before coordinator synthesis, and after coordinator model response.
- Added cancellation finalisation and audit events.
- Added atomic task claim/completion transitions to prevent duplicate worker delivery and completion/cancellation races.
- Added cancellation control and status messaging to the task detail page.
- Added Celery 9-minute soft and 10-minute hard task limits; soft timeout becomes a recorded failed task and is not automatically retried.
- Added tests for queued, running, worker-finalised and cross-tenant cancellation paths.

## Validation
- Python `compileall`: passed.
- Python AST parse: passed for all source files.
- Added `pytest.ini` with `pythonpath = .` so test collection resolves the project package when invoked from the repository root.
- `pytest -q`: collection now reaches application imports but is blocked because Flask is not installed in this environment.
- PostgreSQL/Redis/Celery integration: not run.

## Remaining limitations
- Milestone 12 migration baseline remains metadata-driven and must be replaced with a reviewed explicit baseline before schema evolution.
- Parallel execution, dependencies, budgets, structured validation and full workflow progress are not implemented in this increment.
