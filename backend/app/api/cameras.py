"""FRS cameras (video sources) CRUD + connection test.

Ported from the vizor_nvr FRS camera manager, re-implemented on the platform-edge
stack. A camera is an RTSP source the live supervisor decodes and runs the
FaceEngine over. ``POST /{id}/test`` pulls a single frame to verify connectivity
and store a preview snapshot.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.audit import record as audit_record
from edge.core.errors import NotFoundError
from edge.core.logging import get_logger
from edge.core.storage import get_storage
from edge.db.base import get_db

from ..domain.models import Camera, FRSEvent
from ..domain.permissions import FrsPerm
from .schemas import CameraCreate, CameraOut, CameraUpdate

log = get_logger("frs.cameras")

router = APIRouter(prefix="/frs/cameras", tags=["frs-cameras"])


async def _events_24h(db: AsyncSession, camera_id: uuid.UUID) -> int:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    return int(
        await db.scalar(
            select(func.count()).select_from(FRSEvent).where(
                FRSEvent.camera_id == camera_id, FRSEvent.triggered_at >= since
            )
        )
        or 0
    )


async def _out(db: AsyncSession, c: Camera) -> CameraOut:
    out = CameraOut.model_validate(c)
    storage = get_storage()
    out.snapshot_url = await storage.url(c.snapshot_key) if c.snapshot_key else None
    out.events_24h = await _events_24h(db, c.id)
    return out


@router.get("", response_model=list[CameraOut])
async def list_cameras(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.CAMERA_READ)),
) -> list[CameraOut]:
    rows = (await db.execute(select(Camera).order_by(Camera.name))).scalars().all()
    return [await _out(db, c) for c in rows]


@router.post("", response_model=CameraOut, status_code=201)
async def create_camera(
    data: CameraCreate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.CAMERA_MANAGE)),
) -> CameraOut:
    c = Camera(**data.model_dump())
    db.add(c)
    await db.commit()
    await db.refresh(c)
    await audit_record(
        db, actor=actor, action="frs.camera.create", target_type="frs_camera",
        target_id=str(c.id), meta={"name": c.name},
    )
    return await _out(db, c)


@router.get("/{camera_id}", response_model=CameraOut)
async def get_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.CAMERA_READ)),
) -> CameraOut:
    c = await db.get(Camera, camera_id)
    if c is None:
        raise NotFoundError("camera not found")
    return await _out(db, c)


@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: uuid.UUID,
    data: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.CAMERA_MANAGE)),
) -> CameraOut:
    c = await db.get(Camera, camera_id)
    if c is None:
        raise NotFoundError("camera not found")
    # exclude_unset so a client can clear the optional text fields (location/zone)
    # with an explicit null. Every other Camera column is non-nullable, so a stray
    # null there is meaningless — drop it rather than violate NOT NULL.
    _CLEARABLE = {"location", "zone"}
    patch = {
        k: v
        for k, v in data.model_dump(exclude_unset=True).items()
        if v is not None or k in _CLEARABLE
    }
    for key, value in patch.items():
        setattr(c, key, value)
    await db.commit()
    await db.refresh(c)
    await audit_record(
        db, actor=actor, action="frs.camera.update", target_type="frs_camera",
        target_id=str(camera_id), meta={k: v for k, v in patch.items() if k != "rtsp_url"},
    )
    return await _out(db, c)


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.CAMERA_MANAGE)),
) -> None:
    c = await db.get(Camera, camera_id)
    if c is None:
        raise NotFoundError("camera not found")
    name = c.name
    await db.delete(c)
    await db.commit()
    await audit_record(
        db, actor=actor, action="frs.camera.delete", target_type="frs_camera",
        target_id=str(camera_id), meta={"name": name},
    )


def _grab_frame(url: str, hw_accel: str) -> bytes | None:
    """Pull a single frame from the RTSP url and return it JPEG-encoded (blocking)."""
    import cv2  # local import — heavy runtime dep

    from edge.stream.rtsp import RTSPReader

    reader = RTSPReader(url, fps=1, reconnect=False)
    try:
        for frame in reader.frames():
            ok, buf = cv2.imencode(".jpg", frame)
            return buf.tobytes() if ok else None
    finally:
        reader.close()
    return None


@router.post("/{camera_id}/test", response_model=CameraOut)
async def test_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.CAMERA_MANAGE)),
) -> CameraOut:
    """Try to connect and grab one frame; store it as a preview + update status."""
    from fastapi.concurrency import run_in_threadpool

    c = await db.get(Camera, camera_id)
    if c is None:
        raise NotFoundError("camera not found")
    try:
        frame = await run_in_threadpool(_grab_frame, c.rtsp_url, c.hw_accel)
    except Exception as exc:  # noqa: BLE001 — surface any decode/connect failure as status
        frame = None
        log.warning("camera test failed camera=%s err=%s", camera_id, exc)
        c.last_error = str(exc)[:500]
    if frame:
        key = f"frs/cameras/{c.id.hex}.jpg"
        await get_storage().put(key, frame, "image/jpeg")
        c.snapshot_key = key
        c.status = "online"
        c.last_seen_at = dt.datetime.now(dt.timezone.utc)
        c.last_error = None
    else:
        c.status = "error"
        c.last_error = c.last_error or "no frame received"
    await db.commit()
    await db.refresh(c)
    return await _out(db, c)
