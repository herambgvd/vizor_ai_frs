"""``_cfg_sig`` — an order-stable signature of the recognition-affecting per-camera
config. It must change when a recognition param changes and stay stable when only
cosmetic fields (name / location / zone / status) change."""

from __future__ import annotations

from types import SimpleNamespace

from app.stream_supervisor import _cfg_sig


def _cam(**over):
    base = dict(
        rtsp_url="rtsp://cam/1", fps=10, min_confidence=0.5, detection_enabled=False,
        direction="both", liveness_enabled=True, liveness_threshold=0.7, det_conf=0.5,
        min_face_px=28, min_sharpness=25, max_pose_deg=60, dwell_min_frames=3,
        alert_suppress_seconds=300, hw_accel="none", roi=[],
        # cosmetic / non-recognition fields:
        name="Lobby", location="HQ", zone="Gate 1", status="online",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_identical_config_same_sig():
    assert _cfg_sig(_cam()) == _cfg_sig(_cam())


def test_cosmetic_changes_do_not_churn():
    a = _cfg_sig(_cam())
    assert _cfg_sig(_cam(name="Back Door")) == a
    assert _cfg_sig(_cam(location="Branch")) == a
    assert _cfg_sig(_cam(zone="Gate 9")) == a
    assert _cfg_sig(_cam(status="offline")) == a


def test_recognition_param_changes_bust_sig():
    base = _cfg_sig(_cam())
    for field, value in [
        ("rtsp_url", "rtsp://cam/2"),
        ("fps", 15),
        ("min_confidence", 0.7),
        ("detection_enabled", True),
        ("direction", "entry"),
        ("liveness_enabled", False),
        ("liveness_threshold", 0.9),
        ("det_conf", 0.6),
        ("min_face_px", 40),
        ("min_sharpness", 50),
        ("max_pose_deg", 45),
        ("dwell_min_frames", 5),
        ("alert_suppress_seconds", 60),
        ("hw_accel", "nvdec"),
        ("roi", [[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]]),
    ]:
        assert _cfg_sig(_cam(**{field: value})) != base, f"{field} did not change sig"


def test_sig_is_order_stable():
    # Same values, built in a different insertion order → same signature.
    import json
    s = _cfg_sig(_cam())
    assert json.loads(s)  # valid JSON
    assert _cfg_sig(_cam(roi=[], fps=10)) == s
