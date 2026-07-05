"""The Celery application — background/async work off the request path.

Long-running or scheduled jobs (report generation, batch inference, nightly
cleanups, email digests) don't belong in a web request. They go to Celery workers
via Redis. The web app enqueues a task; a separate worker process runs it.

Broker AND result backend are both Redis (``settings.redis_url``) — one dependency
for both "here is a job" (broker) and "here is its result/status" (backend).

Run a worker:      celery -A edge.tasks.app.celery_app worker -l info
Run the beat:      celery -A edge.tasks.app.celery_app beat -l info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab  # noqa: F401  (imported for the beat example below)

from ..core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "edge",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
    # Import these at worker/beat startup so their @task functions register and
    # edge.tasks.retention.register_beat() installs the periodic cleanup schedule.
    include=["edge.reports.service", "edge.tasks.retention"],
)

# JSON everywhere: human-inspectable payloads and no pickle security surface.
# UTC timestamps so schedules are unambiguous across deployment timezones.
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# --- Celery-beat periodic schedule (placeholder) -----------------------------
# Empty by default. Each scenario adds its own periodic jobs here, e.g.:
#
#   from celery.schedules import crontab
#   celery_app.conf.beat_schedule = {
#       "nightly-report": {
#           "task": "edge.reports.service.run_report_task",
#           "schedule": crontab(hour=2, minute=0),   # 02:00 UTC daily
#           "args": (),
#       },
#   }
celery_app.conf.beat_schedule = {}

# Auto-discover @task-decorated functions in these modules so the worker registers
# them without every module having to be imported explicitly at worker startup.
celery_app.autodiscover_tasks(["edge.reports"])
