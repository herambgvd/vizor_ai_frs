"""FRS background daemons — scheduled-report auto-send + transit overdue sweep.

Ported from vizor_nvr (scenarios/frs/routers/report_schedule.py ``_Scheduler`` and
scenarios/frs/live/manager.py's periodic ``sweep_overdue``). Two async loops, each
polling once a minute, wrapped so a single failure never kills the loop. Launched
from the app lifespan (``start_background_tasks``) and cancelled on shutdown.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from edge.core.logging import get_logger
from edge.db.base import get_sessionmaker

from . import reports, transit_engine
from .domain.models import ReportSchedule

log = get_logger("frs.scheduler")

# Poll cadence — one minute, mirroring vizor_nvr's report scheduler + live sweep.
REPORT_POLL_SECONDS = 60
TRANSIT_POLL_SECONDS = 60


async def report_scheduler_loop() -> None:
    """Every 60s: fire any enabled schedule whose ``next_run_at`` is due. Each run
    builds the report → stores a ReportRun → emails recipients and advances
    ``next_run_at`` (handled inside ``reports.run_schedule``). One failing schedule
    is logged and skipped; the loop never dies."""
    log.info("[report-schedule] scheduler loop started (every %ss)", REPORT_POLL_SECONDS)
    while True:
        try:
            now = datetime.now(timezone.utc)
            async with get_sessionmaker()() as db:
                due = (
                    await db.execute(
                        select(ReportSchedule).where(
                            ReportSchedule.enabled.is_(True),
                            ReportSchedule.next_run_at.isnot(None),
                            ReportSchedule.next_run_at <= now,
                        )
                    )
                ).scalars().all()
                for sched in due:
                    try:
                        await reports.run_schedule(db, sched)
                        # run_schedule advances next_run_at; keep it authoritative but
                        # defend against a same-tick re-fire if it somehow stayed due.
                        if sched.next_run_at is None or sched.next_run_at <= now:
                            sched.next_run_at = reports.next_run(sched.frequency, sched.at_time)
                            await db.commit()
                        log.info("[report-schedule] ran %s (%s)", sched.name, sched.report)
                    except Exception as exc:  # noqa: BLE001 — one bad schedule mustn't stop the rest
                        log.exception("[report-schedule] run failed for %s: %s", sched.id, exc)
                        try:
                            await db.rollback()
                        except Exception:  # noqa: BLE001
                            pass
        except Exception as exc:  # noqa: BLE001 — loop must never die
            log.warning("[report-schedule] loop error: %s", exc)
        await asyncio.sleep(REPORT_POLL_SECONDS)


async def transit_sweep_loop() -> None:
    """Every 60s: flip open transit sessions past their deadline to ``overdue`` (and
    emit a ``transit_overdue`` event per flip). Mirrors vizor_nvr's periodic
    ``sweep_overdue`` cadence. No-op when there are no rules/sessions."""
    log.info("[transit] overdue sweep loop started (every %ss)", TRANSIT_POLL_SECONDS)
    while True:
        try:
            async with get_sessionmaker()() as db:
                await transit_engine.sweep_overdue(db)
        except Exception as exc:  # noqa: BLE001 — the sweep must never blow up the loop
            log.warning("[transit] sweep loop error: %s", exc)
        await asyncio.sleep(TRANSIT_POLL_SECONDS)


def start_background_tasks() -> list[asyncio.Task]:
    """Launch the report-scheduler + transit-sweep loops as asyncio tasks and return
    them. Call from within the running event loop (the app lifespan)."""
    tasks = [
        asyncio.create_task(report_scheduler_loop(), name="frs-report-scheduler"),
        asyncio.create_task(transit_sweep_loop(), name="frs-transit-sweep"),
    ]
    return tasks


def stop_background_tasks(tasks: list[asyncio.Task] | None) -> None:
    """Cancel previously launched background tasks (best-effort)."""
    for t in tasks or []:
        try:
            t.cancel()
        except Exception:  # noqa: BLE001
            pass
