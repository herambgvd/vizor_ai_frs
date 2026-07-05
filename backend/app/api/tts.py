"""Server-side text-to-speech for audio alerts (espeak-ng → WAV).

Used by the operator UI to speak alert text. Requires the ``espeak-ng`` (or
``espeak``) binary; returns 400 with a clear message when it isn't installed.
"""

from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from edge.auth.deps import require_permission
from edge.core.errors import ValidationError

from ..domain.permissions import FrsPerm

router = APIRouter(prefix="/frs", tags=["frs-tts"])


@router.get("/tts")
async def tts(
    text: str = Query(..., max_length=300),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> Response:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise ValidationError("text-to-speech is unavailable (install espeak-ng on the server)")
    try:
        proc = subprocess.run([exe, "--stdout", text], capture_output=True, timeout=10)
    except (subprocess.SubprocessError, OSError) as exc:  # pragma: no cover
        raise ValidationError(f"tts failed: {exc}")
    return Response(
        content=proc.stdout,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=3600"},
    )
