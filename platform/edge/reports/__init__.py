"""Reports: CSV/XLSX/PDF export framework — runnable inline or via Celery.

Pieces:
  * ``export`` serialisers (``to_csv`` / ``to_xlsx`` / ``to_pdf``) — pure bytes.
  * ``ReportJob`` — tracks an export request's lifecycle + result file.
  * ``service.generate_report_now`` (inline) / ``run_report_task`` (Celery worker).
  * ``router`` — list / detail / download, permission-gated.

Wire into a scenario app:

    from edge import reports
    app = create_app(registry, extra_routers=[reports.router])

Produce a report from your own domain rows:

    job = await reports.create_job(db, "Daily events", "csv", requested_by=user.id)
    await reports.generate_report_now(db, job, rows, columns=["time", "camera"])
"""

from .export import to_csv, to_pdf, to_xlsx
from .models import ReportJob
from .router import router
from .service import create_job, generate_report_now, list_query, run_report_task

__all__ = [
    "router",
    "ReportJob",
    "to_csv",
    "to_xlsx",
    "to_pdf",
    "create_job",
    "generate_report_now",
    "list_query",
    "run_report_task",
]
