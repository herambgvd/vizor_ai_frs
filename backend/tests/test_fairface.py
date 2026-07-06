"""FairFace age+gender postprocessing over the raw 18-logit vector:
[0:7] race (ignored), [7:9] gender (0=Male,1=Female), [9:18] age (9 buckets)."""

from __future__ import annotations

import numpy as np

from app.recognition.fairface import (
    AGE_BUCKET_LABELS,
    _AGE_BUCKET_MID,
    postprocess_fairface,
)


def _logits(gender=(0.0, 0.0), age_idx=0, age_peak=6.0):
    v = np.zeros(18, dtype=np.float32)
    v[7], v[8] = gender
    v[9 + age_idx] = age_peak  # dominate one age bucket
    return v


def test_confident_male():
    out = postprocess_fairface(_logits(gender=(6.0, 0.0), age_idx=3))
    assert out["gender"] == "male"
    assert out["gender_confidence"] > 0.65
    assert out["age_range"] == AGE_BUCKET_LABELS[3] == "20-29"
    assert out["age"] == _AGE_BUCKET_MID[3] == 25


def test_confident_female():
    out = postprocess_fairface(_logits(gender=(0.0, 6.0), age_idx=5))
    assert out["gender"] == "female"
    assert out["gender_confidence"] > 0.65
    assert out["age_range"] == "40-49"


def test_low_confidence_gender_is_none():
    # Equal gender logits → 0.5 confidence < 0.65 threshold → gender suppressed.
    out = postprocess_fairface(_logits(gender=(0.0, 0.0), age_idx=2))
    assert out["gender"] is None
    assert out["gender_confidence"] == 0.0
    # age is still resolved
    assert out["age_range"] == AGE_BUCKET_LABELS[2]


def test_each_age_bucket_maps():
    for idx, label in enumerate(AGE_BUCKET_LABELS):
        out = postprocess_fairface(_logits(gender=(6.0, 0.0), age_idx=idx))
        assert out["age_range"] == label
        assert out["age"] == _AGE_BUCKET_MID[idx]


def test_short_vector_returns_nulls():
    out = postprocess_fairface(np.zeros(10, dtype=np.float32))
    assert out == {"gender": None, "gender_confidence": 0.0, "age": None, "age_range": None}


def test_male_index_env_override(monkeypatch):
    # FRS_FAIRFACE_MALE_INDEX=1 flips which gender logit maps to "male".
    monkeypatch.setenv("FRS_FAIRFACE_MALE_INDEX", "1")
    out = postprocess_fairface(_logits(gender=(6.0, 0.0), age_idx=0))
    # argmax is index 0, but male_index is now 1 → labelled female.
    assert out["gender"] == "female"


def test_min_conf_env_override(monkeypatch):
    # Lower the threshold so a 0.5-confidence gender is accepted.
    monkeypatch.setenv("FRS_FAIRFACE_MIN_CONF", "0.4")
    out = postprocess_fairface(_logits(gender=(0.0, 0.0), age_idx=0))
    assert out["gender"] is not None
    assert abs(out["gender_confidence"] - 0.5) < 1e-6
