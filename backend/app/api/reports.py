"""FRS reports + scheduled reports (matches vizor_nvr ReportsTab).

Four fixed reports over a date range with JSON/CSV/XLSX output, an attendance log,
and recurring scheduled deliveries (generate → store → email → downloadable run).
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.auth.security import verify_password
from edge.core.audit import record as audit_record
from edge.core.errors import ForbiddenError, NotFoundError, ValidationError
from edge.core.pagination import Page, PageParams, page_params, paginate
from edge.core.storage import get_storage
from edge.db.base import get_db

from .. import reports as rpt
from ..domain.models import Attendance, Camera, FRSEvent, Person, ReportRun, ReportSchedule
from ..domain.permissions import FrsPerm
from ._scope import allowed_camera_ids

router = APIRouter(prefix="/frs", tags=["frs-reports"])


# --- attendance --------------------------------------------------------------
@router.get("/attendance")
async def attendance_log(
    person_id: uuid.UUID | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    stmt = select(Attendance).order_by(Attendance.day_key.desc(), Attendance.check_in_at.desc())
    if person_id is not None:
        stmt = stmt.where(Attendance.person_id == person_id)
    if since:
        stmt = stmt.where(Attendance.day_key >= since)
    if until:
        stmt = stmt.where(Attendance.day_key <= until)
    page = await paginate(db, stmt, params)
    storage = get_storage()
    items = []
    for a in page.items:
        ci, co = a.check_in_at, a.check_out_at
        duration = int((co - ci).total_seconds()) if (ci and co and co >= ci) else None
        items.append({
            "id": str(a.id),
            "person_id": str(a.person_id) if a.person_id else None,
            "person_name": a.person_name,
            "day": a.day_key,
            "check_in_at": ci.isoformat() if ci else None,
            "check_out_at": co.isoformat() if co else None,
            "check_in_url": await storage.url(a.check_in_snapshot) if a.check_in_snapshot else None,
            "check_out_url": await storage.url(a.check_out_snapshot) if a.check_out_snapshot else None,
            "duration_seconds": duration,
        })
    return {"items": items, "total": page.total, "page": page.page, "pages": page.pages}


@router.get("/attendance/report")
async def attendance_report(
    day_from: str | None = Query(default=None),
    day_to: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    df = day_from or (dt.date.today() - dt.timedelta(days=30)).isoformat()
    dt_ = day_to or dt.date.today().isoformat()
    # Group by person_id (stable identity) so two distinct people who happen to share
    # a display name are not merged; fall back to the name only when person_id is null.
    key = func.coalesce(cast(Attendance.person_id, String), Attendance.person_name)
    rows = (
        await db.execute(
            select(func.max(Attendance.person_name), func.count(func.distinct(Attendance.day_key)),
                   func.min(Attendance.day_key), func.max(Attendance.day_key))
            .where(Attendance.day_key >= df, Attendance.day_key <= dt_)
            .group_by(key).order_by(func.count().desc())
        )
    ).all()
    items = [{"person_name": n or "—", "days_present": d, "first_seen": f, "last_seen": l} for n, d, f, l in rows]
    return {"items": items, "day_from": df, "day_to": dt_}


@router.delete("/attendance/{att_id}")
async def delete_attendance(
    att_id: uuid.UUID,
    password: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.EVENT_MANAGE)),
) -> dict:
    """Delete one attendance record. Sensitive action — the operator must re-enter
    their own password to confirm."""
    if not password or not verify_password(password, actor.password_hash):
        raise ForbiddenError("incorrect password")
    row = await db.get(Attendance, att_id)
    if row is None:
        raise NotFoundError("attendance record not found")
    await db.delete(row)
    await db.commit()
    await audit_record(
        db, actor=actor, action="frs.attendance.delete", target_type="frs_attendance",
        target_id=str(att_id), meta={"person": row.person_name, "day": row.day_key},
    )
    return {"status": "deleted"}


# --- reports (static routes before the {report} catch-all) -------------------
@router.get("/reports/summary")
async def reports_summary(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """Dashboard rollup: cameras, enrolled persons, all-time + today's event counts,
    and today's distinct attendance. Computed as a handful of grouped aggregate
    queries (one per table — no per-row N+1)."""
    now = dt.datetime.now(dt.timezone.utc)
    day_start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=dt.timezone.utc)
    today_key = now.date().isoformat()

    def _i(v) -> int:
        return int(v or 0)

    # Cameras — total / online / recognising in a single row.
    cam = (await db.execute(
        select(
            func.count(),
            func.sum(case((Camera.status == "online", 1), else_=0)),
            func.sum(case((Camera.recognition_enabled.is_(True), 1), else_=0)),
        )
    )).one()

    # Persons — total / enrolled in a single row.
    per = (await db.execute(
        select(
            func.count(),
            func.sum(case((Person.enrollment_status == "enrolled", 1), else_=0)),
        )
    )).one()

    # Events — all-time totals by type in a single row.
    ev_all = (await db.execute(
        select(
            func.count(),
            func.sum(case((FRSEvent.event_type == "face_recognized", 1), else_=0)),
            func.sum(case((FRSEvent.event_type == "face_unknown", 1), else_=0)),
        )
    )).one()

    # Events — today's totals by type in a single row.
    ev_today = (await db.execute(
        select(
            func.count(),
            func.sum(case((FRSEvent.event_type == "face_recognized", 1), else_=0)),
            func.sum(case((FRSEvent.event_type == "face_unknown", 1), else_=0)),
        ).where(FRSEvent.triggered_at >= day_start)
    )).one()

    # Distinct persons with an attendance row for today.
    attendance_today = _i(await db.scalar(
        select(func.count(func.distinct(Attendance.person_id)))
        .where(Attendance.day_key == today_key, Attendance.person_id.is_not(None))
    ))

    return {
        # Back-compat keys (unchanged meaning).
        "total_events": _i(ev_all[0]),
        "recognized": _i(ev_all[1]),
        "unknown": _i(ev_all[2]),
        "persons": _i(per[0]),
        # Cameras.
        "cameras_total": _i(cam[0]),
        "cameras_online": _i(cam[1]),
        "cameras_recognising": _i(cam[2]),
        # Persons.
        "persons_enrolled": _i(per[1]),
        "persons_total": _i(per[0]),
        # Today (UTC).
        "events_today": _i(ev_today[0]),
        "recognitions_today": _i(ev_today[1]),
        "unknowns_today": _i(ev_today[2]),
        "attendance_today": attendance_today,
    }


@router.get("/reports/{report}")
async def report_data(
    report: str,
    day_from: str | None = Query(default=None),
    day_to: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    cam_scope: set | None = Depends(allowed_camera_ids),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    if report not in rpt.REPORTS:
        raise ValidationError(f"unknown report; choose one of {', '.join(rpt.REPORTS)}")
    return await rpt.build(db, report, day_from, day_to, camera_ids=cam_scope)


@router.get("/reports/{report}/export")
async def report_export(
    report: str,
    format: str = Query(default="xlsx"),
    day_from: str | None = Query(default=None),
    day_to: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    cam_scope: set | None = Depends(allowed_camera_ids),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> StreamingResponse:
    if report not in rpt.REPORTS:
        raise ValidationError("unknown report")
    if format not in ("csv", "xlsx"):
        raise ValidationError("format must be csv or xlsx")
    data = await rpt.build(db, report, day_from, day_to, camera_ids=cam_scope)
    blob, ctype = await rpt.to_bytes(data, format)
    fname = f"{report}-{dt.date.today().isoformat()}.{format}"
    return StreamingResponse(iter([blob]), media_type=ctype,
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


# --- scheduled reports -------------------------------------------------------
def _sched_out(s: ReportSchedule) -> dict:
    return {"id": str(s.id), "name": s.name, "report": s.report, "fmt": s.fmt,
            "frequency": s.frequency, "at_time": s.at_time, "range_days": s.range_days,
            "recipients": s.recipients, "enabled": s.enabled,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None}


@router.get("/report-schedules")
async def list_schedules(db: AsyncSession = Depends(get_db), _=Depends(require_permission(FrsPerm.EVENT_READ))) -> dict:
    rows = (await db.execute(select(ReportSchedule).order_by(ReportSchedule.created_at.desc()))).scalars().all()
    return {"items": [_sched_out(s) for s in rows]}


@router.post("/report-schedules", status_code=201)
async def create_schedule(body: dict, db: AsyncSession = Depends(get_db), actor=Depends(require_permission(FrsPerm.EVENT_MANAGE))) -> dict:
    if (body.get("report") or "") not in rpt.REPORTS:
        raise ValidationError("invalid report")
    s = ReportSchedule(
        name=body.get("name") or "Report", report=body["report"], fmt=body.get("fmt", "xlsx"),
        frequency=body.get("frequency", "daily"), at_time=body.get("at_time", "08:00"),
        range_days=int(body.get("range_days", 7)), recipients=body.get("recipients") or None,
        enabled=bool(body.get("enabled", True)),
    )
    s.next_run_at = rpt.next_run(s.frequency, s.at_time)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    await audit_record(db, actor=actor, action="frs.report.schedule_create", target_type="frs_report_schedule", target_id=str(s.id))
    return _sched_out(s)


@router.put("/report-schedules/{sid}")
async def update_schedule(sid: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db), actor=Depends(require_permission(FrsPerm.EVENT_MANAGE))) -> dict:
    s = await db.get(ReportSchedule, sid)
    if s is None:
        raise NotFoundError("schedule not found")
    for k in ("name", "report", "fmt", "frequency", "at_time", "range_days", "recipients", "enabled"):
        if k in body:
            setattr(s, k, body[k])
    s.next_run_at = rpt.next_run(s.frequency, s.at_time)
    await db.commit()
    await db.refresh(s)
    return _sched_out(s)


@router.delete("/report-schedules/{sid}", status_code=204)
async def delete_schedule(sid: uuid.UUID, db: AsyncSession = Depends(get_db), actor=Depends(require_permission(FrsPerm.EVENT_MANAGE))) -> None:
    s = await db.get(ReportSchedule, sid)
    if s is None:
        raise NotFoundError("schedule not found")
    await db.delete(s)
    await db.commit()


@router.post("/report-schedules/{sid}/run")
async def run_schedule_now(sid: uuid.UUID, db: AsyncSession = Depends(get_db), actor=Depends(require_permission(FrsPerm.EVENT_MANAGE))) -> dict:
    s = await db.get(ReportSchedule, sid)
    if s is None:
        raise NotFoundError("schedule not found")
    run = await rpt.run_schedule(db, s)
    await audit_record(db, actor=actor, action="frs.report.run", target_type="frs_report_run", target_id=str(run.id))
    return {"id": str(run.id), "filename": run.filename, "rows": run.rows, "email_ok": run.email_ok}


@router.get("/report-runs")
async def list_runs(db: AsyncSession = Depends(get_db), _=Depends(require_permission(FrsPerm.EVENT_READ))) -> dict:
    rows = (await db.execute(select(ReportRun).order_by(ReportRun.created_at.desc()).limit(50))).scalars().all()
    return {"items": [
        {"id": str(r.id), "report": r.report, "fmt": r.fmt, "filename": r.filename, "rows": r.rows,
         "emailed_to": r.emailed_to, "email_ok": r.email_ok,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]}


@router.get("/report-runs/{rid}/download")
async def download_run(rid: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_permission(FrsPerm.EVENT_READ))) -> StreamingResponse:
    run = await db.get(ReportRun, rid)
    if run is None or not run.path:
        raise NotFoundError("report file not found")
    blob = await get_storage().get(run.path)
    ctype = "text/csv" if run.fmt == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(iter([blob]), media_type=ctype,
                             headers={"Content-Disposition": f"attachment; filename={run.filename}"})
