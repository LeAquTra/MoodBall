"""Django ↔ ASR 服务的 WebSocket 客户端。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from django.conf import settings

logger = logging.getLogger("moodball.asr")

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None  # type: ignore[assignment]

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class AsrSession:
    """一条音频流对应一个 ASR session；断线只上报状态，不在后台无限重连。"""

    def __init__(self, on_event: EventCallback, start_payload: dict | None = None) -> None:
        self.on_event = on_event
        self.start_payload = start_payload or {}
        self.session_id = uuid.uuid4().hex
        self._ws = None
        self._receiver: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False
        self.ready = False

    async def _emit(self, event: dict) -> None:
        try:
            await self.on_event(event)
        except Exception:  # pragma: no cover - 客户端已断开
            logger.debug("asr event dropped", exc_info=True)

    async def start(self) -> bool:
        if not settings.ASR_ENABLED:
            await self._emit(
                {
                    "type": "asr_status",
                    "state": "disabled",
                    "message": "ASR 已关闭，请使用 PTT 或文字输入。",
                }
            )
            return False
        if websockets is None:
            await self._emit(
                {
                    "type": "asr_status",
                    "state": "error",
                    "message": "缺少 websockets 依赖，无法连接 ASR 服务。",
                }
            )
            return False

        await self._emit({"type": "asr_status", "state": "connecting"})
        try:
            self._ws = await websockets.connect(
                settings.ASR_WS_URL,
                open_timeout=settings.ASR_CONNECT_TIMEOUT,
                close_timeout=2,
                max_size=2 * 1024 * 1024,
            )
            payload = {
                "type": "start",
                "session_id": self.session_id,
                "sample_rate": 16000,
                "chunk_ms": settings.ASR_CHUNK_MS,
                **self.start_payload,
            }
            await self._ws.send(json.dumps(payload, ensure_ascii=False))
            self._receiver = asyncio.create_task(self._receive_loop())
            return True
        except Exception as exc:
            self._ws = None
            logger.warning("asr connect failed: %s", exc)
            await self._emit(
                {
                    "type": "asr_status",
                    "state": "error",
                    "message": f"ASR 服务未连接：{exc}。可继续用 PTT / 文字。",
                }
            )
            return False

    async def _receive_loop(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    continue
                try:
                    event = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "ready":
                    self.ready = True
                await self._emit(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closed:
                logger.info("asr stream ended: %s", exc)
                await self._emit(
                    {
                        "type": "asr_status",
                        "state": "error",
                        "message": f"ASR 连接中断：{exc}",
                    }
                )
        finally:
            if not self._closed:
                await self._emit({"type": "asr_status", "state": "closed"})

    async def send_audio(self, data: bytes) -> None:
        if self._closed or self._ws is None or not self.ready:
            return
        async with self._send_lock:
            try:
                await self._ws.send(data)
            except Exception:
                self._closed = True

    async def send_control(self, payload: dict) -> None:
        if self._closed or self._ws is None:
            return
        async with self._send_lock:
            try:
                await self._ws.send(json.dumps({"type": "mute", **payload}, ensure_ascii=False))
            except Exception:
                self._closed = True

    async def finish(self) -> None:
        if self._closed or self._ws is None:
            return
        async with self._send_lock:
            try:
                await self._ws.send(json.dumps({"type": "finish"}))
            except Exception:
                pass

    async def close(self) -> None:
        self._closed = True
        if self._receiver is not None:
            self._receiver.cancel()
            try:
                await self._receiver
            except (asyncio.CancelledError, Exception):
                pass
            self._receiver = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None


async def asr_health() -> dict:
    if not settings.ASR_ENABLED:
        return {"ok": False, "enabled": False, "message": "ASR 已关闭"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.ASR_BASE_URL}/health")
        data = response.json() if "json" in response.headers.get("content-type", "") else {}
        return {"ok": response.status_code < 400, "status": response.status_code, **data}
    except Exception as exc:
        return {"ok": False, "enabled": True, "message": f"ASR 未连接：{exc}"}
