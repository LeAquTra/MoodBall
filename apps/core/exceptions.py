"""统一 API 异常与 DRF 异常处理。"""

from __future__ import annotations

import logging
import uuid

from rest_framework.views import exception_handler as drf_default_handler

logger = logging.getLogger("moodball.api")


class ApiError(Exception):
    """业务可读错误；前端只展示 message，code 用于降级 / 埋点。"""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        retryable: bool = False,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        self.request_id = request_id

    def payload(self, request_id: str | None = None) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "request_id": request_id or self.request_id or f"req_{uuid.uuid4().hex[:12]}",
            }
        }


def drf_exception_handler(exc, context):
    """把 ApiError / ProviderError 也纳入 DRF 的错误体。"""
    from services.base import ProviderError

    if isinstance(exc, ApiError):
        from rest_framework.response import Response

        return Response(exc.payload(), status=exc.status)

    if isinstance(exc, ProviderError):
        from rest_framework.response import Response

        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    "request_id": f"req_{uuid.uuid4().hex[:12]}",
                }
            },
            status=exc.status,
        )

    response = drf_default_handler(exc, context)
    if response is not None:
        detail = response.data
        message = detail.get("detail") if isinstance(detail, dict) else str(detail)
        response.data = {
            "error": {
                "code": "VALIDATION_ERROR" if response.status_code < 500 else "SERVER_ERROR",
                "message": str(message or "请求无法处理"),
                "retryable": response.status_code >= 500,
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
            }
        }
        return response

    logger.exception("unhandled api error", exc_info=exc)
    from rest_framework.response import Response

    return Response(
        {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务内部错误，请查看后端日志。",
                "retryable": True,
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
            }
        },
        status=500,
    )
