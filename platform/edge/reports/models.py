"""ReportJob ORM model — one row per export request, tracking its lifecycle.

A report export can be produced inline (small, in the request) or handed to a
Celery worker (large, off the request path). Either way a ReportJob row records
what was asked for, its status, and — once done — the storage key of the produced
file so the user can download it later.

``format`` and ``status`` are plain String columns (not DB enums) on purpose: it
keeps migrations portable across Postgres/SQLite and dodges the enum-migration
footguns; the allowed values are documented here and validated in the service.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class ReportJob(Base):
    """A single report/export request and its result."""

    __tablename__ = "report_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # One of: "csv" | "xlsx" | "pdf".
    format: Mapped[str] = mapped_column(String, nullable=False)
    # Lifecycle: "pending" -> "running" -> "done" | "failed".
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # Storage key of the produced file (set on success); None until then.
    result_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Human-readable failure reason (set on failure); None otherwise.
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    # Who requested it (a User id) — nullable for system/scheduled jobs.
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # When the job reached a terminal state (done/failed); None while in flight.
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
