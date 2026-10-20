"""AppSetting 的读取 / 合并 / 校验。"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from .models import AppSetting

# 默认值全部来自 .env；数据库里的 AppSetting 覆盖它。
SETTING_DEFAULTS: dict[str, Any] = {
    "wake_word": settings.WAKE_WORD,
    "wake_variants": settings.WAKE_VARIANTS,
    "wake_confirm_hits": settings.WAKE_CONFIRM_HITS,
    "wake_cooldown_ms": settings.WAKE_COOLDOWN_MS,
    "command_timeout_ms": settings.COMMAND_TIMEOUT_MS,
    "tts_voice": settings.TTS_VOICE,
    "tts_model": settings.TTS_MODEL,
    "tts_enabled": settings.TTS_ENABLED,
    "camera_index": settings.CAMERA_INDEX,
    "camera_backend": settings.CAMERA_BACKEND,
    "camera_width": settings.CAMERA_WIDTH,
    "camera_height": settings.CAMERA_HEIGHT,
    "retain_images": True,
    "image_retention_days": settings.IMAGE_RETENTION_DAYS,
    "audio_retention_days": settings.AUDIO_RETENTION_DAYS,
    "speak_replies": True,
    "emotion_style": "balanced",
    "reduced_motion": False,
    "agent_enabled": settings.AGENT_ENABLED,
    "mcp_enabled": settings.MCP_ENABLED,
    "memory_enabled": settings.MEMORY_ENABLED,
    "memory_auto_extract": settings.MEMORY_AUTO_EXTRACT,
    "memory_max_items": settings.MEMORY_MAX_ITEMS,
}

# 允许前端修改的字段与类型
_ALLOWED: dict[str, type | tuple[type, ...]] = {
    "wake_word": str,
    "wake_variants": list,
    "wake_confirm_hits": int,
    "wake_cooldown_ms": int,
    "command_timeout_ms": int,
    "tts_voice": str,
    "tts_model": str,
    "tts_enabled": bool,
    "camera_index": int,
    "camera_backend": str,
    "camera_width": int,
    "camera_height": int,
    "retain_images": bool,
    "image_retention_days": int,
    "audio_retention_days": int,
    "speak_replies": bool,
    "emotion_style": str,
    "reduced_motion": bool,
    "agent_enabled": bool,
    "mcp_enabled": bool,
    "memory_enabled": bool,
    "memory_auto_extract": bool,
    "memory_max_items": int,
}


def _stored() -> dict[str, Any]:
    return {row.key: row.value_json for row in AppSetting.objects.all()}


def get_settings() -> dict[str, Any]:
    data = dict(SETTING_DEFAULTS)
    data.update(_stored())
    return data


def get_setting(key: str, default: Any = None) -> Any:
    if key not in SETTING_DEFAULTS:
        return default
    try:
        row = AppSetting.objects.filter(pk=key).first()
    except Exception:
        row = None
    return row.value_json if row else SETTING_DEFAULTS.get(key, default)


def update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(patch) - set(_ALLOWED))
    if unknown:
        from .exceptions import ApiError

        raise ApiError("UNKNOWN_SETTING", f"不支持的设置项：{', '.join(unknown)}", status=400)

    for key, value in patch.items():
        expected = _ALLOWED[key]
        if expected is int and isinstance(value, bool):
            value = int(value)
        if not isinstance(value, expected):
            from .exceptions import ApiError

            raise ApiError("INVALID_SETTING", f"设置项 {key} 类型不正确", status=400)
        if key == "wake_variants":
            value = [str(item).strip() for item in value if str(item).strip()]
        if key == "wake_confirm_hits":
            value = max(1, min(5, int(value)))
        if key in {"wake_cooldown_ms", "command_timeout_ms"}:
            value = max(0, int(value))
        if key == "memory_max_items":
            value = max(10, min(5000, int(value)))
        AppSetting.objects.update_or_create(key=key, defaults={"value_json": value})

    return get_settings()
