"""核心 API：首页、健康检查、用户设置、表情清单。"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .exceptions import ApiError
from .http import json_error, json_ok, read_json
from .settings_service import get_settings, update_settings

logger = logging.getLogger("moodball.core")

EMOTION_LIST_CANDIDATES = (
    settings.BASE_DIR / "web" / "public" / "vendor" / "emotion-ball" / "emotion-list.json",
    settings.BASE_DIR / "web" / "dist" / "vendor" / "emotion-ball" / "emotion-list.json",
)

PLACEHOLDER = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>MoodBall</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0f1e;color:#e8edff;
font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.card{max-width:620px;padding:36px 40px;border:1px solid rgba(255,255,255,.12);border-radius:24px;
background:linear-gradient(160deg,rgba(124,247,255,.08),rgba(255,139,210,.06));line-height:1.8}
code{background:rgba(255,255,255,.08);padding:2px 7px;border-radius:6px;color:#8ef7ff}
h1{margin:0 0 8px;font-size:26px}p{color:#aeb8da}</style></head>
<body><div class="card"><h1>MoodBall</h1>
<p>后端已启动，但还没有前端构建产物。</p>
<p>开发模式：<code>cd web &amp;&amp; pnpm install &amp;&amp; pnpm dev</code>，打开 <code>http://localhost:5173</code>。</p>
<p>本机成品：<code>cd web &amp;&amp; pnpm build</code> 后刷新本页。</p>
<p>健康检查：<a style="color:#8ef7ff" href="/api/health/">/api/health/</a></p>
</div></body></html>"""


def home(request: HttpRequest) -> HttpResponse:
    index = settings.WEB_DIST / "index.html"
    if index.exists():
        return HttpResponse(index.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")
    return HttpResponse(PLACEHOLDER, content_type="text/html; charset=utf-8")


async def _db_check() -> dict:
    def _ping() -> dict:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True, "engine": "sqlite", "path": str(settings.SQLITE_PATH)}

    try:
        return await sync_to_async(_ping, thread_sensitive=True)()
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


async def _asr_check() -> dict:
    if not settings.ASR_ENABLED:
        return {"ok": False, "enabled": False, "message": "ASR 已关闭"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.ASR_BASE_URL}/health")
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {"ok": response.status_code < 400, "status": response.status_code, **body}
    except Exception as exc:
        return {"ok": False, "enabled": True, "message": f"ASR 未连接：{exc}"}


def _camera_check() -> dict:
    if not settings.CAMERA_ENABLED:
        return {"ok": False, "enabled": False, "message": "摄像头已关闭"}
    try:
        from services.camera import get_camera

        return {"ok": True, **get_camera().status()}
    except Exception as exc:
        return {"ok": False, "enabled": True, "message": str(exc)}


def _provider_check() -> dict:
    from apps.providers.services import provider_status

    return provider_status()


def _mcp_check() -> dict:
    try:
        from apps.mcp.models import McpServer

        total = McpServer.objects.count()
        enabled = McpServer.objects.filter(enabled=True).count()
        return {"ok": True, "total": total, "enabled": enabled}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "message": str(exc)}


async def health(request: HttpRequest) -> JsonResponse:
    db, asr, camera, providers, mcp = await asyncio.gather(
        _db_check(),
        _asr_check(),
        sync_to_async(_camera_check, thread_sensitive=True)(),
        sync_to_async(_provider_check, thread_sensitive=True)(),
        sync_to_async(_mcp_check, thread_sensitive=True)(),
        return_exceptions=True,
    )

    def unwrap(value):
        if isinstance(value, Exception):
            return {"ok": False, "message": str(value)}
        return value

    payload = {
        "ok": bool(unwrap(db).get("ok")) if isinstance(unwrap(db), dict) else False,
        "app": "moodball",
        "debug": settings.DEBUG,
        "mode": "personal" if settings.PERSONAL_MODE else "server",
        "db": unwrap(db),
        "asr": unwrap(asr),
        "camera": unwrap(camera),
        "providers": unwrap(providers),
        "mcp": unwrap(mcp),
        "time_zone": settings.TIME_ZONE,
    }
    return json_ok(payload, request=request)


@csrf_exempt
def settings_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return json_ok({"settings": get_settings()}, request=request)
    if request.method in {"PATCH", "PUT", "POST"}:
        try:
            patch = read_json(request)
            result = update_settings(patch)
        except ApiError as exc:
            return json_error(exc.code, exc.message, exc.status, exc.retryable, request)
        return json_ok({"settings": result}, request=request)
    return json_error("METHOD_NOT_ALLOWED", "只支持 GET / PATCH", 405, request=request)


def load_emotions() -> list[dict]:
    for path in EMOTION_LIST_CANDIDATES:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception as exc:  # pragma: no cover
            logger.warning("read emotion list failed: %s %s", path, exc)
    return []


def emotions(request: HttpRequest) -> JsonResponse:
    items = load_emotions()
    return json_ok({"items": items, "count": len(items)}, request=request)


def index_meta(request: HttpRequest) -> JsonResponse:
    """前端启动时需要的非敏感配置。"""
    return json_ok(
        {
            "app": "moodball",
            "version": "0.1.0",
            "wake_word": settings.WAKE_WORD,
            "wake_variants": settings.WAKE_VARIANTS,
            "wake_confirm_hits": settings.WAKE_CONFIRM_HITS,
            "asr_enabled": settings.ASR_ENABLED,
            "tts_enabled": settings.TTS_ENABLED,
            "camera_enabled": settings.CAMERA_ENABLED,
            "agent_enabled": settings.AGENT_ENABLED,
            "mcp_enabled": settings.MCP_ENABLED,
            "emotion_count": len(load_emotions()),
            "time_zone": settings.TIME_ZONE,
        },
        request=request,
    )


def media_file(request: HttpRequest, path: str) -> HttpResponse:
    """生产模式下 /media 的兜底服务；仅限 MEDIA_ROOT 内部。"""
    root: Path = settings.MEDIA_ROOT.resolve()
    target = (root / path).resolve()
    if root not in target.parents and target != root:
        raise ApiError("FORBIDDEN", "非法路径", status=403)
    if not target.exists() or not target.is_file():
        raise ApiError("NOT_FOUND", "文件不存在", status=404)
    content_type = "application/octet-stream"
    suffix = target.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        content_type = "image/jpeg"
    elif suffix == ".png":
        content_type = "image/png"
    elif suffix == ".wav":
        content_type = "audio/wav"
    elif suffix == ".mp3":
        content_type = "audio/mpeg"
    elif suffix == ".webp":
        content_type = "image/webp"
    return HttpResponse(target.read_bytes(), content_type=content_type)
