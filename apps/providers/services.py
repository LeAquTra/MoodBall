"""Provider 解析、种子与测试连接。"""

from __future__ import annotations

import io
import logging
import time
from types import SimpleNamespace
from urllib.parse import urlparse

from django.conf import settings

from services.base import ProviderError, ProviderNotConfigured

from .models import ProviderProfile

logger = logging.getLogger("moodball.providers")

KINDS = ("chat", "vision", "tts", "asr")


def _env_profile(kind: str) -> SimpleNamespace:
    seed = settings.PROVIDER_DEFAULTS.get(kind, {})
    return SimpleNamespace(
        id=None,
        kind=kind,
        name=seed.get("name", kind),
        base_url=seed.get("base_url", ""),
        model=seed.get("model", ""),
        api_key=seed.get("api_key", ""),
        extra_json=dict(seed.get("extra") or {}),
        enabled=True,
        is_default=True,
        source="env",
    )


def resolve_provider(kind: str):
    """数据库优先；没有记录时回退到 .env 的种子（不落库）。"""
    if kind not in KINDS:
        raise ProviderError("INVALID_PROVIDER_KIND", f"未知 Provider 类型：{kind}", status=400)
    queryset = ProviderProfile.objects.filter(kind=kind, enabled=True)
    profile = queryset.filter(is_default=True).first() or queryset.order_by("created_at").first()
    if profile is not None:
        # `.env` 里的 Key 作为缺失字段的兜底：第一次 GET 种子化时可能还没有填 Key，
        # 之后在 .env 补上 Key 不应该被数据库里的空值永久挡住。
        seed = settings.PROVIDER_DEFAULTS.get(kind, {})
        if not profile.api_key and seed.get("api_key"):
            profile.api_key = seed["api_key"]
        if not profile.base_url and seed.get("base_url"):
            profile.base_url = seed["base_url"]
        if not profile.model and seed.get("model"):
            profile.model = seed["model"]
        profile.source = "db"  # type: ignore[attr-defined]
        return profile
    profile = _env_profile(kind)
    profile.source = "env"
    return profile


def seed_from_env() -> None:
    """把 .env 里尚不存在的 Provider 类型写入数据库，之后以数据库为准。"""
    existing = set(ProviderProfile.objects.values_list("kind", flat=True))
    for kind in KINDS:
        if kind in existing:
            continue
        seed = settings.PROVIDER_DEFAULTS.get(kind)
        if not seed:
            continue
        ProviderProfile.objects.create(
            kind=kind,
            name=seed["name"],
            base_url=seed["base_url"],
            model=seed["model"],
            api_key=seed.get("api_key", ""),
            extra_json=dict(seed.get("extra") or {}),
            enabled=True,
            is_default=True,
        )


def provider_status() -> dict:
    result: dict[str, dict] = {}
    for kind in KINDS:
        try:
            profile = resolve_provider(kind)
        except Exception as exc:  # pragma: no cover
            result[kind] = {"ok": False, "message": str(exc)}
            continue
        result[kind] = {
            "configured": bool(profile.base_url and profile.model and (profile.api_key or kind == "asr")),
            "source": getattr(profile, "source", "db"),
            "name": profile.name,
            "model": profile.model,
            "base_url": profile.base_url,
            "api_key_set": bool(profile.api_key),
        }
    return result


def validate_base_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ProviderError("INVALID_BASE_URL", "Base URL 不能为空", status=400)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderError("INVALID_BASE_URL", "Base URL 必须是 http:// 或 https:// 地址", status=400)
    return value.rstrip("/")


def _chat_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


async def _http_post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
    if response.status_code >= 400:
        detail = response.text[:500]
        raise ProviderError(
            f"PROVIDER_HTTP_{response.status_code}",
            f"Provider 返回 {response.status_code}：{detail}",
            retryable=response.status_code in {429, 500, 502, 503, 504},
        )
    return response.json()


async def test_provider(profile) -> dict:
    # 数据库里 Key 为空时，沿用 .env 的同类型种子（与 resolve_provider 一致）。
    seed = settings.PROVIDER_DEFAULTS.get(profile.kind, {})
    if not getattr(profile, "api_key", ""):
        profile.api_key = seed.get("api_key", "")
    if not getattr(profile, "base_url", ""):
        profile.base_url = seed.get("base_url", "")
    if not getattr(profile, "model", ""):
        profile.model = seed.get("model", "")

    started = time.perf_counter()
    try:
        if profile.kind == "chat":
            await _test_chat(profile)
        elif profile.kind == "vision":
            await _test_vision(profile)
        elif profile.kind == "tts":
            await _test_tts(profile)
        elif profile.kind == "asr":
            await _test_asr(profile)
        else:
            raise ProviderError("INVALID_PROVIDER_KIND", f"未知 Provider 类型：{profile.kind}", status=400)
    except ProviderNotConfigured as exc:
        return {"ok": False, "code": exc.code, "message": exc.message, "latency_ms": _elapsed(started)}
    except ProviderError as exc:
        return {
            "ok": False,
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "latency_ms": _elapsed(started),
        }
    except Exception as exc:  # pragma: no cover
        logger.warning("provider test failed: %s", exc)
        return {"ok": False, "code": "PROVIDER_TEST_FAILED", "message": str(exc), "latency_ms": _elapsed(started)}
    return {"ok": True, "message": "连接正常", "latency_ms": _elapsed(started)}


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


async def _test_chat(profile) -> None:
    if not profile.api_key:
        raise ProviderNotConfigured("chat")
    headers = {"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}
    payload = {
        "model": profile.model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "temperature": 0,
        "stream": False,
    }
    data = await _http_post_json(
        _chat_endpoint(profile.base_url), headers, payload, float(profile.extra_json.get("timeout", 30))
    )
    if not data.get("choices"):
        raise ProviderError("PROVIDER_BAD_RESPONSE", "对话接口没有返回 choices")


async def _test_vision(profile) -> None:
    if not profile.api_key:
        raise ProviderNotConfigured("vision")
    from services.vision import analyze_image

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise ProviderError("PIL_MISSING", "缺少 Pillow，无法生成测试图片") from exc
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (220, 40, 40)).save(buffer, format="JPEG", quality=80)
    result = await analyze_image(profile, buffer.getvalue(), prompt="这张图是什么颜色？只回答颜色。")
    if not isinstance(result, dict):
        raise ProviderError("PROVIDER_BAD_RESPONSE", "视觉接口没有返回 JSON 对象")


async def _test_tts(profile) -> None:
    if not profile.api_key:
        raise ProviderNotConfigured("tts")
    from services.tts import synthesize_bytes

    audio = await synthesize_bytes(profile, "测试", voice=profile.extra_json.get("voice"))
    if len(audio) < 1024:
        raise ProviderError("TTS_TOO_SHORT", "TTS 返回的音频小于 1 KB")


async def _test_asr(profile) -> None:
    import httpx

    url = profile.base_url.rstrip("/") + "/health"
    async with httpx.AsyncClient(timeout=float(profile.extra_json.get("timeout", 5))) as client:
        response = await client.get(url)
    if response.status_code >= 400:
        raise ProviderError(
            f"ASR_HTTP_{response.status_code}",
            f"ASR 健康检查返回 {response.status_code}",
            retryable=True,
        )
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if not data.get("ok", True):
        raise ProviderError("ASR_NOT_READY", data.get("message", "ASR 服务未就绪"), retryable=True)
