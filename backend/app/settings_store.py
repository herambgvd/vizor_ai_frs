"""FRS feature-settings singleton accessor + ingest-key helpers."""

from __future__ import annotations

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from .domain.models import FrsSettings

_SAMPLE_INGEST = {
    "camera_id": "cam-1",
    "camera_name": "Gate 1",
    "person_external_id": "EMP001",
    "person_name": "Ravi Kumar",
    "event_type": "face_recognized",
    "confidence": 0.92,
    "timestamp": "2026-07-04T09:00:00Z",
    "bbox": [100, 120, 220, 300],
    "attributes": {"age": "25-34", "gender": "male"},
    "source": "external-nvr",
    "snapshot_base64": "<optional base64 jpeg>",
}


async def get_settings_row(db: AsyncSession) -> FrsSettings:
    row = await db.get(FrsSettings, "singleton")
    if row is None:
        row = FrsSettings(id="singleton")
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def as_dict(row: FrsSettings) -> dict:
    return {
        "public_dashboard_enabled": row.public_dashboard_enabled,
        "public_show_names": row.public_show_names,
        "ingest_api_enabled": row.ingest_api_enabled,
        "ingest_api_key": row.ingest_api_key,
        "sample_ingest_payload": _SAMPLE_INGEST,
    }


async def rotate_ingest_key(db: AsyncSession) -> str:
    row = await get_settings_row(db)
    row.ingest_api_key = "frsk_" + secrets.token_urlsafe(24)
    await db.commit()
    return row.ingest_api_key
