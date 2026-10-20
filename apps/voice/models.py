"""TTS 缓存与语音会话。"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class TTSAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text_hash = models.CharField(max_length=64, unique=True)
    text = models.TextField()
    voice = models.CharField(max_length=80, blank=True)
    model = models.CharField(max_length=120, blank=True)
    path = models.CharField(max_length=500)
    format = models.CharField(max_length=12, default="wav")
    bytes = models.IntegerField(default=0)
    duration_ms = models.IntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_used_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def url(self) -> str:
        return f"/api/audio/{self.id}/"

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "url": self.url,
            "text": self.text,
            "voice": self.voice,
            "model": self.model,
            "format": self.format,
            "bytes": self.bytes,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat(),
        }


class VoiceSession(models.Model):
    class Status(models.TextChoices):
        CONNECTING = "connecting", "connecting"
        READY = "ready", "ready"
        LISTENING = "listening", "listening"
        CLOSED = "closed", "closed"
        ERROR = "error", "error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        "chat.Conversation", on_delete=models.SET_NULL, null=True, blank=True, related_name="voice_sessions"
    )
    engine = models.CharField(max_length=80, default="qwen3-asr-0.6b")
    mode = models.CharField(max_length=20, default="continuous")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONNECTING)
    wake_count = models.IntegerField(default=0)
    final_count = models.IntegerField(default=0)
    error = models.TextField(blank=True)
    meta_json = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "engine": self.engine,
            "mode": self.mode,
            "status": self.status,
            "wake_count": self.wake_count,
            "final_count": self.final_count,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }
