"""Provider 档案：chat / vision / tts / asr。"""

from __future__ import annotations

import uuid

from django.db import models


class ProviderProfile(models.Model):
    class Kind(models.TextChoices):
        CHAT = "chat", "chat"
        VISION = "vision", "vision"
        TTS = "tts", "tts"
        ASR = "asr", "asr"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    name = models.CharField(max_length=80)
    base_url = models.URLField(max_length=500)
    model = models.CharField(max_length=200)
    api_key = models.TextField(blank=True)
    extra_json = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "-is_default", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "name"], name="uniq_provider_kind_name"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.kind}:{self.name}"

    def as_dict(self, reveal: bool = False) -> dict:
        from django.conf import settings

        from services.secrets import mask_key

        env_key = (settings.PROVIDER_DEFAULTS.get(self.kind) or {}).get("api_key", "")
        effective_key = self.api_key or env_key
        return {
            "id": str(self.id),
            "kind": self.kind,
            "name": self.name,
            "base_url": self.base_url,
            "model": self.model,
            "api_key": effective_key if reveal else mask_key(effective_key),
            "api_key_set": bool(effective_key),
            "extra": self.extra_json or {},
            "enabled": self.enabled,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
