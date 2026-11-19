"""SQLite contract tests for the frozen baseline and Gate 2B migration."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).parents[1]


def _load_revision(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_baseline_and_orchestration_migration_upgrade_and_downgrade():
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    context = MigrationContext.configure(connection)
    baseline = _load_revision("baseline_under_test", "migrations/versions/0001_initial_baseline.py")
    gate2b = _load_revision("gate2b_under_test", "migrations/versions/0002_team_orchestration.py")
    gate2c = _load_revision("gate2c_under_test", "migrations/versions/0003_team_execution_steps.py")
    gate2d = _load_revision("gate2d_under_test", "migrations/versions/0004_review_recovery_controls.py")

    with Operations.context(context):
        baseline.upgrade()
        gate2b.upgrade()
        gate2c.upgrade()
        gate2d.upgrade()

    inspector = inspect(connection)
    assert "team_executions" in inspector.get_table_names()
    assert "workforce_task_dependencies" in inspector.get_table_names()
    assert "team_execution_steps" in inspector.get_table_names()
    team_columns = {column["name"] for column in inspector.get_columns("team_executions")}
    assert {"reviewed_by_user_id", "reviewed_at", "review_decision", "review_note", "recovery_count"}.issubset(team_columns)
    review_fks = inspector.get_foreign_keys("team_executions")
    assert any(item["referred_table"] == "users" and item["constrained_columns"] == ["reviewed_by_user_id"] for item in review_fks)
    assert any(item["name"] == "uq_team_execution_tenant_id" for item in inspector.get_unique_constraints("team_executions"))
    step_fks = inspector.get_foreign_keys("team_execution_steps")
    assert any(item["referred_table"] == "team_executions" and item["referred_columns"] == ["tenant_id", "id"] for item in step_fks)
    task_uniques = inspector.get_unique_constraints("workforce_tasks")
    assert any(item["name"] == "uq_workforce_task_tenant_id" for item in task_uniques)
    dep_fks = inspector.get_foreign_keys("workforce_task_dependencies")
    assert len(dep_fks) == 2
    assert all(item["referred_columns"] == ["tenant_id", "id"] for item in dep_fks)

    with Operations.context(context):
        gate2d.downgrade()
        gate2c.downgrade()
        gate2b.downgrade()
    remaining = set(inspect(connection).get_table_names())
    assert "team_executions" not in remaining
    assert "workforce_task_dependencies" not in remaining
    assert "team_execution_steps" not in remaining
    assert not any(item["name"] == "uq_workforce_task_tenant_id"
                   for item in inspect(connection).get_unique_constraints("workforce_tasks"))
    connection.close()
