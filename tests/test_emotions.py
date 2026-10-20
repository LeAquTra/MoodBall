from __future__ import annotations

from services.emotions import (
    allowed_ids,
    apply_emotion_proposal,
    clean_emotion_id,
    propose_emotion,
)


def test_catalog_has_33_ids() -> None:
    assert len(allowed_ids()) == 33
    assert "02" in allowed_ids()
    assert "50" in allowed_ids()


def test_clean_emotion_id_falls_back() -> None:
    assert clean_emotion_id("99") == "02"
    assert clean_emotion_id("10") == "10"
    assert clean_emotion_id(None, "34") == "34"


def test_tired_user_gets_sleepy_emotion() -> None:
    proposal = propose_emotion("今天有点累")
    assert proposal["emotionId"] == "15"


def test_error_has_priority() -> None:
    proposal = propose_emotion("今天很开心", error="VISION_CAPTURE: camera busy")
    assert proposal["emotionId"] == "34"
    assert proposal["source"] == "rule"


def test_low_confidence_vision() -> None:
    proposal = propose_emotion("看看这是什么", vision={"confidence": 0.1})
    assert proposal["emotionId"] == "11"


def test_vision_with_objects_gets_curious() -> None:
    proposal = propose_emotion("看看", vision={"confidence": 0.9, "objects": ["杯子"], "scene": "桌上有一个杯子"})
    assert proposal["emotionId"] == "03"


def test_apply_proposal_clamps_intensity() -> None:
    result = apply_emotion_proposal({"emotionId": "10", "intensity": 4.2})
    assert result["emotionId"] == "10"
    assert result["intensity"] == 1.0
    result = apply_emotion_proposal({"emotionId": "bad", "intensity": -2})
    assert result["emotionId"] == "02"
    assert result["intensity"] == 0.0
