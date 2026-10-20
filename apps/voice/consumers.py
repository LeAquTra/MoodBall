"""语音 WebSocket consumer：音频转发、唤醒匹配、阶段事件。"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from apps.core.settings_service import get_settings
from services.asr_client import AsrSession
from services.wake import WakeMatcher, normalize

logger = logging.getLogger("moodball.voice")


class VoiceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self._closed = False
        self.phase = "idle"
        self.muted = False
        self.ptt = False
        self.matcher: WakeMatcher | None = None
        self.asr: AsrSession | None = None
        self.session_id: str | None = None
        self.conversation_id: str | None = None
        self.wake_count = 0
        self.final_count = 0
        self._command_task: asyncio.Task | None = None
        self._pump_task: asyncio.Task | None = None
        self._audio_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._suppress_partial_until = 0.0
        await self._send_json(
            {
                "type": "hello",
                "engine": "qwen3-asr",
                "sample_rate": 16000,
                "chunk_ms": settings.ASR_CHUNK_MS,
                "asr_enabled": settings.ASR_ENABLED,
            }
        )

    async def disconnect(self, code):
        self._closed = True
        await self._cancel_command_timer()
        if self._pump_task is not None:
            self._pump_task.cancel()
            self._pump_task = None
        if self.asr is not None:
            await self.asr.close()
            self.asr = None
        await self._close_session()

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None:
            if self._closed:
                return
            if self._audio_queue.full():
                try:
                    self._audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                self._audio_queue.put_nowait(bytes_data)
            except asyncio.QueueFull:
                pass
            return

        try:
            message = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        kind = message.get("type")
        if kind == "start":
            await self._handle_start(message)
        elif kind == "mute":
            self.muted = bool(message.get("value"))
            if self.asr is not None:
                await self.asr.send_control({"value": self.muted})
        elif kind == "ptt_start":
            await self._handle_ptt_start()
        elif kind == "ptt_stop":
            await self._handle_ptt_stop()
        elif kind == "stop":
            await self._handle_stop()
        elif kind == "ping":
            await self._send_json({"type": "pong"})

    # ------------------------------------------------------------------
    async def _handle_start(self, message: dict) -> None:
        if self.asr is not None:
            await self.asr.close()
        await self._cancel_command_timer()
        self.conversation_id = message.get("conversation_id") or None
        self.phase = "wake"
        self.ptt = False
        self.wake_count = 0
        self.final_count = 0
        self._suppress_partial_until = 0.0

        app_settings = await sync_to_async(get_settings, thread_sensitive=True)()
        self.matcher = WakeMatcher(
            wake_word=message.get("wake_word") or app_settings.get("wake_word") or settings.WAKE_WORD,
            variants=app_settings.get("wake_variants") or settings.WAKE_VARIANTS,
            confirm_hits=int(app_settings.get("wake_confirm_hits") or settings.WAKE_CONFIRM_HITS),
            cooldown_ms=int(app_settings.get("wake_cooldown_ms") or settings.WAKE_COOLDOWN_MS),
        )
        self.session_id = await self._create_session(message)
        self.asr = AsrSession(
            self._on_asr_event,
            {
                "session_id": self.session_id,
                "conversation_id": self.conversation_id,
                "mode": message.get("mode", "continuous"),
            },
        )
        await self._send_json(
            {
                "type": "phase",
                "value": "arming",
                "wake_word": self.matcher.wake_word,
            }
        )
        started = await self.asr.start()
        if self._pump_task is None or self._pump_task.done():
            self._pump_task = asyncio.create_task(self._pump_audio())
        if not started:
            await self._send_json({"type": "phase", "value": "idle"})

    async def _handle_ptt_start(self) -> None:
        if self.asr is None:
            await self._send_json(
                {
                    "type": "error",
                    "code": "ASR_NOT_STARTED",
                    "message": "语音会话还没开始，请先点击麦克风。",
                    "retryable": True,
                }
            )
            return
        await self._cancel_command_timer()
        self.ptt = True
        self.phase = "command"
        await self._send_json({"type": "phase", "value": "listening", "mode": "ptt"})

    async def _handle_ptt_stop(self) -> None:
        if self.asr is not None:
            self.ptt = False
            await self.asr.finish()
            self.phase = "command"
            await self._send_json({"type": "phase", "value": "thinking", "mode": "ptt"})

    async def _handle_stop(self) -> None:
        await self._cancel_command_timer()
        if self.asr is not None:
            await self.asr.close()
            self.asr = None
        self.phase = "idle"
        await self._send_json({"type": "phase", "value": "idle"})

    async def _pump_audio(self) -> None:
        try:
            while not self._closed:
                data = await self._audio_queue.get()
                if self.asr is None or self.muted or self.phase == "idle":
                    continue
                await self.asr.send_audio(data)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.debug("audio pump ended", exc_info=True)

    # ------------------------------------------------------------------
    async def _on_asr_event(self, event: dict) -> None:
        if self._closed:
            return
        kind = event.get("type")
        if self.muted and kind in {"partial", "final", "speech_start", "speech_end"}:
            return
        if kind == "ready":
            self.phase = "wake" if self.phase == "idle" else self.phase
            await self._send_json(
                {
                    "type": "ready",
                    "engine": event.get("engine", "qwen3-asr-0.6b"),
                    "sample_rate": event.get("sample_rate", 16000),
                    "cuda": event.get("cuda"),
                }
            )
            await self._send_json({"type": "phase", "value": "armed"})
            return
        if kind == "partial":
            await self._handle_partial(event)
            return
        if kind == "final":
            await self._handle_final(event)
            return
        if kind in {"asr_status", "error", "speech_start", "speech_end"}:
            await self._send_json(event)
            return
        await self._send_json(event)

    async def _handle_partial(self, event: dict) -> None:
        text = str(event.get("text") or "")
        if not text:
            return
        # 刚发送 final 后的尾部 partial 不再展示，避免唤醒词/旧文本闪回。
        if time.monotonic() < self._suppress_partial_until:
            return
        if self.ptt or self.phase == "command":
            await self._send_json({"type": "partial", "text": text, "phase": "command"})
            return
        await self._send_json({"type": "partial", "text": text, "phase": "wake"})
        if self.phase == "wake" and self.matcher is not None:
            hit = self.matcher.feed(text, final=False)
            if hit is not None:
                await self._on_wake(hit)

    async def _handle_final(self, event: dict) -> None:
        text = str(event.get("text") or "")
        if self.ptt:
            self.ptt = False
            await self._send_command(text, reason="ptt")
            return
        if self.phase == "command":
            command = self._command_text(text)
            await self._send_command(command, reason=event.get("reason") or "vad")
            return
        if self.phase == "wake" and self.matcher is not None:
            hit = self.matcher.feed(text, final=True)
            if hit is not None:
                await self._on_wake(hit)
                return
            self.matcher.reset_confirmation()

    async def _on_wake(self, hit) -> None:
        self.phase = "command"
        self.wake_count += 1
        await self._send_json(
            {
                "type": "wake",
                "heard": hit.heard,
                "remainder": hit.remainder,
                "session": self.session_id,
            }
        )
        await self._send_json({"type": "phase", "value": "listening"})
        await self._increment_session("wake_count")
        if hit.remainder and len(hit.remainder) >= 2:
            await self._send_command(hit.remainder, reason="wake_remainder")
        else:
            await self._schedule_command_timeout()

    async def _send_command(self, command: str, reason: str = "vad") -> None:
        command = normalize(command)
        await self._cancel_command_timer()
        self.phase = "wake"
        if self.matcher is not None:
            self.matcher.reset_confirmation()
        if not command:
            await self._send_json({"type": "phase", "value": "armed"})
            return
        self.final_count += 1
        self._suppress_partial_until = time.monotonic() + 2.0
        await self._increment_session("final_count")
        await self._send_json(
            {
                "type": "final",
                "text": command,
                "phase": "command",
                "reason": reason,
            }
        )
        await self._send_json({"type": "phase", "value": "thinking"})
        # VAD 已在 ASR 服务侧 finish 并 reset；只有显式 finish 的场景才需要重置流。
        if self.asr is not None and reason != "vad":
            await self.asr.finish()

    def _command_text(self, final_text: str) -> str:
        if self.matcher is None:
            return normalize(final_text)
        hit = self.matcher.detect(final_text, final=True)
        return hit.remainder if hit is not None else normalize(final_text)

    async def _schedule_command_timeout(self) -> None:
        await self._cancel_command_timer()

        async def _timeout() -> None:
            try:
                await asyncio.sleep(settings.COMMAND_TIMEOUT_MS / 1000.0)
                if self.phase == "command" and not self.ptt:
                    self.phase = "wake"
                    await self._send_json(
                        {"type": "phase", "value": "armed", "reason": "command_timeout"}
                    )
            except asyncio.CancelledError:
                return

        self._command_task = asyncio.create_task(_timeout())

    async def _cancel_command_timer(self) -> None:
        if self._command_task is not None:
            self._command_task.cancel()
            try:
                await self._command_task
            except (asyncio.CancelledError, Exception):
                pass
            self._command_task = None

    # ------------------------------------------------------------------
    async def _send_json(self, payload: dict) -> None:
        if self._closed:
            return
        try:
            await self.send(text_data=json.dumps(payload, ensure_ascii=False))
        except Exception:
            self._closed = True

    async def _create_session(self, message: dict) -> str | None:
        from apps.voice.models import VoiceSession

        conversation_id = message.get("conversation_id") or None
        mode = message.get("mode", "continuous")
        engine = "qwen3-asr-0.6b"

        def _create():
            session = VoiceSession.objects.create(
                conversation_id=conversation_id if conversation_id else None,
                mode=mode,
                engine=engine,
                status=VoiceSession.Status.CONNECTING,
            )
            return str(session.id)

        try:
            return await sync_to_async(_create, thread_sensitive=True)()
        except Exception:
            logger.warning("create voice session failed", exc_info=True)
            return None

    async def _increment_session(self, field: str) -> None:
        if not self.session_id:
            return
        from apps.voice.models import VoiceSession

        def _update():
            session = VoiceSession.objects.filter(pk=self.session_id).first()
            if session is None:
                return
            setattr(session, field, getattr(session, field) + 1)
            session.status = VoiceSession.Status.LISTENING
            session.save(update_fields=[field, "status"])

        try:
            await sync_to_async(_update, thread_sensitive=True)()
        except Exception:
            logger.debug("update voice session failed", exc_info=True)

    async def _close_session(self) -> None:
        if not self.session_id:
            return
        from django.utils import timezone

        from apps.voice.models import VoiceSession

        session_id = self.session_id
        self.session_id = None

        def _close():
            session = VoiceSession.objects.filter(pk=session_id).first()
            if session is None:
                return
            session.status = VoiceSession.Status.CLOSED
            session.ended_at = timezone.now()
            session.save(update_fields=["status", "ended_at"])

        try:
            await sync_to_async(_close, thread_sensitive=True)()
        except Exception:
            logger.debug("close voice session failed", exc_info=True)
