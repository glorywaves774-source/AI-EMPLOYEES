from types import SimpleNamespace
import importlib.util
from pathlib import Path
import pytest

path = Path(__file__).parents[1] / "app" / "workforce" / "reliability.py"
spec = importlib.util.spec_from_file_location("team_reliability_under_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
validate_review_decision = module.validate_review_decision
retryable_step_keys = module.retryable_step_keys


def test_review_decision_requires_reason_for_rejection():
    assert validate_review_decision("approved", "Looks good") == ("approved", "Looks good")
    with pytest.raises(ValueError, match="reason is required"):
        validate_review_decision("rejected", "  ")


def test_review_decision_rejects_unknown_status_and_long_note():
    with pytest.raises(ValueError):
        validate_review_decision("published", "")
    with pytest.raises(ValueError, match="1,000"):
        validate_review_decision("approved", "x" * 1001)


def test_recovery_only_retries_failed_or_blocked_steps_below_attempt_limit():
    steps = [
        SimpleNamespace(step_key="a", status="failed", attempts=1),
        SimpleNamespace(step_key="b", status="blocked", attempts=2),
        SimpleNamespace(step_key="c", status="completed", attempts=1),
        SimpleNamespace(step_key="d", status="failed", attempts=3),
        SimpleNamespace(step_key="e", status="running", attempts=1),
    ]
    assert retryable_step_keys(steps) == ["a", "b"]
