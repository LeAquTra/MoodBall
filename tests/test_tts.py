from __future__ import annotations

import io
import struct
import wave
from types import SimpleNamespace

from django.conf import settings

from services.tts import _base_url, _candidate_bases, _fix_wav_header, _wav_duration, split_sentences, text_hash


def test_split_sentences() -> None:
    parts = split_sentences("你好。今天好吗？\n我很好！")
    assert len(parts) == 3
    assert parts[0] == "你好。"
    assert parts[1] == "今天好吗？"


def test_split_long_sentence() -> None:
    text = "一" * 25
    parts = split_sentences(text, max_chars=10)
    assert [len(part) for part in parts] == [10, 10, 5]


def test_hash_changes_with_voice() -> None:
    base = text_hash("你好", "qwen3-tts-flash", "Cherry", "wav", "dashscope-mm")
    other = text_hash("你好", "qwen3-tts-flash", "Ethan", "wav", "dashscope-mm")
    assert base != other
    assert base == text_hash("你好", "qwen3-tts-flash", "Cherry", "wav", "dashscope-mm")


def test_empty_text_returns_no_parts() -> None:
    assert split_sentences("   ") == []


def test_streaming_wav_header_is_repaired() -> None:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 2400)
    data = bytearray(buffer.getvalue())
    # CosyVoice 流式 WAV 的 RIFF/data 长度常是占位值。
    struct.pack_into("<I", data, 4, 0x40000000)
    struct.pack_into("<I", data, 40, 0x40000000)
    fixed = _fix_wav_header(bytes(data))
    assert _wav_duration(fixed) == 100
    with wave.open(io.BytesIO(fixed), "rb") as handle:
        assert handle.getnframes() == 2400


def test_workspace_speech_protocol_prefers_workspace_base() -> None:
    profile = SimpleNamespace(
        base_url="https://dashscope.aliyuncs.com/api/v1",
        extra_json={
            "protocol": "dashscope-speech",
            "workspace_base_url": settings.DASHSCOPE_WORKSPACE_BASE_URL,
        },
    )
    if not settings.DASHSCOPE_WORKSPACE_BASE_URL:
        return
    assert _base_url(profile, "dashscope-speech") == settings.DASHSCOPE_WORKSPACE_BASE_URL
    bases = _candidate_bases(profile, "dashscope-speech")
    assert bases[0] == settings.DASHSCOPE_WORKSPACE_BASE_URL
    assert "https://dashscope.aliyuncs.com/api/v1" in bases
