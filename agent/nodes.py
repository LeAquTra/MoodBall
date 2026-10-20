"""LangGraph 节点实现。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from services.base import ProviderError, _merge_tool_call_deltas
from services.emotions import (
    allowed_ids,
    apply_emotion_proposal,
    clean_emotion_id,
    propose_emotion,
)
from services.llm import JsonReplyExtractor, estimate_tokens
from services.vision import analyze_image

from .events import emit, emit_state
from .prompts import compose_system, context_block
from .registry import ToolEntry, registry
from .state import AgentState

logger = logging.getLogger("moodball.agent")

VISION_HINTS = ("看看", "看一下", "拍张", "拍照", "摄像头", "桌上", "这是什么", "图里", "画面")
MEMORY_HINTS = ("记得", "之前", "上次", "我说过", "回忆", "以前")
TOOL_HINTS = ("几点", "时间", "磁盘", "摄像头状态", "查一下", "工具")


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------
async def load_context(state: AgentState) -> dict:
    from apps.chat import memory_service
    from apps.chat.models import Conversation, Message

    started = time.perf_counter()
    conversation_id = state["conversation_id"]
    user_message_id = state.get("user_message_id")

    def _load():
        conversation = Conversation.objects.filter(pk=conversation_id).first()
        queryset = Message.objects.filter(conversation_id=conversation_id)
        if user_message_id:
            queryset = queryset.exclude(pk=user_message_id)
        rows = list(queryset.order_by("-created_at")[: settings.AGENT_RECENT_MESSAGES])
        rows.reverse()
        pinned = memory_service.pinned_memories() if memory_service.is_enabled() else []
        return conversation, rows, pinned

    conversation, rows, pinned = await sync_to_async(_load, thread_sensitive=True)()
    history = [
        {"role": row.role, "content": row.content}
        for row in rows
        if row.role in {"user", "assistant"} and row.content.strip()
    ]
    timings = dict(state.get("timings") or {})
    timings["context_ms"] = int((time.perf_counter() - started) * 1000)
    return {
        "history": history,
        "summary": conversation.summary if conversation else "",
        "pinned_memory": pinned,
        "timings": timings,
    }


async def load_tools(state: AgentState) -> dict:
    if not settings.AGENT_ENABLED:
        return {"available_tools": []}
    if settings.MCP_ENABLED:
        try:
            await registry.refresh_if_stale()
        except Exception:
            logger.warning("refresh tool registry failed", exc_info=True)
    return {
        "available_tools": [
            {"name": entry.name, "source": entry.source, "description": entry.description}
            for entry in registry.list()
        ]
    }


async def route(state: AgentState) -> dict:
    await emit_state("thinking", node="route", emotion="30")
    text = state.get("user_text") or ""
    if state.get("with_vision") or state.get("image_ref"):
        intent = "vision"
    elif any(hint in text for hint in VISION_HINTS):
        intent = "vision"
    elif any(hint in text for hint in MEMORY_HINTS):
        intent = "memory"
    elif any(hint in text for hint in TOOL_HINTS):
        intent = "tool"
    else:
        intent = "chat"
    return {"intent": intent}


# ---------------------------------------------------------------------------
# 视觉
# ---------------------------------------------------------------------------
async def capture_vision(state: AgentState) -> dict:
    await emit_state("acting", node="capture_vision", emotion="40")
    started = time.perf_counter()
    try:
        image_ref = state.get("image_ref")
        if image_ref:
            from apps.vision.models import ImageAsset

            def _exists():
                return ImageAsset.objects.filter(pk=image_ref).exists()

            if not await sync_to_async(_exists, thread_sensitive=True)():
                raise ValueError("图片不存在")
        else:
            from services.camera import get_camera
            from services.images import save_image

            snapshot = await sync_to_async(get_camera().snapshot, thread_sensitive=False)()
            asset = await sync_to_async(save_image, thread_sensitive=False)(
                snapshot.jpeg, conversation_id=state["conversation_id"]
            )
            image_ref = str(asset.id)

        timings = dict(state.get("timings") or {})
        timings["capture_ms"] = int((time.perf_counter() - started) * 1000)
        return {"image_ref": image_ref, "timings": timings}
    except Exception as exc:
        from services.camera import CameraError

        logger.warning("capture vision failed: %s", exc)
        if isinstance(exc, CameraError):
            return {"error": f"VISION_CAPTURE: {exc.code} {exc.message}"}
        return {"error": f"VISION_CAPTURE: {exc}"}


async def analyze_vision(state: AgentState) -> dict:
    if state.get("error"):
        return {}
    await emit_state("acting", node="analyze_vision", emotion="40")
    started = time.perf_counter()
    try:
        from apps.providers.services import resolve_provider
        from apps.vision.models import ImageAsset

        def _load_bytes():
            asset = ImageAsset.objects.filter(pk=state.get("image_ref")).first()
            if asset is None:
                raise ValueError("图片记录不存在")
            path = settings.MEDIA_ROOT / asset.path
            return asset, path.read_bytes() if path.exists() else b""

        asset, image_bytes = await sync_to_async(_load_bytes, thread_sensitive=True)()
        if not image_bytes:
            raise ValueError("图片文件已丢失")

        provider = await sync_to_async(resolve_provider, thread_sensitive=True)("vision")
        result = None
        for attempt in range(2):
            try:
                result = await analyze_image(provider, image_bytes)
                break
            except ProviderError as exc:
                if attempt == 0 and exc.retryable:
                    await asyncio.sleep(0.5)
                    continue
                raise

        def _save():
            asset.vision_json = result or {}
            asset.save(update_fields=["vision_json"])

        await sync_to_async(_save, thread_sensitive=True)()
        timings = dict(state.get("timings") or {})
        timings["vision_ms"] = int((time.perf_counter() - started) * 1000)
        return {"vision": result, "timings": timings}
    except Exception as exc:
        logger.warning("analyze vision failed: %s", exc)
        if isinstance(exc, ProviderError):
            return {"error": f"VISION_ANALYZE: {exc.code} {exc.message}"}
        return {"error": f"VISION_ANALYZE: {exc}"}


async def recall_memory(state: AgentState) -> dict:
    await emit_state("thinking", node="recall_memory", emotion="37")
    from apps.chat import memory_service

    try:
        enabled = await sync_to_async(memory_service.is_enabled, thread_sensitive=True)()
        if not enabled:
            return {"memory": []}
        text = state.get("user_text") or ""
        memory = await sync_to_async(memory_service.recall, thread_sensitive=True)(text)
    except Exception:
        logger.warning("recall memory failed", exc_info=True)
        return {"memory": []}
    if memory:
        await emit(
            "memory",
            {
                "phase": "recall",
                "items": memory,
                "count": len(memory),
                "query": text[:120],
            },
        )
    return {"memory": memory}


async def fallback_reply(state: AgentState) -> dict:
    error = state.get("error") or ""
    vision = state.get("vision") or {}
    if error:
        reply, emotion, tips = _vision_failure_reply(error)
    elif vision.get("scene"):
        reply = f"我看到的是：{vision.get('scene')}。"
        emotion, tips = "03", "我看到了"
    else:
        reply = "刚才那一步没有成功，我们换一种方式再试一次吧。"
        emotion, tips = "34", "出了点问题"

    await emit_state("speaking", node="fallback_reply", emotion=emotion)
    for index in range(0, len(reply), 8):
        await emit("token", {"text": reply[index : index + 8]})
        await asyncio.sleep(0.015)
    return {
        "reply": reply,
        "emotion": emotion,
        "intensity": 0.8,
        "tips": tips,
    }


def _vision_failure_reply(error: str) -> tuple[str, str, str]:
    if "CAMERA_TOO_DARK" in error:
        return "画面有点暗，我看不太清。补点光，或者让我再试一次？", "34", "画面太暗"
    if "CAMERA_BLURRY" in error:
        return "画面有点糊，我认不出来。靠近一点或稳住摄像头再让我看看。", "11", "画面太模糊"
    if "CAMERA_BUSY" in error:
        return "摄像头正忙，等这一下处理完再让我看吧。", "34", "摄像头忙"
    if "VISION_ANALYZE" in error and ("PROVIDER_NOT_CONFIGURED" in error or "API" in error):
        return "我还没有配置视觉 Provider。打开设置填好智谱的 Key，我就能看图了。", "11", "视觉未配置"
    if "VISION_ANALYZE" in error:
        return "这次没看清。可以换个角度、靠近一点，或者直接把想说的告诉我。", "11", "没看清"
    if "VISION_CAPTURE" in error:
        return "摄像头这次没有打开成功。你可以检查一下是否被会议软件占用，或者先用文字跟我聊。", "34", "摄像头不可用"
    return "刚才那一步没有成功，我们换一种方式再试一次吧。", "34", "出了点问题"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
async def select_tools(state: AgentState) -> dict:
    query = state.get("user_text") or ""
    vision = state.get("vision") or {}
    if vision.get("scene"):
        query = f"{query} {vision.get('scene')}"
    picked = registry.search(query, k=settings.MCP_MAX_TOOLS_PER_TURN)
    if not picked:
        picked = [entry for entry in registry.list() if entry.source == "builtin"][:6]
    return {
        "selected_tools": [entry.name for entry in picked],
        "available_tools": [
            {"name": entry.name, "source": entry.source, "description": entry.description}
            for entry in registry.list()
        ],
    }


def tools_condition(state: AgentState) -> str:
    messages = state.get("messages") or []
    if not messages:
        return "end"
    return "tools" if getattr(messages[-1], "tool_calls", None) else "end"


async def execute_tool(state: AgentState) -> dict:
    await emit_state("acting", node="execute_tool", emotion="32")
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    calls = getattr(last, "tool_calls", None) or []
    outputs: list[ToolMessage] = []
    events: list[dict] = list(state.get("tool_events") or [])

    for raw_call in calls:
        name = raw_call.get("name") or (raw_call.get("function") or {}).get("name") or ""
        args = raw_call.get("args")
        if args is None:
            args = (raw_call.get("function") or {}).get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        call_id = raw_call.get("id") or f"call_{int(time.time() * 1000)}"

        entry: ToolEntry | None = registry.get(name)
        if entry is None:
            await registry.refresh()
            entry = registry.get(name)

        started = time.perf_counter()
        status = "ok"
        result_text = ""
        result_json: dict = {}
        timed_out = False
        try:
            if entry is None:
                raise ValueError(f"未知工具：{name}")
            if not entry.enabled:
                raise ValueError("工具已被禁用")
            result = await asyncio.wait_for(
                entry.tool.ainvoke(args or {}), timeout=max(3, settings.MCP_DEFAULT_TIMEOUT)
            )
            result_json = _jsonable(result)
            result_text = _stringify(result)
        except asyncio.TimeoutError:
            timed_out = True
            status = "timeout"
            result_text = "TOOL_ERROR: 工具执行超时"
            result_json = {"error": "timeout"}
        except Exception as exc:
            status = "error"
            result_text = f"TOOL_ERROR: {exc}"
            result_json = {"error": str(exc)}

        duration = int((time.perf_counter() - started) * 1000)
        preview = result_text[:500]
        events.append(
            {
                "name": name,
                "source": entry.source if entry else "unknown",
                "server": entry.server if entry else None,
                "args": args if isinstance(args, dict) else {},
                "status": status,
                "duration_ms": duration,
                "result_preview": preview,
                "result": result_json if isinstance(result_json, dict) else {"value": result_json},
            }
        )
        outputs.append(
            ToolMessage(
                content=result_text[: settings.MCP_MAX_RESULT_CHARS],
                tool_call_id=call_id,
                name=name,
            )
        )
        await emit(
            "tool",
            {
                "name": name,
                "source": entry.source if entry else "unknown",
                "server": entry.server if entry else None,
                "status": status,
                "duration_ms": duration,
                "result_preview": preview,
                "timeout": timed_out,
            },
        )

        await _persist_tool_call(
            state.get("run_id"),
            name=name,
            source=entry.source if entry else "unknown",
            server=entry.server if entry else "",
            args=args if isinstance(args, dict) else {},
            result=result_json if isinstance(result_json, dict) else {"value": result_json},
            preview=preview,
            status=status,
            duration_ms=duration,
        )

    return {
        "messages": outputs,
        "tool_events": events,
        "steps": int(state.get("steps") or 0) + 1,
    }


async def _persist_tool_call(run_id, **fields) -> None:
    if not run_id:
        return
    from apps.agent.models import ToolCall

    def _create():
        from apps.agent.models import AgentRun

        run = AgentRun.objects.filter(pk=run_id).first()
        if run is None:
            return
        ToolCall.objects.create(
            run=run,
            name=fields.get("name", ""),
            source=fields.get("source", "builtin"),
            server_name=fields.get("server") or "",
            args_json=fields.get("args") or {},
            result_json=fields.get("result") or {},
            result_preview=fields.get("preview", ""),
            status=fields.get("status", "ok"),
            duration_ms=int(fields.get("duration_ms") or 0),
        )

    try:
        await sync_to_async(_create, thread_sensitive=True)()
    except Exception:
        logger.warning("persist tool call failed", exc_info=True)


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------
async def compose(state: AgentState) -> dict:
    started = time.perf_counter()
    messages = _build_messages(state)
    selected = [
        registry.get(name) for name in state.get("selected_tools", []) if registry.get(name) is not None
    ]
    steps = int(state.get("steps") or 0)
    bind_tools = bool(selected) and steps < max(1, settings.AGENT_MAX_STEPS)
    tools_schema = [_tool_schema(entry) for entry in selected if entry is not None] if bind_tools else []

    provider = None
    try:
        from apps.providers.services import resolve_provider

        provider = await sync_to_async(resolve_provider, thread_sensitive=True)("chat")
    except Exception:
        provider = None

    if provider is None or not getattr(provider, "api_key", ""):
        result = await _local_fallback(state, reason="provider_missing")
        return _compose_result(result, state, started)

    extractor = JsonReplyExtractor()
    raw_tool_calls: list[dict] = []
    usage: dict = {}
    output_started = False
    emitted_any = False
    error: ProviderError | None = None

    for attempt in range(2):
        try:
            async for chunk in provider_stream(provider, messages, tools_schema):
                if chunk.usage:
                    usage = chunk.usage
                if chunk.tool_calls:
                    _merge_tool_call_deltas(raw_tool_calls, chunk.tool_calls)
                if chunk.text:
                    delta = extractor.feed(chunk.text)
                    if delta:
                        emitted_any = True
                        if not output_started:
                            output_started = True
                            await emit_state("speaking", node="compose", emotion="39")
                        await emit("token", {"text": delta})
            error = None
            break
        except ProviderError as exc:
            error = exc
            if attempt == 0 and exc.retryable and not emitted_any:
                await asyncio.sleep(0.5)
                extractor = JsonReplyExtractor()
                continue
            break

    if error is not None:
        logger.warning("chat provider failed: %s", error.message)
        result = await _local_fallback(state, reason=error.code)
        return _compose_result(result, state, started, usage=usage)

    data, reply = extractor.finalize()
    tool_calls = _normalize_tool_calls(raw_tool_calls)

    if tool_calls:
        ai_message = AIMessage(content=reply or "", tool_calls=tool_calls)
        timings = dict(state.get("timings") or {})
        timings["compose_ms"] = int((time.perf_counter() - started) * 1000)
        return {
            "messages": [ai_message],
            "usage": usage,
            "timings": timings,
        }

    if not reply.strip():
        result = await _local_fallback(state, reason="empty_reply")
        return _compose_result(result, state, started, usage=usage)

    emotion = data.get("emotionId") if isinstance(data, dict) else None
    intensity = data.get("intensity") if isinstance(data, dict) else None
    tips = data.get("tips") if isinstance(data, dict) else ""
    timings = dict(state.get("timings") or {})
    timings["compose_ms"] = int((time.perf_counter() - started) * 1000)
    return {
        "messages": [AIMessage(content=reply)],
        "reply": reply,
        "emotion": clean_emotion_id(emotion, "") if emotion else "",
        "emotion_source": "llm",
        "intensity": _safe_float(intensity, 0.7),
        "tips": str(tips or "")[:120],
        "usage": usage,
        "timings": timings,
    }


async def provider_stream(provider, messages: list[dict], tools: list[dict]):
    from services.llm import OpenAICompatChat

    chat = OpenAICompatChat(provider)
    async for chunk in chat.stream(
        messages,
        tools=tools or None,
        temperature=settings.AGENT_TEMPERATURE,
        json_mode=not tools,
    ):
        yield chunk


def _compose_result(result: dict, state: AgentState, started: float, usage: dict | None = None) -> dict:
    timings = dict(state.get("timings") or {})
    timings["compose_ms"] = int((time.perf_counter() - started) * 1000)
    payload = {
        "messages": [AIMessage(content=result.get("reply", ""))],
        "reply": result.get("reply", ""),
        "emotion": result.get("emotion", ""),
        "emotion_source": result.get("source", "rule"),
        "intensity": result.get("intensity", 0.6),
        "tips": result.get("tips", ""),
        "usage": usage or {},
        "timings": timings,
    }
    if result.get("error"):
        payload["error"] = result["error"]
    return payload


async def _local_fallback(state: AgentState, reason: str = "") -> dict:
    vision = state.get("vision") or {}
    memory = state.get("memory") or []
    error = state.get("error") or ""
    text = state.get("user_text") or ""
    proposal = propose_emotion(text, error=error, vision=vision)

    if error:
        reply, emotion, tips = _vision_failure_reply(error)
        proposal.update({"emotionId": emotion, "tips": tips})
    elif vision.get("scene"):
        objects = "、".join(vision.get("objects") or []) or "一些东西"
        reply = f"我看到{vision.get('scene')}，画面里有{objects}。"
        proposal.update({"emotionId": "03", "tips": "我看到了"})
    elif memory:
        fact = memory[0].get("fact", "")
        reply = f"我记得你提过：{fact}。"
        proposal.update({"emotionId": "37", "tips": "翻到一条记忆"})
    elif reason == "provider_missing":
        reply = (
            "我还没有配置对话 Provider。打开右上角设置，填入 DeepSeek 的 Base URL、"
            "模型和 Key，就能正常聊天了；语音、摄像头和小球现在都可以先用。"
        )
        proposal.update({"emotionId": "02", "tips": "等待配置"})
    elif reason == "empty_reply":
        reply = "我在，刚才没有组织好语言。你可以再说一遍吗？"
        proposal.update({"emotionId": "11", "tips": "再说一遍"})
    else:
        reply = "我在听。"
        proposal.update({"emotionId": "10", "tips": ""})

    await emit_state("speaking", node="compose", emotion=proposal.get("emotionId", "39"))
    for index in range(0, len(reply), 8):
        await emit("token", {"text": reply[index : index + 8]})
        await asyncio.sleep(0.015)

    result = {
        "reply": reply,
        "emotion": proposal.get("emotionId", "02"),
        "intensity": proposal.get("intensity", 0.6),
        "tips": proposal.get("tips", ""),
        "source": proposal.get("source", "rule"),
    }
    if error:
        result["error"] = error
    return result


def _build_messages(state: AgentState) -> list[dict]:
    system = compose_system()
    summary = (state.get("summary") or "").strip()
    if summary:
        system += f"\n\n会话摘要（更早的上下文）：{summary}"
    context = context_block(
        state.get("vision"),
        state.get("memory"),
        state.get("selected_tools", []),
        state.get("pinned_memory"),
    )
    if context:
        system += f"\n\n本轮上下文：\n{context}"

    messages: list[dict] = [{"role": "system", "content": system}]
    for item in state.get("history") or []:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    for message in state.get("messages") or []:
        converted = _message_to_openai(message)
        if converted:
            messages.append(converted)
    return messages


def _message_to_openai(message) -> dict | None:
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": _content_text(message.content)}
    if isinstance(message, AIMessage):
        payload: dict[str, Any] = {"role": "assistant", "content": _content_text(message.content) or ""}
        if getattr(message, "tool_calls", None):
            payload["tool_calls"] = [
                {
                    "id": call.get("id") or f"call_{index}",
                    "type": "function",
                    "function": {
                        "name": call.get("name", ""),
                        "arguments": json.dumps(call.get("args") or {}, ensure_ascii=False),
                    },
                }
                for index, call in enumerate(message.tool_calls)
            ]
        return payload
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": getattr(message, "tool_call_id", ""),
            "content": _content_text(message.content),
        }
    return None


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def _tool_schema(entry: ToolEntry) -> dict:
    return {
        "name": entry.name,
        "description": (entry.description or "")[:1000],
        "parameters": entry.input_schema or {"type": "object", "properties": {}},
    }


def _normalize_tool_calls(raw: list[dict]) -> list[dict]:
    calls: list[dict] = []
    for index, call in enumerate(raw):
        function = call.get("function") or {}
        name = function.get("name") or call.get("name") or ""
        if not name:
            continue
        args = function.get("arguments")
        if args is None:
            args = call.get("args")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {"value": args}
        calls.append(
            {
                "name": name,
                "args": args,
                "id": call.get("id") or f"call_{int(time.time() * 1000)}_{index}",
                "type": "tool_call",
            }
        )
    return calls


def _jsonable(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _stringify(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _safe_float(value, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 表情与持久化
# ---------------------------------------------------------------------------
async def plan_emotion(state: AgentState) -> dict:
    error = state.get("error")
    if error:
        _, emotion_id, tips = _vision_failure_reply(error)
        proposal = {"emotionId": emotion_id, "intensity": 0.8, "tips": tips, "source": "rule"}
    else:
        tool_emotion = None
        for event in reversed(state.get("tool_events") or []):
            if event.get("name") == "set_emotion" and event.get("status") == "ok":
                tool_emotion = (event.get("result") or {}).get("emotionId")
                if tool_emotion:
                    break
        if tool_emotion:
            proposal = {
                "emotionId": tool_emotion,
                "intensity": 0.8,
                "tips": "",
                "source": "llm",
            }
        elif state.get("emotion") and state.get("emotion") in allowed_ids():
            proposal = {
                "emotionId": state["emotion"],
                "intensity": state.get("intensity", 0.7),
                "tips": state.get("tips", ""),
                "source": state.get("emotion_source") or "llm",
            }
        else:
            proposal = propose_emotion(
                state.get("user_text", ""),
                state.get("reply", ""),
                state.get("vision"),
            )

    proposal = apply_emotion_proposal(proposal)
    await emit("emotion", proposal)
    return {
        "emotion": proposal["emotionId"],
        "emotion_source": proposal.get("source", "rule"),
        "intensity": proposal["intensity"],
        "tips": proposal["tips"],
    }


async def persist(state: AgentState) -> dict:
    from apps.agent.models import AgentRun
    from apps.chat.models import Conversation, EmotionEvent, Message

    run_id = state.get("run_id")
    reply = (state.get("reply") or "").strip() or "（没有生成回复）"
    emotion = state.get("emotion") or "02"
    usage = state.get("usage") or {}
    timings = state.get("timings") or {}
    latency_ms = int((time.perf_counter() - float(timings.get("started", time.perf_counter()))) * 1000)

    def _persist():
        conversation = Conversation.objects.filter(pk=state["conversation_id"]).first()
        if conversation is None:
            raise ValueError("conversation missing")
        message = Message.objects.create(
            conversation=conversation,
            role="assistant",
            content=reply,
            emotion_id=emotion,
            tokens_in=int(usage.get("in") or estimate_tokens(state.get("user_text", ""))),
            tokens_out=int(usage.get("out") or estimate_tokens(reply)),
            latency_ms=latency_ms,
            meta_json={"tool_events": state.get("tool_events") or [], "intent": state.get("intent")},
        )
        EmotionEvent.objects.create(
            conversation=conversation,
            message=message,
            emotion_id=emotion,
            intensity=float(state.get("intensity") or 0.5),
            source=state.get("emotion_source") or "rule",
            reason=(state.get("tips") or "")[:300],
        )
        if not conversation.title.strip():
            conversation.title = (state.get("user_text") or "新对话")[:24]
        conversation.save(update_fields=["title", "updated_at"])

        if run_id:
            run = AgentRun.objects.filter(pk=run_id).first()
            if run is not None:
                run.status = AgentRun.Status.OK
                run.intent = state.get("intent") or ""
                run.reply = reply
                run.emotion_id = emotion
                run.error = state.get("error") or ""
                run.latency_ms = latency_ms
                run.trace_json = {
                    "timings": timings,
                    "usage": usage,
                    "tool_events": state.get("tool_events") or [],
                    "vision": state.get("vision") or {},
                }
                run.finished_at = timezone.now()
                run.save()
        return str(message.id)

    assistant_message_id = await sync_to_async(_persist, thread_sensitive=True)()
    await emit_state("done", node="persist", emotion=emotion)

    # 记忆提取放到后台：不阻塞 SSE done，不把模型错误带进对话链路。
    try:
        if not state.get("error"):
            from apps.chat.memory_service import memory_settings, schedule_auto_extract

            conf = await sync_to_async(memory_settings, thread_sensitive=True)()
            if conf["enabled"] and conf["auto_extract"]:
                asyncio.create_task(
                    schedule_auto_extract(
                        str(state["conversation_id"]), state.get("user_text") or "", reply
                    )
                )
    except Exception:
        logger.warning("schedule memory extraction failed", exc_info=True)
    return {"assistant_message_id": assistant_message_id}
