"""OpenAI-compatible 对话适配器（DeepSeek / 智谱文本）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator

import httpx

from services.base import ChatChunk, ChatProvider, ProviderError, ProviderNotConfigured

logger = logging.getLogger("moodball.llm")

_JSON_START = re.compile(r"\{")
_REPLY_KEY = re.compile(r'"reply"\s*:\s*"')


def chat_endpoint(profile) -> str:
    base = (profile.base_url or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def parse_json_object(text: str) -> dict | None:
    """从模型输出里提取第一个 JSON 对象；兼容 Markdown 代码块。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in _JSON_START.finditer(cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


class JsonReplyExtractor:
    """从流式 JSON 文本里增量提取 `reply` 字段，让首 token 尽快到达前端。

    模型偶尔会输出 Markdown 或非法 JSON；此时 finalize() 会退回全文。
    """

    def __init__(self) -> None:
        self.raw = ""
        self._search_from = 0
        self._scan = 0
        self._started = False
        self._finished = False
        self._decoded = ""

    def feed(self, token: str) -> str:
        if not token:
            return ""
        self.raw += token
        if self._finished:
            return ""
        if not self._started:
            match = _REPLY_KEY.search(self.raw, self._search_from)
            if not match:
                self._search_from = max(0, len(self.raw) - 16)
                return ""
            self._started = True
            self._scan = match.end()

        out: list[str] = []
        while self._scan < len(self.raw):
            char = self.raw[self._scan]
            if char == '"':
                self._finished = True
                self._scan += 1
                break
            if char == "\\":
                if self._scan + 1 >= len(self.raw):
                    break
                escape = self.raw[self._scan + 1]
                if escape == "u":
                    if self._scan + 6 > len(self.raw):
                        break
                    hex_value = self.raw[self._scan + 2 : self._scan + 6]
                    try:
                        out.append(chr(int(hex_value, 16)))
                    except ValueError:
                        out.append("\\u" + hex_value)
                    self._scan += 6
                    continue
                mapping = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                out.append(mapping.get(escape, "\\" + escape))
                self._scan += 2
                continue
            out.append(char)
            self._scan += 1

        delta = "".join(out)
        self._decoded += delta
        return delta

    @property
    def reply(self) -> str:
        return self._decoded

    def finalize(self) -> tuple[dict | None, str]:
        data = parse_json_object(self.raw) if self.raw else None
        if data and isinstance(data.get("reply"), str):
            reply = data["reply"].strip()
            if reply:
                # 已经流出的内容与最终解析不一致时，以流出的为准（前端已显示）。
                return data, self._decoded.strip() or reply
        if data:
            for key in ("text", "answer", "content", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return data, value.strip()
        fallback = self._decoded.strip()
        if not fallback:
            fallback = self.raw.strip()
        return data, fallback


class OpenAICompatChat(ChatProvider):
    def __init__(self, profile) -> None:
        self.profile = profile
        self.extra = profile.extra_json or {}
        self.timeout = float(self.extra.get("timeout", 60))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.profile.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None,
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool,
        stream: bool,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.profile.model,
            "messages": messages,
            "stream": stream,
            "temperature": self.extra.get("temperature", 0.7) if temperature is None else temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [{"type": "function", "function": tool} for tool in tools]
            payload["tool_choice"] = "auto"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if stream and self.extra.get("stream_usage"):
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[ChatChunk]:
        if not self.profile.api_key:
            raise ProviderNotConfigured("chat")
        if not self.profile.base_url or not self.profile.model:
            raise ProviderNotConfigured("chat")

        payload = self._payload(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            stream=True,
        )
        timeout = httpx.Timeout(connect=10.0, read=self.timeout, write=30.0, pool=10.0)
        endpoint = chat_endpoint(self.profile)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream(
                    "POST", endpoint, headers=self._headers(), json=payload
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", "replace")[:800]
                        raise ProviderError(
                            f"CHAT_HTTP_{response.status_code}",
                            _friendly_http_error(response.status_code, body),
                            retryable=response.status_code in {408, 409, 429, 500, 502, 503, 504},
                            status=502,
                        )
                    async for line in response.aiter_lines():
                        chunk = _parse_sse_line(line)
                        if chunk is None:
                            continue
                        if chunk == "DONE":
                            break
                        yield chunk
            except httpx.TimeoutException as exc:
                raise ProviderError("CHAT_TIMEOUT", "对话服务响应超时，请稍后重试。", retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError("CHAT_NETWORK", f"连接对话服务失败：{exc}", retryable=True) from exc


def _parse_sse_line(line: str) -> ChatChunk | str | None:
    if not line or line.startswith(":") or line.startswith("event:"):
        return None
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if data == "[DONE]":
        return "DONE"
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        logger.debug("unparseable sse chunk: %s", data[:200])
        return None

    usage = obj.get("usage") or {}
    choices = obj.get("choices") or []
    if not choices:
        return ChatChunk(usage=_normalize_usage(usage)) if usage else None
    choice = choices[0]
    delta = choice.get("delta") or {}
    return ChatChunk(
        text=delta.get("content") or "",
        reasoning=delta.get("reasoning_content") or "",
        tool_calls=delta.get("tool_calls") or [],
        usage=_normalize_usage(usage) if usage else {},
        finish_reason=choice.get("finish_reason"),
    )


def _normalize_usage(usage: dict) -> dict:
    if not usage:
        return {}
    return {
        "in": usage.get("prompt_tokens", 0),
        "out": usage.get("completion_tokens", 0),
        "total": usage.get("total_tokens", 0),
    }


def _friendly_http_error(status: int, body: str) -> str:
    if status == 401:
        return "Provider 鉴权失败（401），请检查 API Key 与 Base URL 是否匹配。"
    if status == 403:
        return "Provider 拒绝访问（403），请检查模型权限或余额。"
    if status == 404:
        return "Provider 接口不存在（404），请检查 Base URL 与模型名。"
    if status == 429:
        return "Provider 限流或余额不足（429），请稍后重试。"
    if status >= 500:
        return f"Provider 服务异常（{status}），请稍后重试。"
    return f"Provider 返回错误（{status}）：{body}"


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = max(0, len(text) - chinese)
    return int(chinese * 0.7 + other / 3.2) + 1
