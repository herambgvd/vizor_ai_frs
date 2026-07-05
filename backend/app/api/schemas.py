"""Pydantic request/response schemas for the FRS domain API.

Grown feature-by-feature during the port.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, model_validator


# --- groups ------------------------------------------------------------------
class GroupCreate(BaseModel):
    name: str
    group_type: str = "watchlist"
    color_code: str = "#ef4444"
    description: str | None = None
    alert_sound: str | None = None


class GroupUpdate(BaseModel):
    name: str | None = None
    group_type: str | None = None
    color_code: str | None = None
    description: str | None = None
    alert_sound: str | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    group_type: str
    color_code: str
    description: str | None
    alert_sound: str | None
    person_count: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


# --- persons -----------------------------------------------------------------
def _check_validity(start, end, auto_remove):
    """Shared rule: end >= start, window <= 183 days, auto_remove needs an end."""
    if start and end:
        if end < start:
            raise ValueError("validity_end must be on or after validity_start")
        if (end - start).days > 183:
            raise ValueError("validity window cannot exceed 6 months (183 days)")
    if auto_remove and not end:
        raise ValueError("auto_remove requires a validity_end")


class PersonCreate(BaseModel):
    full_name: str
    external_id: str | None = None
    group_id: uuid.UUID | None = None
    category: str | None = None
    priority: int = 0
    department: str | None = None
    designation: str | None = None
    contact_number: str | None = None
    date_of_joining: dt.date | None = None
    id_type: str | None = None
    id_number: str | None = None
    validity_start: dt.date | None = None
    validity_end: dt.date | None = None
    auto_remove: bool = False
    attributes: dict = {}

    @model_validator(mode="after")
    def _validity(self):
        _check_validity(self.validity_start, self.validity_end, self.auto_remove)
        return self


class PersonUpdate(BaseModel):
    full_name: str | None = None
    external_id: str | None = None
    group_id: uuid.UUID | None = None
    category: str | None = None
    priority: int | None = None
    department: str | None = None
    designation: str | None = None
    contact_number: str | None = None
    date_of_joining: dt.date | None = None
    id_type: str | None = None
    id_number: str | None = None
    validity_start: dt.date | None = None
    validity_end: dt.date | None = None
    auto_remove: bool | None = None
    attributes: dict | None = None

    @model_validator(mode="after")
    def _validity(self):
        _check_validity(self.validity_start, self.validity_end, bool(self.auto_remove))
        return self


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    external_id: str | None
    group_id: uuid.UUID | None
    category: str | None
    priority: int
    enrollment_status: str
    photo_count: int
    enrolled_photo_count: int
    thumbnail_key: str | None
    department: str | None
    designation: str | None
    contact_number: str | None
    date_of_joining: dt.date | None
    id_type: str | None
    id_number: str | None
    id_file_key: str | None
    validity_start: dt.date | None
    validity_end: dt.date | None
    auto_remove: bool
    attributes: dict
    has_id_document: bool = False
    created_at: dt.datetime
    updated_at: dt.datetime


# --- photos ------------------------------------------------------------------
class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    person_id: uuid.UUID
    status: str
    quality_score: float | None
    liveness_score: float | None
    sharpness_score: float | None
    error_code: str | None
    error: str | None
    image_url: str | None = None
    created_at: dt.datetime


# --- cameras -----------------------------------------------------------------
class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    location: str | None = None
    zone: str | None = None
    enabled: bool = True
    recognition_enabled: bool = True
    min_confidence: float = 0.5
    fps: int = 5
    min_face_px: int = 40
    direction: str = "both"        # entry | exit | both
    hw_accel: str = "none"         # none | nvdec
    roi: list = []


class CameraUpdate(BaseModel):
    name: str | None = None
    rtsp_url: str | None = None
    location: str | None = None
    zone: str | None = None
    enabled: bool | None = None
    recognition_enabled: bool | None = None
    min_confidence: float | None = None
    fps: int | None = None
    min_face_px: int | None = None
    direction: str | None = None
    hw_accel: str | None = None
    roi: list | None = None


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    rtsp_url: str
    location: str | None
    zone: str | None
    enabled: bool
    recognition_enabled: bool
    min_confidence: float
    fps: int
    min_face_px: int
    direction: str
    hw_accel: str
    roi: list
    status: str
    last_seen_at: dt.datetime | None
    last_error: str | None
    snapshot_url: str | None = None
    events_24h: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


# --- events + feedback -------------------------------------------------------
class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    camera_id: uuid.UUID | None
    camera_name: str | None
    person_id: uuid.UUID | None
    person_name: str | None
    track_id: str | None
    confidence: float | None
    bbox: list
    liveness_score: float | None
    age: str | None
    age_range: str | None
    gender: str | None
    gender_confidence: float | None
    snapshot_url: str | None = None
    match_thumb_url: str | None = None   # enrolled thumbnail of the matched person
    feedback: str | None = None          # "correct" | "wrong" | None
    triggered_at: dt.datetime


class EventPage(BaseModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int


class EventBulkDelete(BaseModel):
    ids: list[uuid.UUID] = []
    all_matching: bool = False
    camera_id: uuid.UUID | None = None
    event_type: str | None = None
    since: dt.datetime | None = None
    until: dt.datetime | None = None


class FeedbackCreate(BaseModel):
    event_id: uuid.UUID
    is_correct: bool
    matched_person_id: uuid.UUID | None = None
    actual_person_id: uuid.UUID | None = None
    note: str | None = None
