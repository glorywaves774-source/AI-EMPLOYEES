"""Send a harmless probe task and verify that a live Celery worker handles it."""
import os


def main():
    broker = os.environ.get("REDIS_URL")
    if not broker:
        raise SystemExit("REDIS_URL is required.")
    from celery import Celery
    celery = Celery("ai-workforce-release-smoke", broker=broker, backend=broker)
    celery.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json")
    result = celery.send_task("ops.ping")
    try:
        payload = result.get(timeout=int(os.environ.get("WORKER_SMOKE_TIMEOUT", "25")),
                             propagate=True)
    except Exception as exc:
        raise SystemExit(f"Celery worker probe failed: {type(exc).__name__}: {exc}") from exc
    if payload != {"status": "ok", "service": "ai-workforce-worker"}:
        raise SystemExit(f"Unexpected worker probe response: {payload!r}")
    print("Celery worker task execution: OK")


if __name__ == "__main__":
    main()
