"""FRS reports — build tabular report data + CSV/XLSX export, and run scheduled
reports (generate → store → email). Ported from vizor_nvr FRS.

Four fixed reports over a [day_from, day_to] window:
  * attendance — per-person daily presence
  * group      — per-group sighting activity
  * mismatch   — low-confidence recognitions (likely mis-identifications)
  * unknown    — unidentified face sightings
"""

from __future__ import annotations

import csv
import datetime as dt
import io

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .domain.models import Attendance, FRSEvent, Group, Person

REPORTS = ("attendance", "group", "mismatch", "unknown")
# Recognised but below this cosine is treated as a likely mismatch for review.
_MISMATCH_HI = 0.55


def _range(day_from: str | None, day_to: str | None):
    today = dt.date.today()
    df = dt.date.fromisoformat(day_from) if day_from else today - dt.timedelta(days=7)
    dt_ = dt.date.fromisoformat(day_to) if day_to else today
    start = dt.datetime.combine(df, dt.time.min, tzinfo=dt.timezone.utc)
    end = dt.datetime.combine(dt_, dt.time.max, tzinfo=dt.timezone.utc)
    return df, dt_, start, end


async def build(db: AsyncSession, report: str, day_from: str | None, day_to: str | None) -> dict:
    df, dt_, start, end = _range(day_from, day_to)

    if report == "attendance":
        rows = (
            await db.execute(
                select(Attendance).where(Attendance.day_key >= df.isoformat(), Attendance.day_key <= dt_.isoformat())
                .order_by(Attendance.day_key.desc())
            )
        ).scalars().all()
        items = [
            {"person": r.person_name or "—", "day": r.day_key,
             "check_in": r.check_in_at.isoformat() if r.check_in_at else None,
             "check_out": r.check_out_at.isoformat() if r.check_out_at else None}
            for r in rows
        ]
        return {"columns": ["person", "day", "check_in", "check_out"], "items": items}

    if report == "group":
        # sightings per group over the window
        stmt = (
            select(Group.name, func.count(FRSEvent.id))
            .select_from(FRSEvent)
            .join(Person, Person.id == FRSEvent.person_id)
            .join(Group, Group.id == Person.group_id)
            .where(FRSEvent.triggered_at >= start, FRSEvent.triggered_at <= end)
            .group_by(Group.name)
            .order_by(func.count(FRSEvent.id).desc())
        )
        rows = (await db.execute(stmt)).all()
        return {"columns": ["group", "sightings"], "items": [{"group": n, "sightings": c} for n, c in rows]}

    if report == "mismatch":
        rows = (
            await db.execute(
                select(FRSEvent).where(
                    FRSEvent.event_type == "face_recognized",
                    FRSEvent.confidence.isnot(None), FRSEvent.confidence < _MISMATCH_HI,
                    FRSEvent.triggered_at >= start, FRSEvent.triggered_at <= end,
                ).order_by(FRSEvent.triggered_at.desc())
            )
        ).scalars().all()
        items = [{"time": e.triggered_at.isoformat(), "person": e.person_name or "—",
                  "camera": e.camera_name or "—", "confidence": e.confidence} for e in rows]
        return {"columns": ["time", "person", "camera", "confidence"], "items": items}

    if report == "unknown":
        rows = (
            await db.execute(
                select(FRSEvent).where(
                    FRSEvent.event_type == "face_unknown",
                    FRSEvent.triggered_at >= start, FRSEvent.triggered_at <= end,
                ).order_by(FRSEvent.triggered_at.desc())
            )
        ).scalars().all()
        items = [{"time": e.triggered_at.isoformat(), "camera": e.camera_name or "—",
                  "confidence": e.confidence, "snapshot_key": e.snapshot_key} for e in rows]
        return {"columns": ["time", "camera", "confidence"], "items": items}

    raise ValueError(f"unknown report {report!r}")


def to_bytes(data: dict, fmt: str) -> tuple[bytes, str]:
    """Serialise a report dict to CSV or XLSX bytes; returns (bytes, content_type)."""
    cols = data["columns"]
    items = data["items"]
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in items:
            w.writerow(row)
        return buf.getvalue().encode("utf-8"), "text/csv"
    # xlsx
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append([c.replace("_", " ").title() for c in cols])
    for row in items:
        ws.append([row.get(c) for c in cols])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def next_run(frequency: str, at_time: str, after: dt.datetime | None = None) -> dt.datetime:
    """Compute the next fire time for a schedule (UTC)."""
    after = after or dt.datetime.now(dt.timezone.utc)
    try:
        hh, mm = (int(x) for x in at_time.split(":"))
    except ValueError:
        hh, mm = 8, 0
    nxt = after.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= after:
        nxt += dt.timedelta(days=1)
    step = {"daily": 1, "weekly": 7, "monthly": 30}.get(frequency, 1)
    # For weekly/monthly, roll forward to at least `step` days out from `after`.
    while (nxt - after).days < (step - 1):
        nxt += dt.timedelta(days=1)
    return nxt


async def run_schedule(db: AsyncSession, schedule) -> "object":
    """Generate a schedule's report, store the file, email recipients, record a run."""
    from edge.core.storage import get_storage

    from .domain.models import ReportRun

    df = (dt.date.today() - dt.timedelta(days=schedule.range_days)).isoformat()
    dt_ = dt.date.today().isoformat()
    data = await build(db, schedule.report, df, dt_)
    blob, ctype = to_bytes(data, schedule.fmt)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{schedule.report}-{stamp}.{schedule.fmt}"
    key = f"frs/reports/{filename}"
    await get_storage().put(key, blob, ctype)

    emailed, ok = None, False
    recipients = [r.strip() for r in (schedule.recipients or "").split(",") if r.strip()]
    if recipients:
        try:
            from edge.core.config import get_settings
            from edge.messaging.email import send_email

            link = f"{get_settings().frontend_url.rstrip('/')}/reports"
            html = (
                f"<p>Your <strong>{schedule.report}</strong> report for {df} → {dt_} is ready "
                f"({len(data['items'])} rows).</p><p>Download it from the Reports page: "
                f'<a href="{link}">{link}</a></p>'
            )
            await send_email(db, recipients, f"FRS {schedule.report} report", html)
            emailed, ok = ", ".join(recipients), True
        except Exception:  # noqa: BLE001 — email is best-effort
            emailed, ok = ", ".join(recipients), False

    run = ReportRun(schedule_id=schedule.id, report=schedule.report, fmt=schedule.fmt,
                    filename=filename, path=key, rows=len(data["items"]), emailed_to=emailed, email_ok=ok)
    db.add(run)
    schedule.last_run_at = dt.datetime.now(dt.timezone.utc)
    schedule.next_run_at = next_run(schedule.frequency, schedule.at_time)
    await db.commit()
    await db.refresh(run)
    return run
