"""会话 / 消息 REST 与 SSE 流式对话。"""

from __future__ import annotations

import logging
import uuid

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Count
from django.http import HttpRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response

from agent.service import agent_service
from apps.core.exceptions import ApiError
from apps.core.http import aread_json, json_error, json_ok, sse
from services.base import ProviderError, ProviderNotConfigured
from services.tts import synthesize

from . import memory_service
from .models import Conversation, EmotionEvent, MemoryFact, Message

logger = logging.getLogger("moodball.chat")

MAX_TEXT_LENGTH = 4000


def _conversation_payload(conversation: Conversation) -> dict:
    data = conversation.as_dict()
    data["message_count"] = getattr(conversation, "message_count", None)
    return data


@api_view(["GET", "POST"])
def conversations(request):
    if request.method == "GET":
        queryset = (
            Conversation.objects.annotate(message_count=Count("messages"))
            .filter(status=Conversation.Status.ACTIVE)
            .order_by("-updated_at")
        )
        status = request.query_params.get("status")
        if status:
            queryset = Conversation.objects.annotate(message_count=Count("messages")).filter(status=status)
        items = [_conversation_payload(item) for item in queryset[:100]]
        return Response({"ok": True, "items": items})

    data = request.data or {}
    title = str(data.get("title") or "").strip()[:200]
    conversation = Conversation.objects.create(title=title)
    return Response({"ok": True, "conversation": _conversation_payload(conversation)}, status=201)


@api_view(["GET", "PATCH", "DELETE"])
def conversation_detail(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)

    if request.method == "GET":
        conversation = Conversation.objects.annotate(message_count=Count("messages")).get(pk=conversation.pk)
        payload = _conversation_payload(conversation)
        payload["messages"] = [message.as_dict() for message in conversation.messages.all()]
        return Response({"ok": True, "conversation": payload})

    if request.method == "DELETE":
        conversation.delete()
        return Response({"ok": True, "deleted": str(conversation_id)})

    data = request.data or {}
    if "title" in data:
        conversation.title = str(data["title"]).strip()[:200]
    if "status" in data and data["status"] in dict(Conversation.Status.choices):
        conversation.status = data["status"]
    conversation.save()
    return Response({"ok": True, "conversation": _conversation_payload(conversation)})


@api_view(["GET"])
def conversation_messages(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    try:
        limit = max(1, min(int(request.query_params.get("limit", 100)), 500))
    except (TypeError, ValueError):
        limit = 100
    queryset = conversation.messages.all().order_by("created_at")
    total = queryset.count()
    items = list(queryset[:limit])
    return Response(
        {
            "ok": True,
            "items": [message.as_dict() for message in items],
            "total": total,
            "has_more": total > len(items),
        }
    )


@api_view(["GET"])
def conversation_events(request, conversation_id):
    get_object_or_404(Conversation, pk=conversation_id)
    events = EmotionEvent.objects.filter(conversation_id=conversation_id).order_by("created_at")[:500]
    runs = []
    try:
        from apps.agent.models import AgentRun

        runs = [run.as_dict() for run in AgentRun.objects.filter(conversation_id=conversation_id)[:30]]
    except Exception:
        pass
    return Response({"ok": True, "emotions": [event.as_dict() for event in events], "runs": runs})


@api_view(["GET"])
def conversation_export(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    conversation = Conversation.objects.annotate(message_count=Count("messages")).get(pk=conversation.pk)
    payload = _conversation_payload(conversation)
    payload["messages"] = [message.as_dict() for message in conversation.messages.all()]
    payload["emotion_events"] = [
        event.as_dict() for event in conversation.emotion_events.all()[:1000]
    ]
    return Response({"ok": True, "conversation": payload})


@api_view(["GET", "POST"])
def memories(request):
    if request.method == "GET":
        query = str(request.query_params.get("q") or "")
        tag = str(request.query_params.get("tag") or "")
        sort = str(request.query_params.get("sort") or "recent")
        try:
            limit = int(request.query_params.get("limit") or 200)
        except (TypeError, ValueError):
            limit = 200
        try:
            offset = int(request.query_params.get("offset") or 0)
        except (TypeError, ValueError):
            offset = 0
        result = memory_service.list_memories(query, tag, sort, limit, offset)
        return Response(
            {
                "ok": True,
                **result,
                "tags": memory_service.tag_counts(),
                "stats": memory_service.memory_stats(),
                "settings": memory_service.memory_settings(),
            }
        )

    data = request.data or {}
    fact = str(data.get("fact") or "").strip()
    if not fact:
        raise ApiError("INVALID_FACT", "fact 不能为空", 400)
    source = str(data.get("source") or MemoryFact.Source.MANUAL)
    if source not in {choice for choice, _ in MemoryFact.Source.choices}:
        source = MemoryFact.Source.MANUAL
    try:
        confidence = float(data.get("confidence") or 0.8)
    except (TypeError, ValueError):
        confidence = 0.8
    try:
        item, created = memory_service.create_memory(
            fact,
            data.get("tags") or "",
            source=source,
            pinned=bool(data.get("pinned")),
            confidence=confidence,
            conversation_id=data.get("conversation_id"),
        )
    except ValueError as exc:
        raise ApiError("INVALID_FACT", str(exc), 400) from exc
    return Response({"ok": True, "memory": item, "created": created}, status=201 if created else 200)


@api_view(["PATCH", "DELETE"])
def memory_detail(request, memory_id):
    item = get_object_or_404(MemoryFact, pk=memory_id)
    if request.method == "DELETE":
        memory_service.delete_memory(item)
        return Response({"ok": True, "deleted": str(memory_id)})

    data = request.data or {}
    try:
        memory = memory_service.update_memory(
            item,
            fact=data.get("fact"),
            tags=data.get("tags"),
            pinned=data.get("pinned") if "pinned" in data else None,
            confidence=data.get("confidence") if "confidence" in data else None,
        )
    except (ValueError, TypeError) as exc:
        raise ApiError("INVALID_MEMORY", str(exc), 400) from exc
    return Response({"ok": True, "memory": memory})


@api_view(["POST"])
def memories_bulk_delete(request):
    data = request.data or {}
    ids = data.get("ids")
    if not isinstance(ids, list):
        ids = []
    deleted = memory_service.bulk_delete(ids)
    return Response({"ok": True, "deleted": deleted, "stats": memory_service.memory_stats()})


@api_view(["POST"])
def memories_clear(request):
    data = request.data or {}
    keep_pinned = bool(data.get("keep_pinned", True))
    deleted = memory_service.clear_memories(keep_pinned=keep_pinned)
    return Response(
        {"ok": True, "deleted": deleted, "stats": memory_service.memory_stats()}
    )


# ---------------------------------------------------------------------------
# 对话：SSE / 非流式
# ---------------------------------------------------------------------------
async def _prepare_turn(request: HttpRequest, payload: dict):
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ApiError("EMPTY_TEXT", "text 不能为空", 400)
    if len(text) > MAX_TEXT_LENGTH:
        raise ApiError("TEXT_TOO_LONG", f"text 不能超过 {MAX_TEXT_LENGTH} 字", 400)

    conversation_id = payload.get("conversation_id")
    image_id = payload.get("image_id") or None
    with_vision = bool(payload.get("with_vision"))
    speak = bool(payload.get("speak", True))

    if conversation_id:
        try:
            uuid.UUID(str(conversation_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ApiError("INVALID_CONVERSATION_ID", "conversation_id 不是合法 UUID", 400) from exc
    if image_id:
        try:
            image_id = str(uuid.UUID(str(image_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ApiError("INVALID_IMAGE_ID", "image_id 不是合法 UUID", 400) from exc

    def _get_or_create():
        if conversation_id:
            conversation = Conversation.objects.filter(pk=conversation_id).first()
            if conversation is None:
                return None
            return conversation
        return Conversation.objects.create(title=text[:24])

    conversation = await sync_to_async(_get_or_create, thread_sensitive=True)()
    if conversation is None:
        raise ApiError("CONVERSATION_NOT_FOUND", "会话不存在", 404)

    def _save_message():
        return Message.objects.create(
            conversation=conversation,
            role="user",
            content=text,
            image_id=image_id,
        )

    user_message = await sync_to_async(_save_message, thread_sensitive=True)()
    return conversation, user_message, text, image_id, with_vision, speak


@csrf_exempt
async def chat_stream(request: HttpRequest):
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        payload = await aread_json(request)
        conversation, user_message, text, image_id, with_vision, speak = await _prepare_turn(request, payload)
    except ApiError as exc:
        return json_error(exc.code, exc.message, exc.status, exc.retryable, request)

    async def event_stream():
        meta = {
            "conversation_id": str(conversation.id),
            "user_message_id": str(user_message.id),
            "assistant_message_id": None,
        }
        yield sse("meta", meta)
        try:
            async for event in agent_service.stream(
                str(conversation.id),
                text,
                user_message_id=str(user_message.id),
                image_ref=image_id,
                with_vision=with_vision,
                speak=speak,
            ):
                name = event["event"]
                data = event["data"]
                if name == "final":
                    if speak and settings.TTS_ENABLED and data.get("reply"):
                        try:
                            asset = await synthesize(data["reply"])
                            yield sse(
                                "audio",
                                {
                                    "url": asset.url,
                                    "audio_id": str(asset.id),
                                    "duration_ms": asset.duration_ms,
                                },
                            )
                        except ProviderNotConfigured as exc:
                            # 没配置 TTS 是常态；不要每条消息都弹一次警告。
                            logger.info("tts not configured: %s", exc.message)
                        except ProviderError as exc:
                            logger.info("tts unavailable: %s", exc.message)
                            yield sse(
                                "warning",
                                {"code": exc.code, "message": "语音播报暂不可用，只显示文字。"},
                            )
                        except Exception:
                            logger.warning("tts failed", exc_info=True)
                    yield sse(
                        "done",
                        {
                            "conversation_id": str(conversation.id),
                            "message_id": data.get("message_id"),
                            "reply": data.get("reply"),
                            "emotionId": data.get("emotionId"),
                            "intensity": data.get("intensity"),
                            "tips": data.get("tips"),
                            "usage": data.get("usage"),
                            "latency_ms": data.get("latency_ms"),
                            "tool_events": data.get("tool_events") or [],
                        },
                    )
                elif name == "error":
                    yield sse("error", data)
                else:
                    yield sse(name, data)
        except Exception as exc:  # pragma: no cover - 生成器兜底
            logger.exception("chat stream failed")
            yield sse(
                "error",
                {"code": "STREAM_FAILED", "message": f"流式输出中断：{exc}", "retryable": True},
            )

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Connection"] = "keep-alive"
    response["X-Request-ID"] = f"req_{user_message.id.hex[:12]}"
    return response


@csrf_exempt
async def chat_once(request: HttpRequest):
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        payload = await aread_json(request)
        conversation, user_message, text, image_id, with_vision, speak = await _prepare_turn(request, payload)
    except ApiError as exc:
        return json_error(exc.code, exc.message, exc.status, exc.retryable, request)

    result = await agent_service.run(
        str(conversation.id),
        text,
        user_message_id=str(user_message.id),
        image_ref=image_id,
        with_vision=with_vision,
        speak=speak,
    )
    return json_ok(
        {
            "conversation_id": str(conversation.id),
            "user_message_id": str(user_message.id),
            "assistant": result,
        },
        request=request,
    )
