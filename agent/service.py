"""AgentService：运行 LangGraph、转 SSE 事件、异常兜底。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from services.llm import estimate_tokens

from .events import reset_event_queue, set_event_queue
from .graph import build_graph

logger = logging.getLogger("moodball.agent")


class AgentService:
    async def stream(
        self,
        conversation_id: str,
        text: str,
        *,
        user_message_id: str | None = None,
        image_ref: str | None = None,
        with_vision: bool = False,
        speak: bool = True,
    ) -> AsyncIterator[dict]:
        started = time.perf_counter()
        run_id = await self._create_run(conversation_id, text)
        queue: asyncio.Queue = asyncio.Queue()
        token = set_event_queue(queue)
        task: asyncio.Task | None = None
        final_state: dict = {}

        input_state = {
            "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), HumanMessage(content=text)],
            "conversation_id": str(conversation_id),
            "user_message_id": str(user_message_id) if user_message_id else None,
            "user_text": text,
            "image_ref": str(image_ref) if image_ref else None,
            "with_vision": bool(with_vision),
            "speak": bool(speak),
            "run_id": run_id,
            "timings": {"started": started},
            # 显式清空上一轮状态，避免检查点里的旧 vision/error 泄漏
            "vision": None,
            "memory": [],
            "pinned_memory": [],
            "history": [],
            "summary": "",
            "error": None,
            "reply": "",
            "emotion": "",
            "emotion_source": "",
            "intensity": 0.0,
            "tips": "",
            "selected_tools": [],
            "available_tools": [],
            "tool_events": [],
            "steps": 0,
            "usage": {},
            "assistant_message_id": None,
        }

        try:
            if not settings.AGENT_ENABLED:
                result = await self._local_direct(text)
                # 节点把 token 推进了队列；这里补发，保证前端仍能看到流式文本。
                while not queue.empty():
                    yield queue.get_nowait()
                state = {**input_state, **result}
                message_id = await self._persist_fallback(
                    conversation_id, text, result["reply"], result["emotion"], run_id
                )
                final_state = {**state, "assistant_message_id": message_id}
            else:
                settings.CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
                async with AsyncSqliteSaver.from_conn_string(str(settings.CHECKPOINT_DB)) as saver:
                    graph = build_graph(saver)
                    config = {
                        "configurable": {"thread_id": str(conversation_id)},
                        "recursion_limit": max(12, settings.AGENT_MAX_STEPS * 3 + 8),
                    }
                    task = asyncio.create_task(graph.ainvoke(input_state, config=config))
                    try:
                        while True:
                            try:
                                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                                yield item
                            except asyncio.TimeoutError:
                                if task.done():
                                    while not queue.empty():
                                        yield queue.get_nowait()
                                    break
                        final_state = await task
                    except asyncio.CancelledError:
                        if task is not None and not task.done():
                            task.cancel()
                        raise
                    except Exception as exc:
                        logger.exception("agent graph failed")
                        message = _friendly_agent_error(exc)
                        yield {
                            "event": "error",
                            "data": {
                                "code": "AGENT_FAILED",
                                "message": message,
                                "retryable": True,
                            },
                        }
                        message_id = await self._persist_fallback(
                            conversation_id, text, message, "34", run_id, error=str(exc)
                        )
                        final_state = {
                            **input_state,
                            "reply": message,
                            "emotion": "34",
                            "intensity": 0.9,
                            "tips": "出了点问题",
                            "assistant_message_id": message_id,
                        }
                    finally:
                        if task is not None and not task.done():
                            task.cancel()

            if not final_state.get("assistant_message_id"):
                message_id = await self._persist_fallback(
                    conversation_id,
                    text,
                    final_state.get("reply") or "这一轮没有生成回复。",
                    final_state.get("emotion") or "34",
                    run_id,
                )
                final_state["assistant_message_id"] = message_id

            latency_ms = int((time.perf_counter() - started) * 1000)
            reply = final_state.get("reply") or ""
            yield {
                "event": "final",
                "data": {
                    "message_id": final_state.get("assistant_message_id"),
                    "run_id": run_id,
                    "reply": reply,
                    "emotionId": final_state.get("emotion") or "02",
                    "intensity": float(final_state.get("intensity") or 0.5),
                    "tips": final_state.get("tips") or "",
                    "usage": {
                        "in": (final_state.get("usage") or {}).get(
                            "in", estimate_tokens(text)
                        ),
                        "out": (final_state.get("usage") or {}).get(
                            "out", estimate_tokens(reply)
                        ),
                    },
                    "latency_ms": latency_ms,
                    "tool_events": final_state.get("tool_events") or [],
                },
            }
        finally:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            reset_event_queue(token)

    async def run(self, conversation_id: str, text: str, **kwargs) -> dict:
        final: dict | None = None
        error: dict | None = None
        async for event in self.stream(conversation_id, text, **kwargs):
            if event["event"] == "final":
                final = event["data"]
            elif event["event"] == "error":
                error = event["data"]
        if final is None:
            return {
                "message_id": None,
                "reply": "",
                "emotionId": "34",
                "error": error,
            }
        return final

    # ------------------------------------------------------------------
    async def _create_run(self, conversation_id: str, text: str) -> str:
        from apps.agent.models import AgentRun

        def _create() -> str:
            run = AgentRun.objects.create(
                conversation_id=conversation_id,
                thread_id=str(conversation_id),
                status=AgentRun.Status.RUNNING,
                user_text=text,
            )
            return str(run.id)

        try:
            return await sync_to_async(_create, thread_sensitive=True)()
        except Exception:
            logger.warning("create agent run failed", exc_info=True)
            return ""

    async def _persist_fallback(
        self,
        conversation_id: str,
        user_text: str,
        reply: str,
        emotion: str,
        run_id: str,
        error: str = "",
    ) -> str:
        from apps.agent.models import AgentRun
        from apps.chat.models import Conversation, EmotionEvent, Message

        def _persist() -> str:
            conversation = Conversation.objects.filter(pk=conversation_id).first()
            if conversation is None:
                return ""
            message = Message.objects.create(
                conversation=conversation,
                role="assistant",
                content=reply,
                emotion_id=emotion,
                tokens_in=estimate_tokens(user_text),
                tokens_out=estimate_tokens(reply),
                meta_json={"fallback": True, "error": error},
            )
            EmotionEvent.objects.create(
                conversation=conversation,
                message=message,
                emotion_id=emotion,
                intensity=0.9,
                source="fallback",
                reason=error[:300],
            )
            if not conversation.title.strip():
                conversation.title = user_text[:24]
                conversation.save(update_fields=["title", "updated_at"])
            if run_id:
                run = AgentRun.objects.filter(pk=run_id).first()
                if run is not None:
                    run.status = AgentRun.Status.ERROR if error else AgentRun.Status.FALLBACK
                    run.reply = reply
                    run.emotion_id = emotion
                    run.error = error
                    run.finished_at = timezone.now()
                    run.save()
            return str(message.id)

        return await sync_to_async(_persist, thread_sensitive=True)()

    async def _local_direct(self, text: str) -> dict:
        from .nodes import _local_fallback

        state = {"user_text": text, "timings": {"started": time.perf_counter()}}
        result = await _local_fallback(state, reason="provider_missing")
        return {
            "reply": result["reply"],
            "emotion": result["emotion"],
            "intensity": result["intensity"],
            "tips": result["tips"],
        }


def _friendly_agent_error(exc: Exception) -> str:
    text = str(exc)
    if "api_key" in text.lower() or "authentication" in text.lower():
        return "对话服务鉴权失败，请检查设置页里的 Key。"
    if "timeout" in text.lower():
        return "这一步超时了，请稍后重试。"
    return "Agent 运行时出现了问题，已记录日志。可以重试一次。"


agent_service = AgentService()
