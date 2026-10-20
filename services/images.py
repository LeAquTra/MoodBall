"""图片落盘与元数据。"""

from __future__ import annotations

import hashlib
import io
import logging
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("moodball.images")


def _image_dir() -> Path:
    path = settings.MEDIA_ROOT / "images" / timezone.localdate().strftime("%Y%m%d")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_image(jpeg: bytes, conversation_id=None, vision: dict | None = None):
    from apps.vision.models import ImageAsset

    if not jpeg:
        raise ValueError("empty image")
    digest = hashlib.sha256(jpeg).hexdigest()

    # 同一会话一分钟内相同图片直接复用，避免连续抓帧生成大量重复文件。
    recent = None
    if conversation_id:
        recent = (
            ImageAsset.objects.filter(
                conversation_id=conversation_id,
                sha256=digest,
                created_at__gte=timezone.now() - timedelta(minutes=1),
            )
            .order_by("-created_at")
            .first()
        )
    if recent and (settings.MEDIA_ROOT / recent.path).exists():
        if vision:
            recent.vision_json = vision
            recent.save(update_fields=["vision_json"])
        return recent

    width = height = 0
    try:
        from PIL import Image

        with Image.open(io.BytesIO(jpeg)) as image:
            width, height = image.size
    except Exception as exc:  # pragma: no cover
        logger.warning("read image size failed: %s", exc)

    target = _image_dir() / f"{digest[:24]}.jpg"
    target.write_bytes(jpeg)
    relative = target.relative_to(settings.MEDIA_ROOT).as_posix()

    asset = ImageAsset.objects.create(
        conversation_id=conversation_id or None,
        path=relative,
        sha256=digest,
        width=width,
        height=height,
        bytes=len(jpeg),
        vision_json=vision or {},
        expires_at=timezone.now() + timedelta(days=settings.IMAGE_RETENTION_DAYS),
    )
    return asset


def delete_expired_images(days: int | None = None) -> int:
    from apps.vision.models import ImageAsset

    now = timezone.now()
    queryset = ImageAsset.objects.all()
    if days is None:
        queryset = queryset.filter(expires_at__lt=now)
    else:
        queryset = queryset.filter(created_at__lt=now - timedelta(days=days))
    deleted = 0
    for asset in queryset.iterator():
        path = settings.MEDIA_ROOT / asset.path
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        asset.delete()
        deleted += 1
    return deleted
