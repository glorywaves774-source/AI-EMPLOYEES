# Gate 2C Change Log — AI Team Orchestration

## Added

- `0003_team_execution_steps` migration and `TeamExecutionStep` durable specialist-step model.
- Strict Team Coordinator plan validation for active tenant employees, bounded step count/instructions, dependency references, and cycle detection.
- Queue-backed coordinator planning and bounded Celery chord waves for independent specialist steps.
- Sequential dependency release, prerequisite output sharing, authorised knowledge context, specialist retries, cancellation checks, and coordinator consolidation.
- Token budget reservations and optional estimated USD cost reservations using configured model-specific input/output rates.
- Task detail page plan/progress display, per-step status/output, and execution budget usage.
- Tests for plan validation and migration 0003 upgrade/downgrade contract.

## Changed

- New assignments enqueue `workforce.start_team_orchestration` instead of the legacy serial assignment task.
- Existing `workforce.execute_assignment` remains registered for messages already queued before deployment.
- README and migration/orchestration documentation now describe Gate 2C and the current migration chain.

## Validation

- Focused tests: **9 passed** (`test_team_plan.py`, `test_dependency_graph.py`, `test_migration_contract.py`).
- Python compilation: passed.
- AST parse: passed for 47 Python files.
- Full test suite: collection blocked because Flask is not installed in the build environment (`ModuleNotFoundError: flask`).
- PostgreSQL, Redis broker/result backend, Celery chord execution, OpenAI API, and Render deployment: not tested here.

## Deployment warning

Back up and rehearse migrations on PostgreSQL staging before production. Apply `0003_team_execution_steps` after the database is at `0002_team_orchestration`. Verify Redis is configured as both Celery broker and result backend; chords require the result backend. Install the complete `requirements.txt`, then run a real multi-specialist test assignment in staging before enabling this path for production users.
