"""Stream layer: RTSP decode, MediaMTX control, overlay drawing, backpressure.

The building blocks a scenario wires together to go from a live camera to a model
and back to an annotated re-stream:

    RTSPReader        pull decoded BGR frames from an RTSP URL (via FFmpeg)
    MediaMTXClient    register camera paths + build republish URLs
    LatestFrameBuffer drop-oldest buffer so a slow model never lags real time
    draw_detections   render boxes/labels onto a frame (non-mutating)
    draw_landmarks    render keypoints onto a frame (non-mutating)
"""

from __future__ import annotations

from edge.stream.annotate import draw_detections, draw_landmarks
from edge.stream.backpressure import LatestFrameBuffer
from edge.stream.mediamtx import MediaMTXClient
from edge.stream.rtsp import RTSPReader

__all__ = [
    "RTSPReader",
    "MediaMTXClient",
    "draw_detections",
    "draw_landmarks",
    "LatestFrameBuffer",
]
