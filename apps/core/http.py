"""轻量 JSON 响应 / 请求工具，供普通 Django 视图与 SSE 使用。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.http import HttpRequest, JsonResponse

from .exceptions import ApiError


def request_id(request: HttpRequest | None = None) -> str:
    if request is not None:
        incoming = request.headers.get("X-Request-ID", "").strip()
        if incoming:
            return incoming
    return f"req_{uuid.uuid4().hex[:12]}"


def json_ok(data: Any = None, status: int = 200, request: HttpRequest | None = None) -> JsonResponse:
    payload = {"ok": True}
    if isinstance(data, dict):
        payload.update(data)
    elif data is not None:
        payload["data"] = data
    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["X-Request-ID"] = request_id(request)
    return response


def json_error(
    code: str,
    message: str,
    status: int = 400,
    retryable: bool = False,
    request: HttpRequest | None = None,
    extra: dict | None = None,
) -> JsonResponse:
    error = ApiError(code, message, status, retryable, request_id(request))
    payload = error.payload()
    if extra:
        payload["error"].update(extra)
    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["X-Request-ID"] = payload["error"]["request_id"]
    return response


def read_json(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        value = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError("INVALID_JSON", f"请求体不是合法 JSON：{exc}", status=400) from exc
    if not isinstance(value, dict):
        raise ApiError("INVALID_JSON", "请求体必须是 JSON 对象", status=400)
    return value


async def aread_json(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        value = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError("INVALID_JSON", f"请求体不是合法 JSON：{exc}", status=400) from exc
    if not isinstance(value, dict):
        raise ApiError("INVALID_JSON", "请求体必须是 JSON 对象", status=400)
    return value


def sse(event: str, data: dict | str) -> str:
    body = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n"


def bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
