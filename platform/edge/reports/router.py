"""Reports API — list/inspect report jobs + fetch a download link.

Reading the job list requires REPORT_READ; creating an export or downloading a
produced file requires REPORT_EXPORT. Actual generation is scenario-specific (the
rows come from a domain query), so ``POST ""`` only registers a pending job as a
stub — scenarios then call ``service.generate_report_now`` / ``run_report_task``
with their own rows/columns.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import require_permission
from ..auth.models import User
from ..auth.permissions import CorePerm
from ..core.errors import NotFoundError, ValidationError
from ..core.pagination import Page, PageParams, page_params, paginate
from ..core.storage import get_storage
from ..db.base import get_db
from . import service
from .models import ReportJob
from .schemas import CreateReportIn, ReportJobOut

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=Page[ReportJobOut])
async def list_reports(
    params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(CorePerm.REPORT_READ)),
) -> Page[ReportJobOut]:
    """Paginated list of report jobs, newest first."""
    return await paginate(db, service.list_query(), params, item_model=ReportJobOut)


@router.post("", response_model=ReportJobOut, status_code=201)
async def create_report(
    data: CreateReportIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CorePerm.REPORT_EXPORT)),
) -> ReportJob:
    """Register a pending report job (stub).

    Generation is deferred to the owning scenario, which supplies the actual rows
    to ``service.generate_report_now`` (inline) or ``run_report_task`` (worker).
    """
    return await service.create_job(db, data.name, data.format, requested_by=user.id)


@router.get("/{job_id}", response_model=ReportJobOut)
async def get_report(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(CorePerm.REPORT_READ)),
) -> ReportJob:
    """Fetch a single report job (poll this for its status)."""
    job = await db.get(ReportJob, job_id)
    if job is None:
        raise NotFoundError("report job not found")
    return job


@router.get("/{job_id}/download")
async def download_report(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(CorePerm.REPORT_EXPORT)),
) -> dict:
    """Return a fetchable URL for a finished report's file.

    We hand back a URL (local file link or presigned S3 link) rather than
    streaming bytes through the API — the browser fetches the blob directly from
    storage. 404 if the job doesn't exist; 422 if it isn't ``done`` yet.
    """
    job = await db.get(ReportJob, job_id)
    if job is None:
        raise NotFoundError("report job not found")
    if job.status != "done" or not job.result_key:
        raise ValidationError(f"report is not ready (status={job.status})")
    url = await get_storage().url(job.result_key)
    return {"url": url}
