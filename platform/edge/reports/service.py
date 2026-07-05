"""Report generation logic — create jobs, render bytes, store the result.

Two execution paths share the same core (build bytes → store → mark done):

  * INLINE (async): ``generate_report_now`` — runs inside the web request. This is
    what the app uses today: small/medium exports produced on demand.
  * WORKER (sync):  ``run_report_task`` — a Celery task for the SCALE path (large
    exports that shouldn't block a request). It uses the sync DB session + a sync
    call into storage. Wired but optional; the inline path is the default.

The format→bytes mapping and the storage key convention (``reports/<id>.<fmt>``)
are identical across both paths so a downloaded file is the same either way.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import ValidationError
from ..core.storage import get_storage
from ..tasks.base import task
from . import export
from .models import ReportJob

# Allowed export formats → the MIME type stored files are served with.
_CONTENT_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _build_bytes(fmt: str, name: str, rows: list[dict], columns: list[str]) -> bytes:
    """Dispatch to the right serialiser in export.py for ``fmt``."""
    if fmt == "csv":
        return export.to_csv(rows, columns)
    if fmt == "xlsx":
        return export.to_xlsx(rows, columns)
    if fmt == "pdf":
        return export.to_pdf(name, rows, columns)
    raise ValidationError(f"unsupported report format: {fmt!r}")


async def create_job(
    db: AsyncSession, name: str, format: str, requested_by: uuid.UUID | None
) -> ReportJob:
    """Register a new pending report job (writes commit)."""
    if format not in _CONTENT_TYPES:
        raise ValidationError(f"unsupported report format: {format!r}")
    job = ReportJob(name=name, format=format, status="pending", requested_by=requested_by)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def list_query() -> Select:
    """A SELECT of all report jobs, newest first — feed to ``paginate``."""
    return select(ReportJob).order_by(ReportJob.created_at.desc())


async def generate_report_now(
    db: AsyncSession, job: ReportJob, rows: list[dict], columns: list[str]
) -> ReportJob:
    """Produce the report INLINE: build bytes → store → mark the job done.

    On any failure the job is flipped to ``failed`` with the error recorded, and
    the exception is NOT re-raised — the job row is the source of truth for the
    outcome, so callers poll status rather than catch exceptions.
    """
    job.status = "running"
    await db.commit()
    try:
        data = _build_bytes(job.format, job.name, rows, columns)
        key = f"reports/{job.id}.{job.format}"
        await get_storage().put(key, data, _CONTENT_TYPES[job.format])
        job.result_key = key
        job.status = "done"
        job.error = None
    except Exception as exc:  # noqa: BLE001 — record ANY failure on the job row
        job.status = "failed"
        job.error = str(exc)
    finally:
        job.finished_at = _now()
        await db.commit()
        await db.refresh(job)
    return job


# --- Celery scale path -------------------------------------------------------
@task(name="edge.reports.service.run_report_task")
def run_report_task(job_id: str, rows: list[dict], columns: list[str]) -> str:
    """Celery task: same work as ``generate_report_now`` but fully SYNCHRONOUS.

    Celery workers are sync, so this uses the sync DB session (``get_sync_session``)
    and a sync bridge into the (async) storage backend. For now the app relies on
    the inline path above; this task is the horizontal-scale option for big exports
    enqueued with ``run_report_task.delay(str(job.id), rows, columns)``.

    Returns the job's final status so it's visible in the Celery result backend.
    """
    import asyncio

    from ..tasks.base import get_sync_session

    storage = get_storage()

    with get_sync_session() as db:
        job = db.get(ReportJob, uuid.UUID(job_id))
        if job is None:
            return "missing"
        job.status = "running"
        db.commit()
        try:
            data = _build_bytes(job.format, job.name, rows, columns)
            key = f"reports/{job.id}.{job.format}"
            # Storage is async; from a sync worker we drive one call on a throwaway
            # event loop. asyncio.run builds + tears down a loop for this single put.
            asyncio.run(storage.put(key, data, _CONTENT_TYPES[job.format]))
            job.result_key = key
            job.status = "done"
            job.error = None
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = _now()
            db.commit()
            status = job.status
    return status
