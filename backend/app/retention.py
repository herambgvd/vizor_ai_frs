"""Background data-retention sweeper (GDPR/DPDP storage-limitation).

Ported from vizor_nvr (scenarios/frs/live/retention.py). Runs every
``FRS_RETENTION_SWEEP_HOURS`` (default 6) and:

  (a) purges ``FRSEvent`` rows older than ``FRS_RETENTION_EVENT_DAYS`` (default 90)
      in batches — deleting each event's stored snapshot blob + its Qdrant snapshot
      vector before the row;
  (b) fully erases ``Person`` rows flagged ``auto_remove`` whose ``validity_end`` has
      passed — gallery vectors, their FRSEvents (+ snapshots), attendance rows, face
      photos (+ blobs), the government-ID document blob, then the person row.

Retention is GLOBAL (env-driven), never per-camera / per-setting. Enrolled gallery
photos of still-valid persons are never touched — only expired identities and
time-series events. Every step is idempotent, batched, and swallows errors so the
loop never dies.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from edge.core.logging import get_logger
from edge.core.storage import get_storage
from edge.db.base import get_sessionmaker

from . import gallery
from .domain.models import Attendance, FRSEvent, Person, Photo

log = get_logger("frs.retention")

# Rows deleted per DB round-trip so a huge backlog never loads at once.
_BATCH = 500


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


async def _purge_old_events() -> int:
    """Delete events older than the retention window, batch by batch, dropping each
    event's snapshot blob + forensic snapshot vector first."""
    days = _env_int("FRS_RETENTION_EVENT_DAYS", 90)
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = 0
    while True:
        async with get_sessionmaker()() as db:
            rows = (
                await db.execute(
                    select(FRSEvent).where(FRSEvent.triggered_at < cutoff).limit(_BATCH)
                )
            ).scalars().all()
            if not rows:
                break
            for ev in rows:
                await _drop_event_media(ev)
                await db.delete(ev)
            await db.commit()
            total += len(rows)
        if len(rows) < _BATCH:
            break
    return total


async def _drop_event_media(ev: FRSEvent) -> None:
    """Best-effort removal of an event's snapshot blob + Qdrant snapshot vector."""
    if ev.snapshot_key:
        try:
            await get_storage().delete(ev.snapshot_key)
        except Exception as exc:  # noqa: BLE001 — best-effort blob cleanup
            log.warning("[frs-retention] snapshot delete failed event=%s err=%s", ev.id, exc)
    try:
        await run_in_threadpool(gallery.delete_snapshot, str(ev.id))
    except Exception as exc:  # noqa: BLE001
        log.warning("[frs-retention] qdrant snapshot delete failed event=%s err=%s", ev.id, exc)


async def _erase_person(db, p: Person) -> None:
    """Full right-to-erasure cascade for one expired person (mirrors the persons
    API delete + vizor_nvr retention): gallery vectors, events (+ snapshots),
    attendance, photos (+ blobs), ID document, then the person row."""
    pid = p.id
    id_key = p.id_file_key
    # Collect photo blob keys before the person delete cascades their rows away.
    photo_keys = (
        await db.execute(select(Photo.storage_key).where(Photo.person_id == pid))
    ).scalars().all()
    # Gallery embeddings (all points carrying this person_id — main + augments).
    await run_in_threadpool(gallery.delete_by_person, str(pid))
    # Events: drop snapshot media + rows (FK is SET NULL, so delete explicitly).
    events = (
        await db.execute(select(FRSEvent).where(FRSEvent.person_id == pid))
    ).scalars().all()
    for ev in events:
        await _drop_event_media(ev)
        await db.delete(ev)
    # Attendance rows.
    atts = (
        await db.execute(select(Attendance).where(Attendance.person_id == pid))
    ).scalars().all()
    for a in atts:
        await db.delete(a)
    # The person row — frs_photos rows cascade via FK.
    await db.delete(p)
    await db.commit()
    # Blobs after the DB commit so a failed delete never blocks the row removal.
    for key in [*photo_keys, id_key]:
        if not key:
            continue
        try:
            await get_storage().delete(key)
        except Exception:  # noqa: BLE001 — best-effort; not fatal
            pass


async def _purge_expired_persons() -> int:
    """Fully delete persons flagged ``auto_remove`` whose ``validity_end`` has passed."""
    today = date.today()
    total = 0
    while True:
        async with get_sessionmaker()() as db:
            rows = (
                await db.execute(
                    select(Person)
                    .where(
                        Person.auto_remove.is_(True),
                        Person.validity_end.isnot(None),
                        Person.validity_end < today,
                    )
                    .limit(_BATCH)
                )
            ).scalars().all()
            if not rows:
                break
            for p in rows:
                pid = p.id
                try:
                    await _erase_person(db, p)
                    total += 1
                    log.info("[frs-retention] auto-removed expired person %s", pid)
                except Exception as exc:  # noqa: BLE001 — one bad person mustn't stop the sweep
                    log.warning("[frs-retention] erase failed person=%s err=%s", pid, exc)
                    try:
                        await db.rollback()
                    except Exception:  # noqa: BLE001
                        pass
        if len(rows) < _BATCH:
            break
    return total


async def retention_sweeper_loop() -> None:
    """Run the retention sweep every ``FRS_RETENTION_SWEEP_HOURS`` hours (default 6).
    Staggers the first run 60s past boot. Never raises out of the loop."""
    hours = max(1, _env_int("FRS_RETENTION_SWEEP_HOURS", 6))
    log.info(
        "[frs-retention] sweeper loop started (every %sh, events older than %sd)",
        hours, _env_int("FRS_RETENTION_EVENT_DAYS", 90),
    )
    # Stagger first run so boot isn't hammered.
    await asyncio.sleep(60)
    while True:
        try:
            purged = await _purge_old_events()
            expired = await _purge_expired_persons()
            if purged or expired:
                log.info(
                    "[frs-retention] purged %s old events, removed %s expired persons",
                    purged, expired,
                )
        except Exception as exc:  # noqa: BLE001 — the sweep must never blow up
            log.warning("[frs-retention] sweep error: %s", exc)
        await asyncio.sleep(max(1, _env_int("FRS_RETENTION_SWEEP_HOURS", 6)) * 3600)
