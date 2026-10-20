"""摄像头与图像 API。"""

from __future__ import annotations

import logging

from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.core.http import json_error, json_ok, read_json
from services.camera import CameraError, get_camera, reset_camera
from services.images import save_image

logger = logging.getLogger("moodball.vision")


def _camera_error(exc: CameraError, request: HttpRequest) -> JsonResponse:
    return json_error(exc.code, exc.message, 503 if exc.code != "CAMERA_BUSY" else 409, request=request)


@csrf_exempt
def snapshot(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    conversation_id = request.POST.get("conversation_id") or None
    if request.body and not conversation_id:
        try:
            conversation_id = (read_json(request).get("conversation_id")) or None
        except Exception:
            conversation_id = None
    try:
        snap = get_camera().snapshot()
    except CameraError as exc:
        return _camera_error(exc, request)
    try:
        asset = save_image(snap.jpeg, conversation_id=conversation_id)
    except Exception as exc:
        logger.exception("save image failed")
        return json_error("IMAGE_SAVE_FAILED", f"图片保存失败：{exc}", 500, True, request)
    payload = asset.as_dict()
    payload["image"] = payload.copy()
    return json_ok(payload, request=request)

@csrf_exempt
def preview(request: HttpRequest) -> StreamingHttpResponse | JsonResponse:
    if request.method not in {"GET", "HEAD"}:
        return json_error("METHOD_NOT_ALLOWED", "只支持 GET", 405, request=request)
    camera = get_camera()
    status = camera.status()
    if not status["opencv"]:
        return json_error("CAMERA_OPENCV_MISSING", "没有安装 opencv-python。", 503, request=request)
    if not status["enabled"]:
        return json_error("CAMERA_DISABLED", "摄像头已在配置中关闭。", 503, request=request)

    response = StreamingHttpResponse(
        camera.mjpeg_frames(),
        content_type="multipart/x-mixed-replace; boundary=frame",
    )
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response["Pragma"] = "no-cache"
    return response


@csrf_exempt
def release(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    get_camera().release()
    return json_ok({"released": True}, request=request)


@csrf_exempt
def camera_status(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        get_camera().maybe_release_idle()
        return json_ok({"camera": get_camera().status()}, request=request)
    if request.method == "POST":
        camera = reset_camera()
        return json_ok({"camera": camera.status()}, request=request)
    return json_error("METHOD_NOT_ALLOWED", "只支持 GET / POST", 405, request=request)


@csrf_exempt
def images(request: HttpRequest) -> JsonResponse:
    from apps.vision.models import ImageAsset

    if request.method == "GET":
        conversation_id = request.GET.get("conversation_id")
        queryset = ImageAsset.objects.all()
        if conversation_id:
            queryset = queryset.filter(conversation_id=conversation_id)
        items = [asset.as_dict() for asset in queryset[:100]]
        return json_ok({"items": items}, request=request)
    if request.method == "DELETE":
        from django.conf import settings

        count = 0
        for asset in ImageAsset.objects.all():
            try:
                (settings.MEDIA_ROOT / asset.path).unlink(missing_ok=True)
            except Exception:
                pass
            asset.delete()
            count += 1
        return json_ok({"deleted": count}, request=request)
    return json_error("METHOD_NOT_ALLOWED", "只支持 GET / DELETE", 405, request=request)


@csrf_exempt
def image_detail(request: HttpRequest, image_id) -> JsonResponse:
    from django.shortcuts import get_object_or_404

    from apps.vision.models import ImageAsset

    asset = get_object_or_404(ImageAsset, pk=image_id)
    if request.method == "GET":
        return json_ok({"image": asset.as_dict()}, request=request)
    if request.method == "DELETE":
        from django.conf import settings

        (settings.MEDIA_ROOT / asset.path).unlink(missing_ok=True)
        asset.delete()
        return json_ok({"deleted": str(image_id)}, request=request)
    return json_error("METHOD_NOT_ALLOWED", "只支持 GET / DELETE", 405, request=request)


@csrf_exempt
def analyze(request: HttpRequest) -> JsonResponse:
    """手动测试视觉：抓一帧或使用 image_id，返回结构化 JSON。"""
    import asyncio

    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        payload = read_json(request)
    except Exception:
        payload = {}
    image_id = payload.get("image_id")
    from apps.providers.services import resolve_provider
    from apps.vision.models import ImageAsset
    from django.conf import settings
    from services.vision import analyze_image

    try:
        if image_id:
            asset = ImageAsset.objects.filter(pk=image_id).first()
            if asset is None:
                return json_error("IMAGE_NOT_FOUND", "图片不存在", 404, request=request)
            image_bytes = (settings.MEDIA_ROOT / asset.path).read_bytes()
        else:
            snap = get_camera().snapshot()
            asset = save_image(snap.jpeg, conversation_id=payload.get("conversation_id"))
            image_bytes = snap.jpeg
    except CameraError as exc:
        return _camera_error(exc, request)
    except Exception as exc:
        return json_error("IMAGE_READ_FAILED", str(exc), 500, True, request)

    provider = resolve_provider("vision")
    try:
        result = asyncio.run(analyze_image(provider, image_bytes))
    except Exception as exc:
        return json_error("VISION_FAILED", str(exc), 502, True, request)

    asset.vision_json = result
    asset.save(update_fields=["vision_json"])
    return json_ok({"image": asset.as_dict(), "vision": result}, request=request)
