"""ScenarioHook — the seam where scenario-specific logic plugs into the pipeline.

The boilerplate pipeline handles the common, boring parts: decode RTSP frames,
run the detector, track objects, manage the appearance lifecycle. It delegates
the SCENARIO-SPECIFIC decision — what to match against, what counts as an alert —
to a hook:

    FRS  hook -> embed face -> Qdrant watchlist match -> identity alert
    ANPR hook -> OCR plate  -> Postgres hotlist match  -> plate alert
    PPE  hook -> rule: person without helmet            -> violation alert

Keeping this a small interface means one pipeline serves every scenario; only the
hook (and its matcher/model) changes.

NOTE: FrameContext / ScenarioEvent are firmed up in the pipeline phase; typed as
Any here so the interface is importable before the pipeline exists.
"""

from __future__ import annotations

from typing import Any, Protocol


class ScenarioHook(Protocol):
    async def on_frame(self, ctx: Any) -> list[Any]:
        """Handle one processed frame's detections; return events/alerts to emit."""
        ...
