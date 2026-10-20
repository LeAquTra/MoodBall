"""抓帧元数据；图片二进制放 media/images/。"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class ImageAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        "chat.Conversation", on_delete=models.SET_NULL, null=True, blank=True, related_name="images"
    )
    path = models.CharField(max_length=500)
    sha256 = models.CharField(max_length=64, db_index=True)
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    bytes = models.IntegerField(default=0)
    vision_json = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    @property
    def url(self) -> str:
        return f"{settings.MEDIA_URL.rstrip('/')}/{self.path}"

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "url": self.url,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "bytes": self.bytes,
            "vision": self.vision_json or {},
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
        }
