"""对话与记忆模型。"""

from __future__ import annotations

import uuid

from django.db import models


class Conversation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "active"
        ARCHIVED = "archived", "archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["-updated_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return self.title or str(self.id)

    def as_dict(self, with_messages: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "title": self.title or "新对话",
            "status": self.status,
            "summary": self.summary,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": getattr(self, "message_count", None),
        }
        if with_messages:
            data["messages"] = [message.as_dict() for message in self.messages.all()]
        return data


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "user"
        ASSISTANT = "assistant", "assistant"
        TOOL = "tool", "tool"
        SYSTEM = "system", "system"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    emotion_id = models.CharField(max_length=4, blank=True)
    image_id = models.UUIDField(null=True, blank=True)
    audio_id = models.UUIDField(null=True, blank=True)
    tokens_in = models.IntegerField(default=0)
    tokens_out = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    meta_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["conversation", "role"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.role}: {self.content[:40]}"

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "role": self.role,
            "content": self.content,
            "emotion_id": self.emotion_id,
            "image_id": str(self.image_id) if self.image_id else None,
            "audio_id": str(self.audio_id) if self.audio_id else None,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
            "meta": self.meta_json or {},
            "created_at": self.created_at.isoformat(),
        }


class EmotionEvent(models.Model):
    class Source(models.TextChoices):
        STATE = "state", "state"
        RULE = "rule", "rule"
        LLM = "llm", "llm"
        INTERACTION = "interaction", "interaction"
        FALLBACK = "fallback", "fallback"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, null=True, blank=True, related_name="emotion_events"
    )
    message = models.ForeignKey(
        Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="emotion_events"
    )
    emotion_id = models.CharField(max_length=4)
    intensity = models.FloatField(default=0.5)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.RULE)
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "message_id": str(self.message_id) if self.message_id else None,
            "emotion_id": self.emotion_id,
            "intensity": self.intensity,
            "source": self.source,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


class MemoryFact(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "manual"
        AGENT = "agent", "agent"
        AUTO = "auto", "auto"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="memory_facts"
    )
    fact = models.TextField()
    tags = models.CharField(max_length=300, blank=True)
    confidence = models.FloatField(default=0.7)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    pinned = models.BooleanField(default=False)
    use_count = models.IntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tags"]),
            models.Index(fields=["pinned", "-created_at"]),
            models.Index(fields=["-last_used_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.fact[:40]

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "fact": self.fact,
            "tags": self.tags,
            "tag_list": [item for item in (self.tags or "").replace("，", ",").split(",") if item.strip()],
            "confidence": self.confidence,
            "source": self.source,
            "pinned": self.pinned,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
