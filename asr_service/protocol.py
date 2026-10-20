"""内部 WebSocket 消息约定（Django ↔ ASR）。"""

from __future__ import annotations

from typing import Any, TypedDict


class ClientMessage(TypedDict, total=False):
    type: str
    session_id: str
    sample_rate: int
    chunk_ms: int
    mode: str
    value: bool


def ready(
    engine: str,
    cuda: bool,
    streaming: bool,
    model: str,
    backend: str | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "ready",
        "engine": engine,
        "cuda": cuda,
        "streaming": streaming,
        "backend": backend,
        "device": device,
        "model": model,
        "sample_rate": 16000,
    }


def partial(text: str, language: str | None = None) -> dict[str, Any]:
    return {"type": "partial", "text": text, "language": language}


def final(text: str, language: str | None = None, reason: str = "finish") -> dict[str, Any]:
    return {"type": "final", "text": text, "language": language, "reason": reason}


def error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message, "retryable": retryable}


def status(state: str, message: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "asr_status", "state": state}
    if message:
        payload["message"] = message
    return payload
