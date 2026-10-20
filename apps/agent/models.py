"""Agent 运行记录与工具调用。"""

from __future__ import annotations

import uuid

from django.db import models


class AgentRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "running"
        OK = "ok", "ok"
        ERROR = "error", "error"
        FALLBACK = "fallback", "fallback"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        "chat.Conversation", on_delete=models.CASCADE, related_name="agent_runs"
    )
    thread_id = models.CharField(max_length=80, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    intent = models.CharField(max_length=20, blank=True)
    user_text = models.TextField(blank=True)
    reply = models.TextField(blank=True)
    emotion_id = models.CharField(max_length=4, blank=True)
    error = models.TextField(blank=True)
    latency_ms = models.IntegerField(default=0)
    trace_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "thread_id": self.thread_id,
            "status": self.status,
            "intent": self.intent,
            "user_text": self.user_text,
            "reply": self.reply,
            "emotion_id": self.emotion_id,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "trace": self.trace_json or {},
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class ToolCall(models.Model):
    class Status(models.TextChoices):
        OK = "ok", "ok"
        ERROR = "error", "error"
        TIMEOUT = "timeout", "timeout"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="tool_calls")
    name = models.CharField(max_length=200)
    source = models.CharField(max_length=20, default="builtin")
    server_name = models.CharField(max_length=80, blank=True)
    args_json = models.JSONField(default=dict, blank=True)
    result_json = models.JSONField(default=dict, blank=True)
    result_preview = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OK)
    duration_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["name", "created_at"])]

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "run_id": str(self.run_id),
            "name": self.name,
            "source": self.source,
            "server": self.server_name,
            "args": self.args_json or {},
            "result": self.result_json or {},
            "result_preview": self.result_preview,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat(),
        }
