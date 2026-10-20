"""内置工具：抓帧、记忆、表情、时间。"""

from __future__ import annotations

import logging
from datetime import datetime

from asgiref.sync import sync_to_async
from langchain_core.tools import tool

from services.emotions import allowed_ids, clean_emotion_id, emotion_name

logger = logging.getLogger("moodball.tools")


@tool
async def capture_photo() -> dict:
    """抓一帧摄像头画面，返回 image_id 与本地 URL。用户要求看东西时使用。"""
    from services.camera import get_camera
    from services.images import save_image

    snapshot = await sync_to_async(get_camera().snapshot, thread_sensitive=False)()
    asset = await sync_to_async(save_image, thread_sensitive=False)(snapshot.jpeg)
    return {
        "image_id": str(asset.id),
        "url": asset.url,
        "width": asset.width,
        "height": asset.height,
        "sha256": asset.sha256,
    }


@tool
async def recall_memory(query: str = "", k: int = 5) -> list[dict]:
    """按关键词检索长期记忆；query 为空时返回置顶和最近用过的记忆。"""
    from apps.chat import memory_service

    if not await sync_to_async(memory_service.is_enabled, thread_sensitive=True)():
        return []
    return await sync_to_async(memory_service.recall, thread_sensitive=True)(query, k)


@tool
async def remember_fact(fact: str, tags: str = "", pinned: bool = False) -> dict:
    """把用户明确要求长期记住的事实写入记忆库；相似事实会自动合并去重。"""
    from apps.chat import memory_service

    if not fact.strip():
        return {"ok": False, "error": "fact 不能为空"}
    if not await sync_to_async(memory_service.is_enabled, thread_sensitive=True)():
        return {"ok": False, "error": "长期记忆已在设置中关闭"}
    item, created = await sync_to_async(memory_service.create_memory, thread_sensitive=True)(
        fact,
        tags,
        source="agent",
        pinned=bool(pinned),
        confidence=0.9,
    )
    return {"ok": True, "created": created, "memory": item}


@tool
async def forget_memory(query: str) -> dict:
    """按关键词删除长期记忆；用户说「忘掉」「别记住」「删掉这条记忆」时使用。"""
    from apps.chat import memory_service

    if not query.strip():
        return {"ok": False, "error": "query 不能为空"}
    deleted = await sync_to_async(memory_service.forget_matching, thread_sensitive=True)(query)
    return {"ok": True, "deleted": deleted}


@tool
async def set_emotion(emotion_id: str, tips: str = "") -> dict:
    """显式请求小球切换表情；emotion_id 必须是 33 个合法 ID 之一。"""
    if emotion_id not in allowed_ids():
        return {
            "ok": False,
            "error": f"非法表情 ID：{emotion_id}",
            "allowed": sorted(allowed_ids()),
        }
    return {
        "ok": True,
        "emotionId": clean_emotion_id(emotion_id),
        "name": emotion_name(emotion_id),
        "tips": (tips or "")[:120],
    }


@tool
def get_time() -> str:
    """返回本机当前日期与时间。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
async def camera_status() -> dict:
    """查询摄像头是否已打开、分辨率与最近错误。"""
    from services.camera import get_camera

    return await sync_to_async(get_camera().status, thread_sensitive=False)()


BUILTIN_TOOLS = [
    capture_photo,
    recall_memory,
    remember_fact,
    forget_memory,
    set_emotion,
    get_time,
    camera_status,
]
