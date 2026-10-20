"""TTS 试听 / 音频文件 / 语音会话 API。"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import FileResponse, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from apps.core.http import aread_json, json_error, json_ok
from services.asr_client import asr_health
from services.base import ProviderError
from services.tts import preview

logger = logging.getLogger("moodball.voice")


@csrf_exempt
async def tts_preview(request: HttpRequest):
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        data = await aread_json(request)
    except ApiError as exc:
        return json_error(exc.code, exc.message, exc.status, exc.retryable, request)
    text = str(data.get("text") or "你好，我是 MoodBall。").strip()[: settings.TTS_MAX_CHARS]
    voice = data.get("voice") or None
    try:
        result = await preview(text, voice=voice)
    except ProviderError as exc:
        return json_error(exc.code, exc.message, exc.status, exc.retryable, request)
    except Exception as exc:
        logger.warning("tts preview failed", exc_info=True)
        return json_error("TTS_FAILED", str(exc), 502, True, request)
    return json_ok(result, request=request)


def audio_detail(request: HttpRequest, audio_id):
    from apps.voice.models import TTSAsset

    asset = get_object_or_404(TTSAsset, pk=audio_id)
    path = settings.MEDIA_ROOT / asset.path
    if not path.exists():
        return json_error("AUDIO_NOT_FOUND", "音频文件已被清理", 404, request=request)
    content_type = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "pcm": "audio/L16",
    }.get(asset.format.lower(), "application/octet-stream")
    response = FileResponse(open(path, "rb"), content_type=content_type)
    response["Cache-Control"] = "private, max-age=3600"
    response["Content-Length"] = str(path.stat().st_size)
    return response


@api_view(["GET"])
def voice_sessions(request):
    from apps.voice.models import VoiceSession

    queryset = VoiceSession.objects.all()[:100]
    conversation_id = request.query_params.get("conversation_id")
    if conversation_id:
        queryset = VoiceSession.objects.filter(conversation_id=conversation_id)[:100]
    return Response({"ok": True, "items": [session.as_dict() for session in queryset]})


@csrf_exempt
async def voice_status(request: HttpRequest) -> JsonResponse:
    health = await asr_health()
    return json_ok(
        {
            "asr": health,
            "enabled": settings.ASR_ENABLED,
            "wake_word": settings.WAKE_WORD,
            "command_timeout_ms": settings.COMMAND_TIMEOUT_MS,
            "tts_enabled": settings.TTS_ENABLED,
        },
        request=request,
    )
