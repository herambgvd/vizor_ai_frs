"""Server-side text-to-speech for audio alerts (espeak-ng → WAV).

Browser SpeechSynthesis is unreliable across kiosks / voice-packs, so the spoken FRS
alerts ("Authorized <name>", "Unregistered person detected", …) are synthesised on
the server with espeak-ng and streamed back as WAV. The frontend fetches the WAV as
an authed blob and plays it on a gesture-unlocked <audio> element, so it sounds the
same on every browser regardless of installed voices.

Synthesised WAVs are cached on disk by a content hash of ``voice:text`` (vizor_nvr
parity): repeated phrases ("Authorized <name>") are synthesised once and served from
cache thereafter. Requires the ``espeak-ng`` (or ``espeak``) binary; returns 400 with
a clear message when it isn't installed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from edge.auth.deps import require_permission
from edge.core.errors import ValidationError

from ..domain.permissions import FrsPerm

router = APIRouter(prefix="/frs", tags=["frs-tts"])

# Content-hash disk cache — repeated phrases don't re-synthesise every event.
_CACHE = Path(os.getenv("FRS_TTS_CACHE", "/tmp/frs_tts"))
_CACHE.mkdir(parents=True, exist_ok=True)
_VOICE = os.getenv("FRS_TTS_VOICE", "en-us")


def _synthesize(exe: str, text: str) -> bytes:
    """Synthesise ``text`` to a WAV, memoised on disk by hash(voice:text).

    On a cache hit the file is just read back; on a miss espeak-ng writes the WAV to
    the cache path and we return its bytes. Runs on the threadpool (blocking IO +
    subprocess) so the event loop is never stalled.
    """
    key = hashlib.sha1(f"{_VOICE}:{text}".encode()).hexdigest()[:20]
    out = _CACHE / f"{key}.wav"
    if not out.exists():
        try:
            subprocess.run(
                [exe, "-v", _VOICE, "-s", "165", "-w", str(out), text],
                check=True, timeout=10,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError) as exc:  # pragma: no cover
            # Don't leave a truncated/empty file behind to poison the cache.
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass
            raise ValidationError(f"tts failed: {exc}")
    return out.read_bytes()


@router.get("/tts")
async def tts(
    text: str = Query(..., max_length=300),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> Response:
    text = (text or "").strip()
    if not text:
        return Response(status_code=204)
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise ValidationError("text-to-speech is unavailable (install espeak-ng on the server)")
    data = await run_in_threadpool(_synthesize, exe, text)
    return Response(
        content=data,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )
