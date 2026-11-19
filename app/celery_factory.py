from celery import Celery, Task

def make_celery(app):
    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery = Celery(app.import_name, task_cls=FlaskTask)
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_reject_on_worker_lost=True,
        task_soft_time_limit=540,
        task_time_limit=600,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            "billing-subscription-expiry-hourly": {
                "task": "billing.process_subscription_expirations",
                "schedule": 3600.0,
            },
        },
    )
    celery.set_default()
    return celery
