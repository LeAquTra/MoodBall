"""核心模型：用户设置与运行日志。"""

from __future__ import annotations

import uuid

from django.db import models


class AppSetting(models.Model):
    key = models.CharField(max_length=80, primary_key=True)
    value_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name = "应用设置"
        verbose_name_plural = "应用设置"

    def __str__(self) -> str:  # pragma: no cover
        return self.key


class EventLog(models.Model):
    class Level(models.TextChoices):
        DEBUG = "debug", "debug"
        INFO = "info", "info"
        WARNING = "warning", "warning"
        ERROR = "error", "error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.CharField(max_length=40, default="system")
    action = models.CharField(max_length=120)
    level = models.CharField(max_length=12, choices=Level.choices, default=Level.INFO)
    detail_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["level", "created_at"]),
        ]

    @classmethod
    def log(
        cls,
        action: str,
        *,
        actor: str = "system",
        level: str = Level.INFO,
        detail: dict | None = None,
    ) -> "EventLog":
        return cls.objects.create(
            actor=actor,
            action=action,
            level=level,
            detail_json=detail or {},
        )
