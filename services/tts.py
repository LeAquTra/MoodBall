"""百炼 TTS 适配：分句、缓存、下载到本地。

支持两种协议：
- dashscope-mm：Qwen3-TTS（/services/aigc/multimodal-generation/generation）
- dashscope-speech：Qwen-Audio-TTS / CosyVoice（/services/audio/tts/SpeechSynthesizer）
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import re
import struct
import time
import wave
from datetime import timedelta
from pathlib import Path

import httpx
from django.conf import settings
from django.utils import timezone

from services.base import ProviderError, ProviderNotConfigured

logger = logging.getLogger("moodball.tts")

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\n])")


def split_sentences(text: str, max_chars: int | None = None) -> list[str]:
    """按中文句末标点 / 换行分句，并保证每段不超过 max_chars。"""
    limit = max_chars or settings.TTS_MAX_CHARS
    cleaned = re.sub(r"[ \t]+", " ", (text or "").strip())
    if not cleaned:
        return []
    parts = [part.strip() for part in _SENTENCE_END.split(cleaned) if part.strip()]
    result: list[str] = []
    for part in parts:
        while len(part) > limit:
            result.append(part[:limit])
            part = part[limit:]
        if part:
            result.append(part)
    return result


def text_hash(text: str, model: str, voice: str, fmt: str, protocol: str) -> str:
    raw = f"{protocol}|{model}|{voice}|{fmt}|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _audio_dir() -> Path:
    path = settings.MEDIA_ROOT / "tts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _wav_duration(data: bytes) -> int:
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate() or 1
            channels = handle.getnchannels() or 1
            width = handle.getsampwidth() or 2
            bytes_per_frame = max(1, channels * width)
            # 流式 WAV 的 nframes 可能是占位值（例如 1073741773）；按实际文件大小修正。
            expected = max(0, (len(data) - 44) // bytes_per_frame)
            if frames <= 0 or frames > expected * 1.2 + 1:
                frames = expected
            return int(frames / rate * 1000)
    except Exception:
        return 0


def _fix_wav_header(data: bytes) -> bytes:
    """CosyVoice 流式 WAV 的 RIFF/data 长度常是占位值，播放器可能解码失败。"""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data
    position = 12
    while position + 8 <= len(data):
        chunk_id = data[position : position + 4]
        chunk_size = struct.unpack("<I", data[position + 4 : position + 8])[0]
        if chunk_id == b"data":
            actual = max(0, len(data) - position - 8)
            if chunk_size != actual:
                fixed = bytearray(data)
                struct.pack_into("<I", fixed, position + 4, actual)
                struct.pack_into("<I", fixed, 4, len(fixed) - 8)
                return bytes(fixed)
            return data
        if chunk_size <= 0 or position + 8 + chunk_size > len(data):
            break
        position += 8 + chunk_size + (chunk_size % 2)
    return data


def _estimate_duration(text: str) -> int:
    return int(max(400, len(text) / 4.2 * 1000))


def _workspace_base(profile=None) -> str:
    extra = (profile.extra_json or {}) if profile is not None else {}
    base = extra.get("workspace_base_url") or settings.DASHSCOPE_WORKSPACE_BASE_URL
    return (base or "").rstrip("/")


def _base_url(profile, protocol: str) -> str:
    extra = profile.extra_json or {}
    if protocol == "dashscope-speech" and _workspace_base(profile):
        return _workspace_base(profile)
    return (extra.get("base_url") or profile.base_url or settings.DASHSCOPE_BASE_URL).rstrip("/")


def _endpoint_for_base(base: str, protocol: str) -> str:
    base = (base or "").rstrip("/")
    if base.endswith("/generation") or base.endswith("/SpeechSynthesizer"):
        return base
    if protocol == "dashscope-speech":
        return f"{base}/services/audio/tts/SpeechSynthesizer"
    return f"{base}/services/aigc/multimodal-generation/generation"


def _endpoint(profile, protocol: str) -> str:
    return _endpoint_for_base(_base_url(profile, protocol), protocol)


def _candidate_bases(profile, protocol: str) -> list[str]:
    bases = [_base_url(profile, protocol)]
    workspace = _workspace_base(profile)
    if workspace and workspace not in bases:
        bases.append(workspace)
    standard = (profile.base_url or settings.DASHSCOPE_BASE_URL).rstrip("/")
    if standard and standard not in bases:
        bases.append(standard)
    return bases


def _payload(profile, text: str, voice: str, protocol: str) -> dict:
    extra = profile.extra_json or {}
    if protocol == "dashscope-speech":
        return {
            "model": profile.model,
            "input": {
                "text": text,
                "voice": voice,
                "format": extra.get("format", settings.TTS_FORMAT),
                "sample_rate": int(extra.get("sample_rate", settings.TTS_SAMPLE_RATE)),
            },
        }
    return {
        "model": profile.model,
        "input": {
            "text": text,
            "voice": voice,
            "language_type": extra.get("language_type", "Chinese"),
        },
    }


async def _fetch_audio(profile, text: str, voice: str) -> tuple[bytes, str]:
    if not profile.api_key:
        raise ProviderNotConfigured("tts")
    extra = profile.extra_json or {}
    protocol = extra.get("protocol", settings.TTS_PROTOCOL)
    fmt = extra.get("format", settings.TTS_FORMAT)
    timeout = float(extra.get("timeout", settings.TTS_TIMEOUT))
    headers = {"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}

    if len(text) > settings.TTS_MAX_CHARS:
        text = text[: settings.TTS_MAX_CHARS]

    bases = _candidate_bases(profile, protocol)
    last_error: ProviderError | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        for index, base in enumerate(bases):
            endpoint = _endpoint_for_base(base, protocol)
            try:
                response = await client.post(
                    endpoint, headers=headers, json=_payload(profile, text, voice, protocol)
                )
            except httpx.TimeoutException:
                last_error = ProviderError(
                    "TTS_TIMEOUT", f"TTS 服务响应超时（{base}）", retryable=True
                )
                if index + 1 < len(bases):
                    logger.info("tts base timeout, trying next: %s", base)
                    continue
                raise last_error
            except httpx.HTTPError as exc:
                last_error = ProviderError(
                    "TTS_NETWORK", f"连接 TTS 服务失败（{base}）：{exc}", retryable=True
                )
                if index + 1 < len(bases):
                    logger.info("tts base network error, trying next: %s", base)
                    continue
                raise last_error
            if response.status_code >= 400:
                error = ProviderError(
                    f"TTS_HTTP_{response.status_code}",
                    f"TTS 服务返回 {response.status_code}（{base}）：{response.text[:300]}",
                    retryable=response.status_code in {408, 429, 500, 502, 503, 504},
                )
                last_error = error
                # 百炼业务空间 Key 可能只对专属域名有效；鉴权 / 路径失败时换下个域名。
                if response.status_code in {401, 403, 404, 400} and index + 1 < len(bases):
                    logger.info("tts base failed, trying next: %s %s", response.status_code, base)
                    continue
                raise error

            body = response.json()
            audio = body.get("output", {}).get("audio") or {}
            url = audio.get("url") or body.get("output", {}).get("url")
            data_b64 = audio.get("data")
            if url:
                download = await client.get(url, timeout=httpx.Timeout(30.0, connect=10.0))
                if download.status_code >= 400:
                    raise ProviderError("TTS_DOWNLOAD_FAILED", "TTS 音频下载失败", retryable=True)
                return download.content, fmt
            if data_b64:
                return base64.b64decode(data_b64), fmt
            raise ProviderError("TTS_EMPTY", "TTS 响应里没有音频 URL 或数据")

    raise last_error or ProviderError("TTS_EMPTY", "TTS 响应里没有音频 URL 或数据")


async def synthesize_bytes(profile, text: str, voice: str | None = None) -> bytes:
    """不做缓存 / 落库的原始合成，供“测试连接”使用。"""
    data, _ = await _fetch_with_retry(
        profile, text, voice or (profile.extra_json or {}).get("voice", settings.TTS_VOICE)
    )
    return _fix_wav_header(data)


async def _fetch_with_retry(profile, text: str, voice: str) -> tuple[bytes, str]:
    for attempt in range(2):
        try:
            return await _fetch_audio(profile, text, voice)
        except ProviderError as exc:
            if attempt == 0 and exc.retryable:
                await asyncio.sleep(0.5)
                continue
            raise
    raise ProviderError("TTS_FAILED", "TTS 合成失败", retryable=True)


async def synthesize(text: str, voice: str | None = None, profile=None):
    """合成并落库；命中缓存直接返回 TTSAsset。"""
    from asgiref.sync import sync_to_async

    from apps.voice.models import TTSAsset
    from apps.providers.services import resolve_provider

    if not settings.TTS_ENABLED:
        raise ProviderError("TTS_DISABLED", "TTS 已在配置中关闭", status=400)
    if not text.strip():
        raise ProviderError("TTS_EMPTY_TEXT", "没有可合成的文本", status=400)

    if profile is None:
        profile = await sync_to_async(resolve_provider, thread_sensitive=True)("tts")
    extra = profile.extra_json or {}
    voice = voice or extra.get("voice", settings.TTS_VOICE)
    fmt = extra.get("format", settings.TTS_FORMAT)
    protocol = extra.get("protocol", settings.TTS_PROTOCOL)
    digest = text_hash(text, profile.model, voice, fmt, protocol)

    existing = await sync_to_async(TTSAsset.objects.filter(text_hash=digest).first, thread_sensitive=True)()
    if existing:
        file_path = settings.MEDIA_ROOT / existing.path
        if file_path.exists() and file_path.stat().st_size > 0:
            def _touch():
                existing.save(update_fields=["last_used_at"])

            await sync_to_async(_touch, thread_sensitive=True)()
            return existing

    data, fmt = await _fetch_with_retry(profile, text, voice)
    data = _fix_wav_header(data)
    if len(data) < 128:
        raise ProviderError("TTS_TOO_SHORT", "TTS 返回的音频过短")

    suffix = "." + (fmt or "wav").lower().lstrip(".")
    relative = f"tts/{digest[:32]}{suffix}"
    target = settings.MEDIA_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    duration = _wav_duration(data) if suffix == ".wav" else 0
    if duration <= 0:
        duration = _estimate_duration(text)

    def _store():
        asset, _ = TTSAsset.objects.update_or_create(
            text_hash=digest,
            defaults={
                "text": text,
                "voice": voice,
                "model": profile.model,
                "path": relative,
                "format": fmt,
                "bytes": len(data),
                "duration_ms": duration,
                "expires_at": timezone.now() + timedelta(days=settings.AUDIO_RETENTION_DAYS),
            },
        )
        return asset

    asset = await sync_to_async(_store, thread_sensitive=True)()
    await sync_to_async(_trim_cache, thread_sensitive=True)()
    return asset


def _trim_cache() -> None:
    from apps.voice.models import TTSAsset

    limit = settings.TTS_CACHE_MAX_ITEMS
    rows = list(TTSAsset.objects.order_by("-last_used_at")[limit:])
    for asset in rows:
        try:
            (settings.MEDIA_ROOT / asset.path).unlink(missing_ok=True)
        except OSError:
            pass
        asset.delete()


async def preview(text: str = "你好，我是 MoodBall。", voice: str | None = None) -> dict:
    started = time.perf_counter()
    asset = await synthesize(text, voice=voice)
    return {
        "audio_url": asset.url,
        "audio_id": str(asset.id),
        "duration_ms": asset.duration_ms,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
