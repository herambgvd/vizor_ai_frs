"""ROI helpers in the stream supervisor: normalisation of the stored ROI shapes
and ray-cast point-in-polygon."""

from __future__ import annotations

from app.stream_supervisor import _normalize_roi, _point_in_any_roi

# A unit square in 0..1 normalised coords.
SQUARE = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


# ── _normalize_roi ──────────────────────────────────────────────────────────────
def test_normalize_empty_returns_none():
    assert _normalize_roi(None) is None
    assert _normalize_roi([]) is None
    assert _normalize_roi("") is None


def test_normalize_flat_polygon_is_wrapped():
    # [[x,y],...] → wrapped as one polygon in a list.
    assert _normalize_roi(SQUARE) == [SQUARE]


def test_normalize_dict_polygons_passthrough():
    raw = [{"points": SQUARE}]
    assert _normalize_roi(raw) == raw


# ── _point_in_any_roi ───────────────────────────────────────────────────────────
def test_point_inside_flat_polygon():
    polys = _normalize_roi(SQUARE)
    assert _point_in_any_roi(0.5, 0.5, polys) is True


def test_point_outside_flat_polygon():
    polys = _normalize_roi(SQUARE)
    assert _point_in_any_roi(0.05, 0.05, polys) is False
    assert _point_in_any_roi(0.95, 0.5, polys) is False


def test_point_inside_dict_polygon():
    polys = _normalize_roi([{"points": SQUARE}])
    assert _point_in_any_roi(0.5, 0.5, polys) is True
    assert _point_in_any_roi(0.9, 0.9, polys) is False


def test_multiple_polygons_any_match():
    left = [[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]]
    right = [[0.8, 0.8], [1.0, 0.8], [1.0, 1.0], [0.8, 1.0]]
    polys = [left, right]
    assert _point_in_any_roi(0.1, 0.1, polys) is True   # in left
    assert _point_in_any_roi(0.9, 0.9, polys) is True   # in right
    assert _point_in_any_roi(0.5, 0.5, polys) is False  # between


def test_degenerate_polygon_ignored():
    # Fewer than 3 points is not a polygon → never inside.
    assert _point_in_any_roi(0.5, 0.5, [[[0.1, 0.1], [0.9, 0.9]]]) is False


def test_empty_polygons_never_inside():
    assert _point_in_any_roi(0.5, 0.5, None) is False
    assert _point_in_any_roi(0.5, 0.5, []) is False
