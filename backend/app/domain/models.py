"""FRS domain ORM models.

Re-implemented from the vizor_nvr FRS module, feature-by-feature. Each ported
feature adds its own table(s) here. All use portable SQLAlchemy types
(Uuid/JSON/String) so the same models run on Postgres and SQLite.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from edge.db.base import Base


class Group(Base):
    """A person group / watchlist. Persons belong to at most one group; deleting a
    group orphans its persons (their group_id is cleared) rather than deleting them."""

    __tablename__ = "frs_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    # Free-form category, e.g. "watchlist" | "whitelist" | "vip" | "staff".
    group_type: Mapped[str] = mapped_column(String, nullable=False, default="watchlist")
    color_code: Mapped[str] = mapped_column(String, nullable=False, default="#ef4444")
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Optional alert sound key played by the UI on a match against this group.
    alert_sound: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Person(Base):
    """A person in the gallery. Face samples (frs_photos) + their embeddings are
    added by the Photos port; this is the identity record + profile + consent."""

    __tablename__ = "frs_persons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Optional external key (badge/HR id) for bulk import upsert + 3rd-party ingest.
    external_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True, index=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frs_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Enrollment rollup (maintained by the Photos port): unenrolled|pending|enrolled|failed.
    enrollment_status: Mapped[str] = mapped_column(String, nullable=False, default="unenrolled")
    photo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enrolled_photo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thumbnail_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Extended profile.
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    designation: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_joining: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Government ID.
    id_type: Mapped[str | None] = mapped_column(String, nullable=True)
    id_number: Mapped[str | None] = mapped_column(String, nullable=True)
    id_file_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Validity window + auto-purge (DPDP storage limitation).
    validity_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    validity_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    auto_remove: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Free-form extra attributes so scenarios extend without a migration.
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Photo(Base):
    """One enrolled face sample for a person. The stored image lives under the
    encrypted-at-rest frs/ prefix; its embedding(s) live in the Qdrant gallery
    (grouped by ``embedding_id`` = the photo id, shared by the main + augment
    points so a delete removes them all)."""

    __tablename__ = "frs_photos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frs_persons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    thumbnail_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # pending (uploaded, not yet embedded) | enrolled | failed.
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    embedding_id: Mapped[str | None] = mapped_column(String, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Camera(Base):
    """A face-recognition camera / video source. The RTSP url may embed credentials,
    so it is treated as sensitive. When ``recognition_enabled`` and ``enabled`` are
    both set, the live supervisor decodes the stream, runs the FaceEngine, and writes
    recognition events via ``record_event``. ``direction`` feeds the transit engine."""

    __tablename__ = "frs_cameras"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    rtsp_url: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    # Logical grouping / zone label (free-form), e.g. "Lobby", "Gate 3".
    zone: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recognition_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Recognition tuning.
    min_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    fps: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    min_face_px: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    # entry | exit | both — used by the transit engine.
    direction: Mapped[str] = mapped_column(String, nullable=False, default="both")
    # none | nvdec — hardware decode selection for the RTSP reader.
    hw_accel: Mapped[str] = mapped_column(String, nullable=False, default="none")
    # Polygon regions of interest (list of {points:[[x,y],...]} in 0..1 coords).
    roi: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # online | offline | error — maintained by the supervisor's health check.
    status: Mapped[str] = mapped_column(String, nullable=False, default="offline", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshot_key: Mapped[str | None] = mapped_column(String, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FRSEvent(Base):
    """A recognition event — a person sighting written by the live pipeline or the
    ingest API. The face crop is stored under the encrypted frs/ prefix and its
    embedding in the Qdrant snapshots collection (for forensic search)."""

    __tablename__ = "frs_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    camera_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # face_recognized | face_unknown | spoof_detected | face_detected
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frs_persons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    person_name: Mapped[str | None] = mapped_column(String, nullable=True)
    track_id: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    snapshot_key: Mapped[str | None] = mapped_column(String, nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    age: Mapped[str | None] = mapped_column(String, nullable=True)
    age_range: Mapped[str | None] = mapped_column(String, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    gender_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FRSFeedback(Base):
    """An operator verdict on a recognition event (correct / wrong). Feeds the
    mismatch report and future active-learning. ``actual_person_id`` records who
    the face really was when the match was wrong."""

    __tablename__ = "frs_feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frs_events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    matched_person_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actual_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frs_persons.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    operator: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Investigation(Base):
    """A saved forensic face-search job (query image → gallery/snapshot hits)."""

    __tablename__ = "frs_investigations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="done")
    similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.45)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    results: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TransitRule(Base):
    """A cross-camera movement rule: a person seen at an entry camera must reach an
    exit camera within a deadline, else the session is flagged overdue."""

    __tablename__ = "frs_transit_rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # {entry_camera, exit_camera, deadline_seconds, group_id?, direction?}
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TransitSession(Base):
    """An in-flight or finished transit: person entered at one camera, expected to
    exit at another before ``attributes.deadline``. status: open|completed|overdue."""

    __tablename__ = "frs_transit_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frs_transit_rules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frs_persons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # person_name, entry_camera, exit_camera, entry_snapshot, exit_snapshot, deadline, duration_seconds
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Attendance(Base):
    """A person's daily presence — first check-in + last check-out for a day_key,
    derived from recognition events by the event writer."""

    __tablename__ = "frs_attendance"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frs_persons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    person_name: Mapped[str | None] = mapped_column(String, nullable=True)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    day_key: Mapped[str] = mapped_column(String, nullable=False, index=True)  # YYYY-MM-DD
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_in_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    check_out_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ReportSchedule(Base):
    """A recurring report delivery (attendance/group/mismatch/unknown → email)."""

    __tablename__ = "frs_report_schedules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    report: Mapped[str] = mapped_column(String, nullable=False)         # attendance|group|mismatch|unknown
    fmt: Mapped[str] = mapped_column(String, nullable=False, default="xlsx")  # csv|xlsx
    frequency: Mapped[str] = mapped_column(String, nullable=False, default="daily")  # daily|weekly|monthly
    at_time: Mapped[str] = mapped_column(String, nullable=False, default="08:00")
    range_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    recipients: Mapped[str | None] = mapped_column(String, nullable=True)  # comma-separated emails
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ReportRun(Base):
    """A generated report file (from a schedule or an ad-hoc run)."""

    __tablename__ = "frs_report_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frs_report_schedules.id", ondelete="SET NULL"), nullable=True
    )
    report: Mapped[str] = mapped_column(String, nullable=False)
    fmt: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str | None] = mapped_column(String, nullable=True)  # storage key
    rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    emailed_to: Mapped[str | None] = mapped_column(String, nullable=True)
    email_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FrsSettings(Base):
    """Singleton FRS feature config (row id='singleton'): public dashboard +
    third-party ingest API toggles + the ingest key."""

    __tablename__ = "frs_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="singleton")
    public_dashboard_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public_show_names: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ingest_api_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ingest_api_key: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
