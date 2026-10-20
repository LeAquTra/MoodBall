from __future__ import annotations

from types import SimpleNamespace

from asr_service.engine import ASREngine


def test_normalize_transformers_result() -> None:
    engine = ASREngine()
    assert engine._normalize_result([SimpleNamespace(text=" 你好，小球 ")]) == "你好，小球"
    assert engine._normalize_result(SimpleNamespace(text="hello")) == "hello"
    assert engine._normalize_result(" raw ") == "raw"
    assert engine._normalize_result({"text": "dict"}) == "dict"
    assert engine._normalize_result([]) == ""


def test_model_path_resolution() -> None:
    engine = ASREngine()
    assert engine.model_path.endswith("Qwen3-ASR-0.6B")
    assert engine.max_batch >= 1
    assert engine.max_new_tokens >= 32
