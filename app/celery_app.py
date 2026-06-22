# The Celery application instance.


from celery import Celery

from .config import CELERY_BROKER_URL

celery_app = Celery(
    "defectsense",
    broker=CELERY_BROKER_URL,
    include=["app.tasks"],  # tells the worker where to find our task definitions
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,        # we never check task results
    worker_prefetch_multiplier=1,   # don't let a worker grab a big batch of jobs at once
    broker_connection_retry_on_startup=True,  # keep retrying if redis isn't up yet when the worker starts
    broker_connection_retry=True,    # and keep retrying if it drops out mid-run, not just at startup
)
