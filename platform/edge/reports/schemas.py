"""Pydantic schemas for the reports API."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class ReportJobOut(BaseModel):
    """A report job as returned by the list/detail endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    format: str
    status: str
    result_key: str | None
    error: str | None
    requested_by: uuid.UUID | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


class CreateReportIn(BaseModel):
    """Body for the stub create endpoint. ``format`` defaults to CSV.

    Real report generation is scenario-specific (the rows come from a domain
    query), so this just registers a pending job; scenarios call the service's
    ``generate_report_now`` / ``run_report_task`` with their own rows.
    """

    name: str
    format: str = "csv"
