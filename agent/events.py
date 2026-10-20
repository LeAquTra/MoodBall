"""运行期事件通道：节点把 SSE 事件推给 AgentService。"""

from __future__ import annotations

import asyncio
import contextvars
from typing import Any

_event_queue: contextvars.ContextVar[asyncio.Queue | None] = contextvars.ContextVar(
    "moodball_event_queue", default=None
)


def set_event_queue(queue: asyncio.Queue | None):
    return _event_queue.set(queue)


def reset_event_queue(token) -> None:
    _event_queue.reset(token)


async def emit(event: str, data: dict[str, Any] | None = None) -> None:
    queue = _event_queue.get()
    if queue is None:
        return
    queue.put_nowait({"event": event, "data": data or {}})


async def emit_state(state: str, *, node: str = "", emotion: str | None = None) -> None:
    payload = {"state": state, "node": node}
    if emotion:
        payload["emotion"] = emotion
    await emit("state", payload)
