"""Opt-in tests against a dedicated disposable staging environment.

Set AI_WORKFORCE_RUN_LIVE_INTEGRATION=1 only when DATABASE_URL, REDIS_URL,
S3 access and the deployed worker all point to a non-production test stack.
"""
import os
import pytest

RUN_LIVE = os.environ.get("AI_WORKFORCE_RUN_LIVE_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(not RUN_LIVE, reason="live staging integration tests are opt-in")


def test_web_readiness_reports_database_and_redis():
    from app import create_app
    app = create_app()
    response = app.test_client().get("/readyz")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["database"] == "ok"
    assert payload["redis"] == "ok"


def test_celery_worker_executes_probe_task():
    from app import create_app
    app = create_app()
    celery = app.extensions["celery"]
    result = celery.send_task("ops.ping")
    assert result.get(timeout=25, propagate=True) == {
        "status": "ok", "service": "ai-workforce-worker"
    }
