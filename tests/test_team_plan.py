from types import SimpleNamespace
import pytest

import importlib.util
from pathlib import Path

_module_path = Path(__file__).parents[1] / "app" / "workforce" / "team_plan.py"
_spec = importlib.util.spec_from_file_location("team_plan_under_test", _module_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
validate_team_plan = _module.validate_team_plan
ready_steps = _module.ready_steps


@pytest.fixture
def specialists():
    return [SimpleNamespace(id=11, name="Research Officer"),
            SimpleNamespace(id=12, name="Project Manager")]


def test_valid_plan_preserves_dependencies(specialists):
    plan = validate_team_plan({"steps": [
        {"employee_id": 11, "title": "Research", "instructions": "Research the market", "depends_on": []},
        {"employee_id": 12, "title": "Plan", "instructions": "Build a schedule", "depends_on": [1]},
    ]}, specialists)
    assert plan[1]["depends_on"] == ["step_1"]
    assert plan[0]["employee_name"] == "Research Officer"


def test_rejects_unknown_employee(specialists):
    with pytest.raises(ValueError, match="not active"):
        validate_team_plan({"steps": [{"employee_id": 99, "title": "X", "instructions": "Y"}]}, specialists)


def test_rejects_cycles(specialists):
    with pytest.raises(ValueError, match="cycle"):
        validate_team_plan({"steps": [
            {"employee_id": 11, "title": "A", "instructions": "A", "depends_on": [2]},
            {"employee_id": 12, "title": "B", "instructions": "B", "depends_on": [1]},
        ]}, specialists)


def test_ready_steps_only_releases_satisfied_dependencies():
    steps = [
        SimpleNamespace(step_key="step_1", status="completed", depends_on_json=[]),
        SimpleNamespace(step_key="step_2", status="queued", depends_on_json=["step_1"]),
        SimpleNamespace(step_key="step_3", status="queued", depends_on_json=["step_2"]),
    ]
    assert ready_steps(steps) == ["step_2"]
