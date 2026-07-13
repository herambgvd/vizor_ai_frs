"""Transit auto-engine: entry opens a session, exit closes it, the sweep flips
past-deadline opens to overdue and emits a ``transit_overdue`` event."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from app import transit_engine
from app.domain.models import FRSEvent, Person, TransitRule, TransitSession


def _now() -> dt.datetime:
    # Naive UTC for sighting timestamps. SQLite's DateTime(timezone=True) drops
    # tzinfo on round-trip, so the engine's ``when - started_at`` duration maths
    # needs both sides naive here (Postgres keeps them aware in production).
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _aware_now() -> dt.datetime:
    # The sweep parses the deadline ISO string and forces UTC, so its ``now`` must
    # be tz-aware to compare against it.
    return dt.datetime.now(dt.timezone.utc)


async def _seed_rule(db, *, entry, exits, window=15, enabled=True) -> TransitRule:
    rule = TransitRule(
        name="gate",
        enabled=enabled,
        config={
            "entry_camera": str(entry),
            "exit_cameras": [str(x) for x in exits],
            "window_minutes": window,
        },
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def _sessions(db):
    return (await db.execute(select(TransitSession))).scalars().all()


# ── _as_uuid helper ───────────────────────────────────────────────────────────
def test_as_uuid_roundtrip_and_bad_input():
    u = uuid.uuid4()
    assert transit_engine._as_uuid(u) is u
    assert transit_engine._as_uuid(str(u)) == u
    assert transit_engine._as_uuid(None) is None
    assert transit_engine._as_uuid("not-a-uuid") is None
    assert transit_engine._as_uuid(12345) is None


# ── on_recognition: entry ──────────────────────────────────────────────────────
async def test_entry_opens_session(db):
    entry, exit_cam, pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rule = await _seed_rule(db, entry=entry, exits=[exit_cam], window=15)
    now = _now()

    await transit_engine.on_recognition(
        db, person_id=pid, person_name="Alice", camera_id=entry, when=now,
        snapshot_key="frs/entry.jpg",
    )

    rows = await _sessions(db)
    assert len(rows) == 1
    s = rows[0]
    assert s.status == "open"
    assert s.rule_id == rule.id and s.person_id == pid
    assert s.attributes["entry_camera"] == str(entry)
    assert s.attributes["person_name"] == "Alice"
    assert s.attributes["entry_snapshot"] == "frs/entry.jpg"
    # deadline = entry + window minutes
    deadline = dt.datetime.fromisoformat(s.attributes["deadline"])
    assert abs((deadline - now).total_seconds() - 15 * 60) < 1


async def test_entry_twice_does_not_double_open(db):
    entry, pid = uuid.uuid4(), uuid.uuid4()
    await _seed_rule(db, entry=entry, exits=[uuid.uuid4()])
    now = _now()
    await transit_engine.on_recognition(db, person_id=pid, camera_id=entry, when=now)
    await transit_engine.on_recognition(
        db, person_id=pid, camera_id=entry, when=now + dt.timedelta(minutes=1))
    rows = await _sessions(db)
    assert len(rows) == 1  # still one open session


# ── on_recognition: exit ───────────────────────────────────────────────────────
async def test_exit_closes_open_session(db):
    entry, exit_cam, pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_rule(db, entry=entry, exits=[exit_cam])
    t0 = _now()
    await transit_engine.on_recognition(db, person_id=pid, camera_id=entry, when=t0)
    t1 = t0 + dt.timedelta(minutes=5)
    await transit_engine.on_recognition(
        db, person_id=pid, camera_id=exit_cam, when=t1, snapshot_key="frs/exit.jpg")

    rows = await _sessions(db)
    assert len(rows) == 1
    s = rows[0]
    assert s.status == "closed"
    assert s.ended_at is not None
    assert s.attributes["exit_camera"] == str(exit_cam)
    assert s.attributes["exit_snapshot"] == "frs/exit.jpg"
    assert s.attributes["duration_seconds"] == 5 * 60


async def test_exit_without_open_session_is_noop(db):
    entry, exit_cam, pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_rule(db, entry=entry, exits=[exit_cam])
    # Exit sighting with no prior entry — nothing to close, nothing opened.
    await transit_engine.on_recognition(db, person_id=pid, camera_id=exit_cam, when=_now())
    assert await _sessions(db) == []


async def test_unknown_camera_does_nothing(db):
    entry, exit_cam, pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_rule(db, entry=entry, exits=[exit_cam])
    await transit_engine.on_recognition(db, person_id=pid, camera_id=uuid.uuid4(), when=_now())
    assert await _sessions(db) == []


async def test_disabled_rule_ignored(db):
    entry, pid = uuid.uuid4(), uuid.uuid4()
    await _seed_rule(db, entry=entry, exits=[uuid.uuid4()], enabled=False)
    await transit_engine.on_recognition(db, person_id=pid, camera_id=entry, when=_now())
    assert await _sessions(db) == []


async def test_missing_ids_short_circuit(db):
    await _seed_rule(db, entry=uuid.uuid4(), exits=[uuid.uuid4()])
    await transit_engine.on_recognition(db, person_id=None, camera_id=uuid.uuid4(), when=_now())
    await transit_engine.on_recognition(db, person_id=uuid.uuid4(), camera_id=None, when=_now())
    assert await _sessions(db) == []


# ── sweep_overdue ──────────────────────────────────────────────────────────────
async def test_sweep_flips_overdue_and_emits_event(db):
    entry, pid = uuid.uuid4(), uuid.uuid4()
    rule = await _seed_rule(db, entry=entry, exits=[uuid.uuid4()], window=15)
    # Open a session whose deadline is already in the past.
    t0 = _now() - dt.timedelta(minutes=30)
    db.add(Person(id=pid, full_name="Bob"))
    await db.commit()
    await transit_engine.on_recognition(
        db, person_id=pid, person_name="Bob", camera_id=entry, when=t0)

    flipped = await transit_engine.sweep_overdue(db, now=_aware_now())
    assert flipped == 1

    rows = await _sessions(db)
    assert rows[0].status == "overdue"

    # A transit_overdue event was written for the operator.
    evs = (await db.execute(
        select(FRSEvent).where(FRSEvent.event_type == "transit_overdue"))).scalars().all()
    assert len(evs) == 1
    ev = evs[0]
    assert ev.severity == "warning"
    assert ev.detection_type == "transit"
    assert ev.person_id == pid
    assert ev.attributes["rule_id"] == str(rule.id)
    assert ev.attributes["rule_name"] == "gate"
    assert ev.attributes["person_name"] == "Bob"
    assert ev.attributes["overdue_seconds"] >= 0


async def test_sweep_leaves_within_deadline_open(db):
    entry, pid = uuid.uuid4(), uuid.uuid4()
    await _seed_rule(db, entry=entry, exits=[uuid.uuid4()], window=60)
    await transit_engine.on_recognition(db, person_id=pid, camera_id=entry, when=_now())

    flipped = await transit_engine.sweep_overdue(db, now=_aware_now())
    assert flipped == 0
    assert (await _sessions(db))[0].status == "open"


async def test_sweep_ignores_closed_sessions(db):
    entry, exit_cam, pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_rule(db, entry=entry, exits=[exit_cam], window=15)
    t0 = _now() - dt.timedelta(minutes=30)
    await transit_engine.on_recognition(db, person_id=pid, camera_id=entry, when=t0)
    await transit_engine.on_recognition(
        db, person_id=pid, camera_id=exit_cam, when=t0 + dt.timedelta(minutes=2))
    # Session is closed even though its deadline has passed — sweep must skip it.
    flipped = await transit_engine.sweep_overdue(db, now=_aware_now())
    assert flipped == 0
    assert (await _sessions(db))[0].status == "closed"
