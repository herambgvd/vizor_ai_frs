"""Overlay drawing helpers — bounding boxes, labels, and landmark points.

These render detection results on top of a frame for preview / debugging / the
annotated re-stream. They are deliberately **non-mutating**: each function works
on a ``.copy()`` of the input so the caller's original frame (which may still be
needed for recording or a second model) is never scribbled on.

The detection objects are duck-typed: anything with a ``.bbox`` attribute works,
whether it's a dataclass, a Pydantic model, or a namedtuple. ``.label`` and
``.score`` are optional and only drawn when present. Bounding boxes are expected
as ``(x1, y1, x2, y2)`` in pixel coordinates.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import cv2
import numpy as np

# BGR colours (OpenCV convention). Defaults chosen to be visible on most video.
_DEFAULT_BOX_COLOR = (0, 255, 0)      # green
_DEFAULT_POINT_COLOR = (0, 0, 255)    # red
_TEXT_COLOR = (0, 0, 0)               # black text on the coloured label chip
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _to_xyxy(bbox: Any) -> tuple[int, int, int, int]:
    """Coerce a bbox (tuple/list/np array of 4 numbers) to int ``(x1,y1,x2,y2)``."""
    x1, y1, x2, y2 = (int(round(float(v))) for v in bbox)
    return x1, y1, x2, y2


def draw_detections(
    frame: np.ndarray,
    items: list,
    *,
    color: tuple[int, int, int] = _DEFAULT_BOX_COLOR,
) -> np.ndarray:
    """Draw each detection's bounding box (and optional label/score) on a copy.

    Args:
        frame: source image, HxWx3 BGR uint8. Not modified.
        items: detections; each must expose ``.bbox`` = (x1, y1, x2, y2), and may
            expose ``.label`` (str) and ``.score`` (float in 0..1).
        color: BGR box colour.

    Returns:
        A new annotated frame (the input is left untouched).
    """
    out = frame.copy()
    for item in items:
        bbox = getattr(item, "bbox", None)
        if bbox is None:
            # Not a detection we can draw — skip rather than crash the stream.
            continue
        x1, y1, x2, y2 = _to_xyxy(bbox)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness=2)

        # Build an optional "label 0.87" caption from whatever fields exist.
        label = getattr(item, "label", None)
        score = getattr(item, "score", None)
        caption_parts: list[str] = []
        if label is not None:
            caption_parts.append(str(label))
        if score is not None:
            caption_parts.append(f"{float(score):.2f}")
        if not caption_parts:
            continue
        caption = " ".join(caption_parts)

        # Draw a filled chip behind the text so it's legible on busy footage.
        (tw, th), baseline = cv2.getTextSize(caption, _FONT, 0.5, 1)
        chip_top = max(0, y1 - th - baseline - 4)
        cv2.rectangle(out, (x1, chip_top), (x1 + tw + 4, y1), color, thickness=cv2.FILLED)
        cv2.putText(
            out,
            caption,
            (x1 + 2, y1 - baseline - 2),
            _FONT,
            0.5,
            _TEXT_COLOR,
            1,
            cv2.LINE_AA,
        )
    return out


def draw_landmarks(
    frame: np.ndarray,
    points: Iterable[Sequence[float]],
    color: tuple[int, int, int] = _DEFAULT_POINT_COLOR,
) -> np.ndarray:
    """Draw landmark points (e.g. face keypoints) as filled dots on a copy.

    Args:
        frame: source image, HxWx3 BGR uint8. Not modified.
        points: iterable of ``(x, y)`` pixel coordinates.
        color: BGR dot colour.

    Returns:
        A new annotated frame.
    """
    out = frame.copy()
    for pt in points:
        x, y = int(round(float(pt[0]))), int(round(float(pt[1])))
        cv2.circle(out, (x, y), radius=2, color=color, thickness=cv2.FILLED)
    return out
