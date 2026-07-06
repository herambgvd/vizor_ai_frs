"""Report builders (``reports.build``) shapes on empty and seeded data, plus the
``next_run`` schedule helper. No storage/email is exercised (that's the export /
run_schedule path)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import reports
from app.domain.models import (
    Attendance,
    FRSEvent,
    Group,
    Person,
    TransitRule,
    TransitSession,
)

TODAY = dt.date.today()
DF = (TODAY - dt.timedelta(days=1)).isoformat()
DT = TODAY.isoformat()

EXPECTED_COLUMNS = {
    "attendance": ["snapshot", "day", "person_name", "first_in", "last_out", "duration"],
    "group": ["group", "headcount", "present", "compliance_pct"],
    "mismatch": ["snapshot", "person_name", "entry_time", "exit_time", "status"],
    "unknown": ["snapshot", "time", "camera", "detected_pct"],
}


# ── empty data: shape only ──────────────────────────────────────────────────────
@pytest.mark.parametrize("report", reports.REPORTS)
async def test_build_empty(db, report):
    data = await reports.build(db, report, DF, DT)
    assert data["columns"] == EXPECTED_COLUMNS[report]
    assert data["items"] == []
    assert data["total"] == 0


async def test_build_unknown_report_raises(db):
    with pytest.raises(ValueError):
        await reports.build(db, "does-not-exist", DF, DT)


# ── attendance ──────────────────────────────────────────────────────────────────
async def test_attendance_rows(db):
    pid = uuid.uuid4()
    db.add(Person(id=pid, full_name="Alice"))
    cin = dt.datetime.combine(TODAY, dt.time(9, 0), tzinfo=dt.timezone.utc)
    cout = dt.datetime.combine(TODAY, dt.time(17, 30), tzinfo=dt.timezone.utc)
    db.add(Attendance(person_id=pid, person_name="Alice", day_key=TODAY.isoformat(),
                      check_in_at=cin, check_out_at=cout))
    await db.commit()

    data = await reports.build(db, "attendance", DF, DT)
    assert data["total"] == 1
    row = data["items"][0]
    assert row["person_name"] == "Alice"
    assert row["day"] == TODAY.isoformat()
    assert row["duration"] == "8h 30m"


# ── group ───────────────────────────────────────────────────────────────────────
async def test_group_compliance(db):
    gid = uuid.uuid4()
    db.add(Group(id=gid, name="Staff"))
    present_pid, absent_pid = uuid.uuid4(), uuid.uuid4()
    db.add(Person(id=present_pid, full_name="Seen", group_id=gid))
    db.add(Person(id=absent_pid, full_name="Unseen", group_id=gid))
    db.add(Attendance(person_id=present_pid, person_name="Seen", day_key=TODAY.isoformat(),
                      check_in_at=dt.datetime.now(dt.timezone.utc)))
    await db.commit()

    data = await reports.build(db, "group", DF, DT)
    assert data["total"] == 1
    row = data["items"][0]
    assert row["group"] == "Staff"
    assert row["headcount"] == 2
    assert row["present"] == 1
    assert row["compliance_pct"] == 50.0


# ── mismatch (transit sessions) ─────────────────────────────────────────────────
async def test_mismatch_status_mapping(db):
    rule = TransitRule(name="gate", config={})
    db.add(rule)
    await db.commit()
    now = dt.datetime.now(dt.timezone.utc)
    for status, ended in [("closed", now), ("overdue", None), ("open", None)]:
        db.add(TransitSession(rule_id=rule.id, person_id=uuid.uuid4(), status=status,
                              started_at=now, ended_at=ended,
                              attributes={"person_name": f"P-{status}"}))
    await db.commit()

    data = await reports.build(db, "mismatch", DF, DT)
    assert data["total"] == 3
    statuses = {r["status"] for r in data["items"]}
    assert statuses == {"Resolved", "Unresolved (overdue)", "Unpaired (no exit)"}


# ── unknown ─────────────────────────────────────────────────────────────────────
async def test_unknown_uses_detector_confidence(db):
    now = dt.datetime.now(dt.timezone.utc)
    ev = FRSEvent(id=uuid.uuid4(), event_type="face_unknown", title="Unknown face",
                  camera_name="Lobby", triggered_at=now,
                  attributes={"det_confidence": 0.9})
    db.add(ev)
    # A recognized event must NOT appear in the unknown report.
    db.add(FRSEvent(id=uuid.uuid4(), event_type="face_recognized", title="x",
                    triggered_at=now, attributes={}))
    await db.commit()

    data = await reports.build(db, "unknown", DF, DT)
    assert data["total"] == 1
    row = data["items"][0]
    assert row["camera"] == "Lobby"
    assert row["detected_pct"] == 90.0


# ── next_run scheduling ─────────────────────────────────────────────────────────
def test_next_run_daily_later_today():
    after = dt.datetime(2026, 7, 6, 7, 0, tzinfo=dt.timezone.utc)
    nxt = reports.next_run("daily", "08:00", after=after)
    assert nxt == dt.datetime(2026, 7, 6, 8, 0, tzinfo=dt.timezone.utc)


def test_next_run_daily_rolls_to_tomorrow():
    after = dt.datetime(2026, 7, 6, 9, 0, tzinfo=dt.timezone.utc)
    nxt = reports.next_run("daily", "08:00", after=after)
    assert nxt == dt.datetime(2026, 7, 7, 8, 0, tzinfo=dt.timezone.utc)


def test_next_run_weekly_is_a_week_out():
    after = dt.datetime(2026, 7, 6, 9, 0, tzinfo=dt.timezone.utc)
    nxt = reports.next_run("weekly", "08:00", after=after)
    assert nxt.hour == 8 and nxt.minute == 0
    assert (nxt - after).days >= 6


def test_next_run_bad_time_defaults_to_0800():
    after = dt.datetime(2026, 7, 6, 9, 0, tzinfo=dt.timezone.utc)
    nxt = reports.next_run("daily", "not-a-time", after=after)
    assert nxt.hour == 8 and nxt.minute == 0
