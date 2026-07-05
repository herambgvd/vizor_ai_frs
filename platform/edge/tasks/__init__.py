"""Tasks: the Celery app + a ``@task`` decorator + a sync DB session for workers.

Enqueue background work from anywhere:

    from edge.reports.service import run_report_task
    run_report_task.delay(str(job.id), rows, columns)

Define a task:

    from edge.tasks import task

    @task
    def cleanup_old_files(): ...

Run a worker:  celery -A edge.tasks.app.celery_app worker -l info
"""

from .app import celery_app
from .base import get_sync_session, task

__all__ = ["celery_app", "task", "get_sync_session"]
