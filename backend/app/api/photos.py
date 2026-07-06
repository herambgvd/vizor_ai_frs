"""Face photo enrollment + management (nested under persons).

Ported from vizor_nvr FRS. Upload runs the enrollment pipeline (detect → embed →
gallery upsert) in a threadpool; the person's enrollment rollup + thumbnail are
recomputed after every change. Deleting a photo removes its blob + gallery points.
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.audit import record as audit_record
from edge.core.errors import NotFoundError
from edge.core.storage import _dec, get_storage
from edge.db.base import get_db

from .. import enroll, gallery
from ..domain.models import Person, Photo
from ..domain.permissions import FrsPerm
from .schemas import PhotoOut

router = APIRouter(prefix="/frs", tags=["frs-photos"])


async def _photo_out(p: Photo) -> PhotoOut:
    out = PhotoOut.model_validate(p)
    out.image_url = await get_storage().url(p.storage_key) if p.storage_key else None
    return out


async def _recount(db: AsyncSession, person: Person) -> None:
    """Recompute the person's photo rollup + thumbnail from its photos."""
    photos = (
        await db.execute(select(Photo).where(Photo.person_id == person.id).order_by(Photo.created_at))
    ).scalars().all()
    person.photo_count = len(photos)
    enrolled = [p for p in photos if p.status == "enrolled"]
    person.enrolled_photo_count = len(enrolled)
    if enrolled:
        person.enrollment_status = "enrolled"
    elif any(p.status == "pending" for p in photos):
        person.enrollment_status = "pending"
    elif photos:
        person.enrollment_status = "failed"
    else:
        person.enrollment_status = "unenrolled"
    person.thumbnail_key = enrolled[0].storage_key if enrolled else (photos[0].storage_key if photos else None)


def _apply_result(photo: Photo, result: dict) -> None:
    photo.status = result.get("status", "failed")
    photo.embedding_id = result.get("embedding_id")
    photo.quality_score = result.get("quality_score")
    photo.liveness_score = result.get("liveness_score")
    photo.sharpness_score = result.get("sharpness_score")
    photo.error_code = result.get("error_code")
    photo.error = result.get("error")


@router.post("/persons/{person_id}/photos", response_model=PhotoOut, status_code=201)
async def upload_photo(
    person_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.PERSON_MANAGE)),
) -> PhotoOut:
    """Upload a face photo and enroll it (detect → embed → gallery)."""
    person = await db.get(Person, person_id)
    if person is None:
        raise NotFoundError("person not found")
    data = await file.read()
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    photo_id = uuid.uuid4()
    key = f"frs/persons/{person_id}/face_{photo_id.hex}{ext}"
    await get_storage().put(key, data, file.content_type)
    photo = Photo(id=photo_id, person_id=person_id, storage_key=key, status="pending")
    db.add(photo)
    await db.commit()

    result = await run_in_threadpool(
        enroll.enroll_photo, data, person_id=person_id, photo_id=photo_id, person_name=person.full_name
    )
    _apply_result(photo, result)
    await _recount(db, person)
    await db.commit()
    await db.refresh(photo)
    await audit_record(
        db, actor=actor, action="frs.photo.enroll", target_type="frs_photo",
        target_id=str(photo.id), meta={"person_id": str(person_id), "status": photo.status},
    )
    return await _photo_out(photo)


@router.get("/persons/{person_id}/photos", response_model=list[PhotoOut])
async def list_photos(
    person_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.PERSON_READ)),
) -> list[PhotoOut]:
    rows = (
        await db.execute(select(Photo).where(Photo.person_id == person_id).order_by(Photo.created_at))
    ).scalars().all()
    return [await _photo_out(p) for p in rows]


@router.delete("/photos/{photo_id}", status_code=204)
async def delete_photo(
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.PERSON_MANAGE)),
) -> None:
    photo = await db.get(Photo, photo_id)
    if photo is None:
        raise NotFoundError("photo not found")
    person = await db.get(Person, photo.person_id)
    key = photo.storage_key
    await run_in_threadpool(gallery.delete_by_point_key, str(photo_id))
    await db.delete(photo)
    await db.commit()
    if key:
        try:
            await get_storage().delete(key)
        except Exception:  # pragma: no cover
            pass
    if person is not None:
        await _recount(db, person)
        await db.commit()
    await audit_record(
        db, actor=actor, action="frs.photo.delete", target_type="frs_photo", target_id=str(photo_id),
    )


@router.post("/photos/{photo_id}/retry", response_model=PhotoOut)
async def retry_photo(
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.PERSON_MANAGE)),
) -> PhotoOut:
    """Re-run enrollment on a stored photo (drops any stale gallery points first)."""
    photo = await db.get(Photo, photo_id)
    if photo is None:
        raise NotFoundError("photo not found")
    person = await db.get(Person, photo.person_id)
    # Stored face media is encrypted at rest (frs/ prefix); S3 get() returns the
    # ciphertext, so decrypt before handing raw JPEG bytes to the decoder.
    data = _dec(photo.storage_key, await get_storage().get(photo.storage_key))
    await run_in_threadpool(gallery.delete_by_point_key, str(photo_id))
    result = await run_in_threadpool(
        enroll.enroll_photo, data, person_id=photo.person_id, photo_id=photo_id,
        person_name=(person.full_name if person else ""),
    )
    _apply_result(photo, result)
    if person is not None:
        await _recount(db, person)
    await db.commit()
    await db.refresh(photo)
    return await _photo_out(photo)
