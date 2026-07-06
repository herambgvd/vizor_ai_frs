"""Direction-aware daily attendance punching (``events._touch_attendance`` and the
``record_event`` attendance path).

entry camera  → earliest check-in
exit camera   → latest check-out
both / unset  → legacy first-seen / last-seen
transit_overdue (and other non-sightings) must NOT punch the clock.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select

from app import events
from app.domain.models import Attendance, Person


def _day(y=2026, m=7, d=6, hh=9, mm=0):
    # NOTE: naive UTC on purpose. SQLite's DateTime(timezone=True) does not preserve
    # tzinfo on round-trip (a SQLite-only quirk; Postgres does), so a stored aware
    # value reads back naive. Using naive UTC keeps stored == expected on either DB.
    return dt.datetime(y, m, d, hh, mm)


async def _rows(db, pid):
    return (await db.execute(
        select(Attendance).where(Attendance.person_id == pid))).scalars().all()


async def _touch(db, **kw):
    kw.setdefault("person_name", "P")
    kw.setdefault("camera_id", uuid.uuid4())
    kw.setdefault("event_id", uuid.uuid4())
    kw.setdefault("snapshot_key", None)
    await events._touch_attendance(db, **kw)
    await db.commit()


# ── entry ──────────────────────────────────────────────────────────────────────
async def test_entry_sets_checkin(db):
    pid = uuid.uuid4()
    await _touch(db, person_id=pid, event_type="face_recognized",
                 ts=_day(hh=9), direction="entry", snapshot_key="in.jpg")
    rows = await _rows(db, pid)
    assert len(rows) == 1
    assert rows[0].check_in_at == _day(hh=9)
    assert rows[0].check_out_at is None
    assert rows[0].check_in_snapshot == "in.jpg"


async def test_entry_keeps_earliest_checkin(db):
    pid = uuid.uuid4()
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=9), direction="entry")
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=8), direction="entry")
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=11), direction="entry")
    rows = await _rows(db, pid)
    assert len(rows) == 1
    assert rows[0].check_in_at == _day(hh=8)  # earliest wins


# ── exit ───────────────────────────────────────────────────────────────────────
async def test_exit_first_creates_checkout_only(db):
    pid = uuid.uuid4()
    await _touch(db, person_id=pid, event_type="face_recognized",
                 ts=_day(hh=18), direction="exit", snapshot_key="out.jpg")
    rows = await _rows(db, pid)
    assert len(rows) == 1
    assert rows[0].check_in_at is None
    assert rows[0].check_out_at == _day(hh=18)
    assert rows[0].check_out_snapshot == "out.jpg"


async def test_exit_keeps_latest_checkout(db):
    pid = uuid.uuid4()
    # Exit sightings arrive in time order (as they do live); each advances check-out.
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=9), direction="entry")
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=17), direction="exit")
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=18), direction="exit")
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=19), direction="exit")
    rows = await _rows(db, pid)
    assert len(rows) == 1
    assert rows[0].check_in_at == _day(hh=9)
    assert rows[0].check_out_at == _day(hh=19)  # advances to most recent exit


# ── both / unset (legacy last-seen) ────────────────────────────────────────────
async def test_both_is_last_seen(db):
    pid = uuid.uuid4()
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=9), direction="both")
    await _touch(db, person_id=pid, event_type="face_recognized", ts=_day(hh=17), direction=None)
    rows = await _rows(db, pid)
    assert len(rows) == 1
    assert rows[0].check_in_at == _day(hh=9)     # first sighting
    assert rows[0].check_out_at == _day(hh=17)   # advances to last seen


# ── non-sightings must not punch ────────────────────────────────────────────────
async def test_transit_overdue_does_not_punch(db):
    pid = uuid.uuid4()
    await _touch(db, person_id=pid, event_type="transit_overdue", ts=_day(), direction="entry")
    assert await _rows(db, pid) == []


async def test_no_person_id_does_not_punch(db):
    await _touch(db, person_id=None, event_type="face_recognized", ts=_day(), direction="entry")
    # nothing to assert on a specific pid; just confirm no row exists at all
    assert (await db.execute(select(Attendance))).scalars().all() == []


async def test_separate_days_are_separate_rows(db):
    pid = uuid.uuid4()
    await _touch(db, person_id=pid, event_type="face_recognized",
                 ts=_day(d=6, hh=9), direction="entry")
    await _touch(db, person_id=pid, event_type="face_recognized",
                 ts=_day(d=7, hh=9), direction="entry")
    assert len(await _rows(db, pid)) == 2


# ── record_event integration (no snapshot → no storage/qdrant touched) ──────────
async def test_record_event_punches_and_enriches(db):
    pid = uuid.uuid4()
    db.add(Person(id=pid, full_name="Carol"))
    await db.commit()

    ev = await events.record_event(
        db, event_type="face_recognized", person_id=pid, person_name="Carol",
        camera_id=uuid.uuid4(), direction="entry", triggered_at=_day(hh=9),
    )
    assert ev.attributes["authorized"] is True
    assert ev.attributes["auth_reason"] is None
    rows = await _rows(db, pid)
    assert len(rows) == 1 and rows[0].check_in_at == _day(hh=9)


async def test_record_event_transit_overdue_no_punch(db):
    pid = uuid.uuid4()
    ev = await events.record_event(
        db, event_type="transit_overdue", person_id=pid, person_name="Dan",
        camera_id=uuid.uuid4(), direction="entry", triggered_at=_day(),
        attributes={"title": "Transit overdue — Dan"},
    )
    assert ev.severity == "warning" and ev.detection_type == "transit"
    assert await _rows(db, pid) == []
