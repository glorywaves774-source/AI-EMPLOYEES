# AI Workforce — Gate 2B Change Log

## Scope
Continue from Milestone 12 + Gate 2A. Freeze the historical database baseline and introduce the persistence and validation foundation for Stage 4 team orchestration.

## Changes
- Replaced the metadata-driven `0001_initial` migration with an explicit fixed snapshot of the original 28-table Milestone 12 schema.
- Added migration `0002_team_orchestration`.
- Added `TeamExecution` for durable coordinator execution state, JSON plan, bounded parallelism, token budget, optional cost budget, usage totals and lifecycle timestamps.
- Added `WorkforceTaskDependency` with same-tenant composite foreign keys, duplicate-edge prevention and self-dependency prevention.
- Added a composite `(tenant_id, id)` unique key on workforce tasks to support tenant-safe composite references.
- Added pure cycle detection and ready-task evaluation helpers.
- Added orchestration persistence services for creating execution records, adding dependencies, starting executions, reserving usage atomically and finalising execution state.
- Added SQLite/Alembic migration contract tests and dependency graph tests.
- Updated migration and rollout documentation.

## Validation
- Focused tests: 5 passed (`test_dependency_graph.py`, `test_migration_contract.py`).
- Python compileall: passed.
- Python AST parsing: passed for 48 Python files.
- SQLAlchemy model metadata creation with all 30 tables: passed using an isolated metadata validation harness.
- Alembic upgrade/downgrade of 0001 + 0002 against SQLite: passed; new tables and composite foreign keys were inspected.
- Full Flask application test suite: not completed because Flask is not installed in the execution environment; the full-suite command timed out during collection/execution.
- PostgreSQL, Redis/Celery worker, OpenAI API, and live Render deployment: not run.

## Not yet implemented
- Celery group/chord fan-out and parallel specialist execution.
- Automatic task-plan generation by the Team Coordinator.
- Runtime orchestration progress UI and human escalation workflow.
- Provider-priced token/cost reconciliation.

These are explicitly deferred to Gate 2C. The existing Gate 2A task execution path remains the live assignment path.
