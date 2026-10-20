"""表情清单与后端情绪提案。

前端 EmotionController 才是最终仲裁者；这里只给出可解释的建议值。
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("moodball.emotions")

EMOTION_FILES = (
    settings.BASE_DIR / "web" / "public" / "vendor" / "emotion-ball" / "emotion-list.json",
    settings.BASE_DIR / "web" / "dist" / "vendor" / "emotion-ball" / "emotion-list.json",
)

STATE_LOCKED = {"30", "32", "35", "39", "40", "34", "38"}
FALLBACK_ID = "02"


@lru_cache(maxsize=1)
def emotion_catalog() -> tuple[dict, ...]:
    for path in EMOTION_FILES:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return tuple(item for item in data if isinstance(item, dict) and item.get("id"))
        except Exception as exc:  # pragma: no cover
            logger.warning("load emotions failed: %s %s", path, exc)
    return ()


def allowed_ids() -> frozenset[str]:
    return frozenset(item["id"] for item in emotion_catalog())


def emotion_name(emotion_id: str) -> str:
    for item in emotion_catalog():
        if item["id"] == emotion_id:
            return item.get("name", "")
    return ""


def clean_emotion_id(value: str | None, fallback: str | None = None) -> str:
    value = (value or "").strip()
    if value in allowed_ids():
        return value
    return fallback or settings.AGENT_DEFAULT_EMOTION or FALLBACK_ID


_POSITIVE = re.compile(r"(开心|高兴|喜欢|太好了|谢谢|爱你|棒|赞|不错|成功|完成|好耶|哈哈|可爱)")
_NEGATIVE = re.compile(r"(难过|失落|累|疲惫|烦|生气|讨厌|失败|崩溃|糟糕|害怕|焦虑|压力|不想)")
_SLEEPY = re.compile(r"(困|睡|晚安|熬夜|累|疲惫)")
_ANGRY = re.compile(r"(生气|愤怒|讨厌|闭嘴|滚|烦死)")
_SHY = re.compile(r"(害羞|夸|摸头|可爱|喜欢你)")
_CONFUSED = re.compile(r"(不懂|疑惑|为什么|怎么会|奇怪|不确定|没看清|认不出)")
_GREETING = re.compile(r"^(你好|嗨|hi|hello|早上好|晚上好|在吗|小d)")
_VISION_HINTS = re.compile(r"(看看|看一下|这是什么|桌上|图里|摄像头|拍)")


def propose_emotion(
    user_text: str = "",
    reply: str = "",
    vision: dict | None = None,
    error: str | None = None,
    safety: str | None = None,
) -> dict:
    """返回 {emotionId, intensity, tips, source}；调用方仍会做校验。"""
    user_text = user_text or ""
    reply = reply or ""

    if error:
        return {"emotionId": "34", "intensity": 0.9, "tips": "出了点问题", "source": "rule"}
    if safety == "sensitive" or (vision or {}).get("safety") == "sensitive":
        return {"emotionId": "38", "intensity": 0.9, "tips": "这个我不太方便看", "source": "rule"}

    if vision:
        confidence = float(vision.get("confidence") or 0)
        if confidence < 0.35:
            return {"emotionId": "11", "intensity": 0.6, "tips": "有点看不清", "source": "rule"}
        if vision.get("objects") or vision.get("scene"):
            return {"emotionId": "03", "intensity": 0.7, "tips": "我看到了", "source": "rule"}

    combined = f"{user_text} {reply}"
    if _ANGRY.search(user_text):
        return {"emotionId": "21", "intensity": 0.85, "tips": "", "source": "rule"}
    if _SLEEPY.search(user_text):
        return {"emotionId": "15", "intensity": 0.8, "tips": "早点休息呀", "source": "rule"}
    if _SHY.search(combined):
        return {"emotionId": "14", "intensity": 0.75, "tips": "", "source": "rule"}
    if _NEGATIVE.search(user_text):
        return {"emotionId": "12", "intensity": 0.75, "tips": "我在听", "source": "rule"}
    if _POSITIVE.search(combined):
        return {"emotionId": "10", "intensity": 0.8, "tips": "", "source": "rule"}
    if _CONFUSED.search(combined):
        return {"emotionId": "11", "intensity": 0.6, "tips": "", "source": "rule"}
    if _GREETING.search(user_text.strip()):
        return {"emotionId": "10", "intensity": 0.6, "tips": "", "source": "rule"}
    if _VISION_HINTS.search(user_text):
        return {"emotionId": "03", "intensity": 0.6, "tips": "让我看看", "source": "rule"}
    return {
        "emotionId": settings.AGENT_DEFAULT_EMOTION or FALLBACK_ID,
        "intensity": 0.5,
        "tips": "",
        "source": "rule",
    }


def apply_emotion_proposal(proposal: dict, fallback: str | None = None) -> dict:
    emotion_id = clean_emotion_id(proposal.get("emotionId"), fallback)
    try:
        intensity = float(proposal.get("intensity", 0.5))
    except (TypeError, ValueError):
        intensity = 0.5
    return {
        "emotionId": emotion_id,
        "intensity": max(0.0, min(1.0, intensity)),
        "tips": str(proposal.get("tips") or "")[:120],
        "source": proposal.get("source") or "rule",
    }
