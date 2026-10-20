"""长期记忆服务：检索、去重、统计、容量控制与自动提取。

设计要点
--------
- 记忆是"事实"而不是聊天记录：一条 `MemoryFact.fact` 一句话，可带标签、可置顶。
- 写入统一走 `create_memory`，做归一化 + 相似去重，避免 agent / 自动提取写出重复条目。
- 召回统一走 `recall`，会累计 `use_count` 与 `last_used_at`，前端"常用"排序才有意义。
- 自动提取是"尽力而为"：没配 Provider、超时、JSON 不合法都只记日志，不影响对话主流程。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import timedelta
from difflib import SequenceMatcher

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone

logger = logging.getLogger("moodball.memory")

MAX_FACT_CHARS = 500
MAX_TAGS = 8
MAX_TAG_CHARS = 24
SENSITIVE_MARKERS = (
    "密码",
    "口令",
    "验证码",
    "身份证",
    "银行卡",
    "信用卡",
    "手机号",
    "家庭住址",
    "家住",
)

_TAG_SPLIT = re.compile(r"[,，、;；#\s]+")

# 口语化记忆问句里的虚词 / 动词；检索前剥掉，避免整句 icontains 永远不命中。
_STOP_PHRASES = (
    "你还记得",
    "你记得",
    "还记得",
    "我之前说过",
    "我说过",
    "别记住",
    "不要记住",
    "忘掉",
    "忘记",
    "删掉",
    "删除",
    "记得",
    "之前",
    "上次",
    "以前",
    "回忆",
    "帮我",
    "什么",
    "哪些",
    "哪个",
    "吗",
    "呢",
    "我",
    "你",
    "的",
)


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------
def normalize_fact(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.strip("。；;，, ")
    return text[:MAX_FACT_CHARS]


def parse_tags(value) -> list[str]:
    if isinstance(value, str):
        parts = _TAG_SPLIT.split(value)
    elif isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value]
    else:
        parts = []
    tags: list[str] = []
    for part in parts:
        tag = str(part).strip().lstrip("#").strip()[:MAX_TAG_CHARS]
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:MAX_TAGS]


def tags_to_string(value) -> str:
    return ",".join(parse_tags(value))[:300]


def _tokens(text: str) -> list[str]:
    cleaned = text or ""
    for phrase in _STOP_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    parts = [item for item in re.split(r"[\s,，。！？!?、;；:：]+", cleaned) if item]
    if not parts:
        parts = [item for item in re.split(r"[\s,，。！？!?、;；:：]+", text or "") if item]
    return parts[:8]


def _is_sensitive(fact: str) -> bool:
    return any(marker in fact for marker in SENSITIVE_MARKERS)


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 8 and len(b) >= 8 and (a in b or b in a):
        return 0.96
    return SequenceMatcher(None, a, b).ratio()


def _order(sort: str) -> tuple[str, ...]:
    if sort == "oldest":
        return ("created_at",)
    if sort == "used":
        return ("-use_count", "-last_used_at", "-created_at")
    if sort == "pinned":
        return ("-pinned", "-created_at")
    return ("-created_at",)


# ---------------------------------------------------------------------------
# 查询 / 统计
# ---------------------------------------------------------------------------
def _filtered(query: str = "", tag: str = ""):
    from .models import MemoryFact

    queryset = MemoryFact.objects.all()
    keyword = (query or "").strip()
    if keyword:
        condition = Q(fact__icontains=keyword) | Q(tags__icontains=keyword)
        for token in _tokens(keyword)[:6]:
            condition |= Q(fact__icontains=token) | Q(tags__icontains=token)
        queryset = queryset.filter(condition)
    tag = (tag or "").strip().lstrip("#")
    if tag:
        queryset = queryset.filter(tags__icontains=tag)
    return queryset


def list_memories(
    query: str = "",
    tag: str = "",
    sort: str = "recent",
    limit: int = 200,
    offset: int = 0,
) -> dict:
    limit = max(1, min(int(limit or 200), 500))
    offset = max(0, int(offset or 0))
    queryset = _filtered(query, tag).order_by(*_order(sort))
    total = queryset.count()
    items = [row.as_dict() for row in queryset[offset : offset + limit]]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def tag_counts(limit: int = 24) -> list[dict]:
    from .models import MemoryFact

    counts: dict[str, int] = {}
    for raw in MemoryFact.objects.values_list("tags", flat=True):
        for tag in parse_tags(raw or ""):
            counts[tag] = counts.get(tag, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"tag": tag, "count": count} for tag, count in ordered[:limit]]


def memory_stats() -> dict:
    from .models import MemoryFact

    week_ago = timezone.now() - timedelta(days=7)
    aggregated = MemoryFact.objects.aggregate(
        total=Count("id"),
        pinned=Count("id", filter=Q(pinned=True)),
        manual=Count("id", filter=Q(source=MemoryFact.Source.MANUAL)),
        agent=Count("id", filter=Q(source=MemoryFact.Source.AGENT)),
        auto=Count("id", filter=Q(source=MemoryFact.Source.AUTO)),
        used=Count("id", filter=Q(use_count__gt=0)),
        used_7d=Count("id", filter=Q(last_used_at__gte=week_ago)),
    )
    return {key: int(value or 0) for key, value in aggregated.items()}


def memory_settings() -> dict:
    from apps.core.settings_service import get_setting

    return {
        "enabled": bool(get_setting("memory_enabled", getattr(settings, "MEMORY_ENABLED", True))),
        "auto_extract": bool(
            get_setting("memory_auto_extract", getattr(settings, "MEMORY_AUTO_EXTRACT", False))
        ),
        "max_items": int(get_setting("memory_max_items", getattr(settings, "MEMORY_MAX_ITEMS", 500))),
        "recall_limit": int(getattr(settings, "MEMORY_RECALL_LIMIT", 5)),
        "pinned_limit": int(getattr(settings, "MEMORY_PINNED_LIMIT", 5)),
    }


def is_enabled() -> bool:
    return bool(memory_settings()["enabled"])


# ---------------------------------------------------------------------------
# 写入 / 更新 / 删除
# ---------------------------------------------------------------------------
def _enforce_limit() -> int:
    """超出上限时删除最久未用且未置顶的记忆，返回删除条数。"""
    from .models import MemoryFact

    limit = max(10, int(memory_settings()["max_items"]))
    total = MemoryFact.objects.count()
    if total <= limit:
        return 0
    removable = MemoryFact.objects.filter(pinned=False).order_by("last_used_at", "created_at")
    excess = total - limit
    ids = list(removable.values_list("id", flat=True)[:excess])
    if not ids:
        return 0
    MemoryFact.objects.filter(id__in=ids).delete()
    logger.info("memory limit reached, pruned %s rows", len(ids))
    return len(ids)


def _find_duplicate(fact: str):
    from .models import MemoryFact

    ratio = float(getattr(settings, "MEMORY_DEDUPE_RATIO", 0.9))
    for row in MemoryFact.objects.all()[:800]:
        if _similar(fact, normalize_fact(row.fact)) >= ratio:
            return row
    return None


def create_memory(
    fact: str,
    tags="",
    *,
    source: str = "manual",
    pinned: bool = False,
    confidence: float = 0.8,
    conversation_id: str | uuid.UUID | None = None,
) -> tuple[dict, bool]:
    """写入一条记忆；返回 (序列化结果, 是否新建)。相似条目会合并而不是重复插入。"""
    from .models import MemoryFact

    normalized = normalize_fact(fact)
    tag_string = tags_to_string(tags)
    if not normalized:
        raise ValueError("fact 不能为空")

    duplicate = _find_duplicate(normalized)
    if duplicate is not None:
        merged_tags = tags_to_string(list(parse_tags(duplicate.tags)) + parse_tags(tag_string))
        duplicate.tags = merged_tags
        duplicate.pinned = duplicate.pinned or bool(pinned)
        duplicate.confidence = max(float(duplicate.confidence or 0), float(confidence or 0))
        duplicate.save(update_fields=["tags", "pinned", "confidence", "updated_at"])
        return duplicate.as_dict(), False

    valid_sources = {choice for choice, _ in MemoryFact.Source.choices}
    if source not in valid_sources:
        source = MemoryFact.Source.MANUAL
    row = MemoryFact.objects.create(
        fact=normalized,
        tags=tag_string,
        source=source,
        pinned=bool(pinned),
        confidence=max(0.0, min(1.0, float(confidence or 0.8))),
        conversation_id=conversation_id or None,
    )
    _enforce_limit()
    return row.as_dict(), True


def update_memory(memory, *, fact: str | None = None, tags=None, pinned=None, confidence=None) -> dict:
    fields: list[str] = []
    if fact is not None:
        normalized = normalize_fact(fact)
        if not normalized:
            raise ValueError("fact 不能为空")
        memory.fact = normalized
        fields.append("fact")
    if tags is not None:
        memory.tags = tags_to_string(tags)
        fields.append("tags")
    if pinned is not None:
        memory.pinned = bool(pinned)
        fields.append("pinned")
    if confidence is not None:
        memory.confidence = max(0.0, min(1.0, float(confidence)))
        fields.append("confidence")
    if fields:
        fields.append("updated_at")
        memory.save(update_fields=fields)
    return memory.as_dict()


def delete_memory(memory) -> None:
    memory.delete()


def bulk_delete(ids: list[str]) -> int:
    from .models import MemoryFact

    valid: list[str] = []
    for raw in ids or []:
        try:
            valid.append(str(uuid.UUID(str(raw))))
        except (TypeError, ValueError, AttributeError):
            continue
    if not valid:
        return 0
    deleted, _ = MemoryFact.objects.filter(id__in=valid).delete()
    return int(deleted)


def clear_memories(keep_pinned: bool = True) -> int:
    from .models import MemoryFact

    queryset = MemoryFact.objects.all()
    if keep_pinned:
        queryset = queryset.filter(pinned=False)
    deleted, _ = queryset.delete()
    return int(deleted)


def forget_matching(query: str) -> int:
    """按关键词删除记忆（agent 的 forget_memory 工具用）。空查询不删除任何东西。"""
    keyword = (query or "").strip()
    if not keyword:
        return 0
    return int(_filtered(keyword).delete()[0])


# ---------------------------------------------------------------------------
# 召回
# ---------------------------------------------------------------------------
def recall(query: str = "", limit: int | None = None, mark_used: bool = True) -> list[dict]:
    from .models import MemoryFact

    limit = max(1, min(int(limit or getattr(settings, "MEMORY_RECALL_LIMIT", 5)), 20))
    keyword = (query or "").strip()
    if keyword:
        queryset = _filtered(keyword)
        if not queryset.exists():
            queryset = MemoryFact.objects.all()
    else:
        queryset = MemoryFact.objects.all()
    rows = list(
        queryset.order_by("-pinned", "-use_count", "-last_used_at", "-created_at")[:limit]
    )
    if rows and mark_used:
        now = timezone.now()
        MemoryFact.objects.filter(id__in=[row.id for row in rows]).update(
            use_count=F("use_count") + 1, last_used_at=now
        )
        for row in rows:
            row.use_count += 1
            row.last_used_at = now
    return [row.as_dict() for row in rows]


def pinned_memories(limit: int | None = None) -> list[dict]:
    from .models import MemoryFact

    limit = max(1, min(int(limit or getattr(settings, "MEMORY_PINNED_LIMIT", 5)), 20))
    return [row.as_dict() for row in MemoryFact.objects.filter(pinned=True)[:limit]]


# ---------------------------------------------------------------------------
# 自动提取（尽力而为）
# ---------------------------------------------------------------------------
def _parse_fact_array(text: str) -> list[str]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char != "[":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
    return []


def _clean_candidates(raw: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in raw[:8]:
        fact = normalize_fact(item)
        if len(fact) < 4 or len(fact) > 180:
            continue
        if _is_sensitive(fact):
            continue
        if any(_similar(fact, existing) >= 0.9 for existing in cleaned):
            continue
        cleaned.append(fact)
    return cleaned[:3]


async def extract_facts(user_text: str, reply: str) -> list[str]:
    """用对话 Provider 从一轮对话里提取 0-3 条用户事实；任何异常都返回空列表。"""
    if not user_text.strip() or not reply.strip():
        return []
    try:
        from apps.providers.services import resolve_provider
        from services.llm import OpenAICompatChat

        provider = await sync_to_async(resolve_provider, thread_sensitive=True)("chat")
        if provider is None or not getattr(provider, "api_key", ""):
            return []
        chat = OpenAICompatChat(provider)
        messages = [
            {"role": "system", "content": _extract_prompt()},
            {"role": "user", "content": f"用户：{user_text[:2000]}\n小球：{reply[:2000]}"},
        ]
        timeout = float(getattr(settings, "MEMORY_EXTRACT_TIMEOUT", 25.0))
        result = await asyncio.wait_for(
            chat.complete(messages, temperature=0.2, max_tokens=240, json_mode=False),
            timeout=timeout,
        )
        return _clean_candidates(_parse_fact_array(result.content))
    except asyncio.TimeoutError:
        logger.info("memory extraction timed out")
        return []
    except Exception as exc:  # pragma: no cover - 网络 / JSON 兜底
        logger.info("memory extraction skipped: %s", exc)
        return []


def _extract_prompt() -> str:
    try:
        from agent.prompts import MEMORY_EXTRACT

        return MEMORY_EXTRACT
    except Exception:  # pragma: no cover
        return (
            "从下面这轮对话中提取 0-3 条值得长期记住的用户事实。"
            '只输出 JSON 数组：["事实1", "事实2"]。'
            "不要提取一次性寒暄、临时情绪、敏感信息。"
        )


async def maybe_auto_extract(conversation_id: str, user_text: str, reply: str) -> list[dict]:
    """按设置执行自动提取并落库；返回新建的记忆列表。"""
    conf = await sync_to_async(memory_settings, thread_sensitive=True)()
    if not conf["enabled"] or not conf["auto_extract"]:
        return []
    facts = await extract_facts(user_text, reply)
    if not facts:
        return []
    created: list[dict] = []
    for fact in facts:
        try:
            item, is_new = await sync_to_async(create_memory, thread_sensitive=True)(
                fact,
                tags="自动提取",
                source="auto",
                confidence=0.6,
                conversation_id=conversation_id,
            )
        except Exception:
            logger.warning("auto memory create failed", exc_info=True)
            continue
        if is_new:
            created.append(item)
    if created:
        logger.info("auto extracted %s memories", len(created))
    return created


async def schedule_auto_extract(conversation_id: str, user_text: str, reply: str) -> None:
    """后台任务入口：吞掉所有异常，绝不把记忆提取问题抛给对话链路。"""
    try:
        await maybe_auto_extract(conversation_id, user_text, reply)
    except Exception:  # pragma: no cover
        logger.warning("auto extract task failed", exc_info=True)
