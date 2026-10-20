"""能力适配器基类与统一错误。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


class ProviderError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status = status


class ProviderNotConfigured(ProviderError):
    def __init__(self, kind: str) -> None:
        super().__init__(
            "PROVIDER_NOT_CONFIGURED",
            f"还没有配置 {kind} Provider。请在设置页填写 Base URL、模型与 Key。",
            retryable=False,
            status=400,
        )


@dataclass
class ChatChunk:
    text: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str | None = None


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str | None = None


class ChatProvider(ABC):
    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[ChatChunk]:
        raise NotImplementedError

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> ChatResult:
        result = ChatResult()
        async for chunk in self.stream(messages, **kwargs):
            if chunk.text:
                result.content += chunk.text
            if chunk.usage:
                result.usage = chunk.usage
            if chunk.finish_reason:
                result.finish_reason = chunk.finish_reason
            if chunk.tool_calls:
                _merge_tool_call_deltas(result.tool_calls, chunk.tool_calls)
        return result


def _merge_tool_call_deltas(acc: list[dict], deltas: list[dict]) -> None:
    for delta in deltas:
        index = delta.get("index", len(acc))
        while len(acc) <= index:
            acc.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
        target = acc[index]
        if delta.get("id"):
            target["id"] = delta["id"]
        function = delta.get("function") or {}
        if function.get("name"):
            target["function"]["name"] += function["name"]
        if function.get("arguments"):
            target["function"]["arguments"] += function["arguments"]


class VisionProvider(ABC):
    @abstractmethod
    async def analyze(self, image_jpeg: bytes, prompt: str) -> dict:
        raise NotImplementedError


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str, **kwargs: Any) -> bytes:
        raise NotImplementedError
