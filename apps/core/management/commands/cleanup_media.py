"""清理过期抓帧 / TTS 音频，以及没有数据库引用的孤儿文件。"""

from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.vision.models import ImageAsset
from apps.voice.models import TTSAsset


class Command(BaseCommand):
    help = "清理过期图片 / TTS 音频 / 孤儿文件。先删文件再删数据库记录。"

    def add_arguments(self, parser):
        parser.add_argument("--image-days", type=int, default=settings.IMAGE_RETENTION_DAYS)
        parser.add_argument("--audio-days", type=int, default=settings.AUDIO_RETENTION_DAYS)
        parser.add_argument("--orphan", action="store_true", help="同时删除数据库没有引用的文件")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        now = timezone.now()
        dry = options["dry_run"]
        image_cutoff = now - timedelta(days=max(1, options["image_days"]))
        audio_cutoff = now - timedelta(days=max(1, options["audio_days"]))

        image_count = 0
        images = ImageAsset.objects.filter(Q(expires_at__lt=now) | Q(created_at__lt=image_cutoff))
        for asset in images.iterator():
            path = settings.MEDIA_ROOT / asset.path
            self.stdout.write(f"image: {asset.path}")
            if not dry:
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    self.stderr.write(f"  删除文件失败：{exc}")
                asset.delete()
            image_count += 1

        audio_count = 0
        audios = TTSAsset.objects.filter(Q(expires_at__lt=now) | Q(created_at__lt=audio_cutoff))
        for asset in audios.iterator():
            path = settings.MEDIA_ROOT / asset.path
            self.stdout.write(f"audio: {asset.path}")
            if not dry:
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    self.stderr.write(f"  删除文件失败：{exc}")
                asset.delete()
            audio_count += 1

        orphan_count = 0
        if options["orphan"]:
            orphan_count = self._cleanup_orphans(dry)

        self.stdout.write(
            self.style.SUCCESS(
                f"完成：图片 {image_count}，音频 {audio_count}，孤儿 {orphan_count}"
                + ("（dry-run，未真正删除）" if dry else "")
            )
        )

    def _cleanup_orphans(self, dry: bool) -> int:
        referenced = set(ImageAsset.objects.values_list("path", flat=True))
        referenced.update(TTSAsset.objects.values_list("path", flat=True))
        root: Path = settings.MEDIA_ROOT
        count = 0
        if not root.exists():
            return 0
        for path in list(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative in referenced:
                continue
            # 刚写入的文件留 1 小时缓冲，避免和正在进行的请求竞争。
            if time.time() - path.stat().st_mtime < 3600:
                continue
            self.stdout.write(f"orphan: {relative}")
            if not dry:
                try:
                    path.unlink()
                except OSError as exc:
                    self.stderr.write(f"  删除失败：{exc}")
                    continue
            count += 1
        return count
