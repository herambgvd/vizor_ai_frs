"""Third-party FRS event ingest — an external NVR/system posts recognition events.

Authenticated by the rotating ingest key (``X-FRS-Ingest-Key``), gated by the
``ingest_api_enabled`` feature toggle. Resolves the person by external_id (or
name), then records the event (which also updates attendance + the snapshots
collection) via the shared event writer.
"""

from __future__ import annotations

import base64
import datetime as dt
import secrets
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.core.errors import UnauthorizedError
from edge.db.base import get_db

from .. import events, settings_store
from ..domain.models import Camera, Person

router = APIRouter(prefix="/frs/ingest", tags=["frs-ingest"])


@router.post("/event")
async def ingest_event(body: dict, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    row = await settings_store.get_settings_row(db)
    if not row.ingest_api_enabled or not row.ingest_api_key:
        raise UnauthorizedError("ingest API is disabled")
    key = request.headers.get("x-frs-ingest-key") or ""
    if not secrets.compare_digest(key, row.ingest_api_key):
        raise UnauthorizedError("invalid ingest key")

    # Resolve the person (external_id first, then name).
    person_id, person_name = None, body.get("person_name")
    ext = body.get("person_external_id")
    person = None
    if ext:
        person = (await db.execute(select(Person).where(Person.external_id == ext))).scalar_one_or_none()
    elif person_name:
        person = (await db.execute(select(Person).where(Person.full_name == person_name))).scalar_one_or_none()
    if person is not None:
        person_id, person_name = person.id, person.full_name

    # Resolve the posting camera so we can key the transit engine + direction-aware
    # attendance off it. The external system may send a camera_id (uuid) or a
    # camera_name; fall back to "both" direction / no camera when it's unknown.
    cam_ref = body.get("camera_id")
    cam_name = body.get("camera_name") or body.get("camera_id")
    camera = None
    cam_uuid = None
    if cam_ref:
        try:
            cam_uuid = uuid.UUID(str(cam_ref))
        except (ValueError, TypeError):
            cam_uuid = None
    if cam_uuid is not None:
        camera = await db.get(Camera, cam_uuid)
    if camera is None and cam_name:
        camera = (
            await db.execute(select(Camera).where(Camera.name == cam_name))
        ).scalar_one_or_none()
    resolved_camera_id = camera.id if camera is not None else cam_uuid
    resolved_camera_name = camera.name if camera is not None else cam_name
    direction = camera.direction if camera is not None else "both"

    snapshot = None
    b64 = body.get("snapshot_base64")
    if b64:
        try:
            snapshot = base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            snapshot = None

    triggered_at = None
    ts = body.get("timestamp")
    if ts:
        try:
            triggered_at = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            triggered_at = None

    ev = await events.record_event(
        db,
        event_type=body.get("event_type", "face_recognized"),
        person_id=person_id,
        person_name=person_name,
        camera_id=resolved_camera_id,
        camera_name=resolved_camera_name,
        confidence=body.get("confidence"),
        bbox=body.get("bbox") or [],
        snapshot_bytes=snapshot,
        attributes=body.get("attributes") or {"source": body.get("source")},
        triggered_at=triggered_at,
        direction=direction,
    )
    return {"ok": True, "event_id": str(ev.id), "matched": person_id is not None,
            "person_id": str(person_id) if person_id else None}
