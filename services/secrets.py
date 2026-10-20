"""个人本机模式：Key 明文读取，UI 只做掩码。"""

from __future__ import annotations


def reveal_key(profile) -> str:
    return profile.api_key or ""


def mask_key(raw: str) -> str:
    if not raw:
        return ""
    if len(raw) <= 8:
        return "****"
    return f"{raw[:3]}****{raw[-4:]}"


def key_is_placeholder(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return not lowered or lowered in {"change-me", "sk-xxx", "your-key-here", "test", "none"}
