"""MCP 客户端封装：stdio / http / sse → LangChain tools。"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger("moodball.mcp")


class McpError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LoadedMcpTool:
    name: str
    original_name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    tool: BaseTool | None = None


def resolve_command(command: str) -> str:
    """Windows 下 `npx` 实际是 `npx.cmd`；解析成绝对路径给 subprocess。"""
    if not command:
        return command
    if shutil.which(command):
        return shutil.which(command) or command
    for suffix in (".cmd", ".exe", ".bat", ".ps1"):
        candidate = shutil.which(command + suffix)
        if candidate:
            return candidate
    return command


def to_connection(server) -> dict[str, Any]:
    if server.transport == "stdio":
        connection: dict[str, Any] = {
            "transport": "stdio",
            "command": resolve_command(server.command),
            "args": list(server.args_json or []),
            # 子进程需要 SystemRoot / PATH 等基础环境；再叠加用户配置的 env。
            "env": {**os.environ, **dict(server.env_json or {})},
        }
        return connection
    if server.transport in {"http", "streamable_http"}:
        return {
            "transport": "http",
            "url": server.url,
            "headers": dict(server.headers_json or {}),
        }
    if server.transport == "sse":
        return {
            "transport": "sse",
            "url": server.url,
            "headers": dict(server.headers_json or {}),
        }
    raise McpError("MCP_BAD_TRANSPORT", f"不支持的 transport：{server.transport}")


def _schema_for(tool: BaseTool) -> dict:
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is None:
        return {}
    try:
        if hasattr(args_schema, "model_json_schema"):
            return args_schema.model_json_schema()
        if isinstance(args_schema, dict):
            return args_schema
    except Exception:
        pass
    return {}


def _rename_tool(tool: BaseTool, name: str, description: str) -> BaseTool:
    try:
        return tool.model_copy(update={"name": name, "description": description})
    except Exception:  # pragma: no cover - 兼容旧版 LangChain
        try:
            tool.name = name  # type: ignore[misc]
            tool.description = description  # type: ignore[misc]
            return tool
        except Exception:
            return tool


def _normalize_result(value):
    """MCP 常返回 content blocks；转成文本，模型更容易消费。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        texts = []
        for item in value:
            if isinstance(item, dict) and "text" in item:
                texts.append(str(item["text"]))
            else:
                texts.append(str(item))
        return "\n".join(texts)
    if isinstance(value, dict) and "text" in value:
        return str(value["text"])
    content = getattr(value, "content", None)
    if content is not None:
        return _normalize_result(content)
    return value


def _wrap_tool(tool: BaseTool, namespaced: str, description: str) -> BaseTool:
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is None:
        return _rename_tool(tool, namespaced, description)

    async def _call(_tool=tool, **kwargs):
        return _normalize_result(await _tool.ainvoke(kwargs))

    try:
        return StructuredTool.from_function(
            name=namespaced,
            description=description,
            args_schema=args_schema,
            coroutine=_call,
        )
    except Exception:
        return _rename_tool(tool, namespaced, description)


async def load_mcp_tools_for(server) -> list[LoadedMcpTool]:
    """启动一个 MCP server 会话并发现工具；失败抛 McpError。"""
    if not server.enabled:
        return []
    connection = to_connection(server)
    client = MultiServerMCPClient({server.name: connection}, handle_tool_errors=True)
    try:
        tools = await client.get_tools(server_name=server.name)
    except Exception as exc:
        raise McpError("MCP_DISCOVERY_FAILED", f"{server.name} 工具发现失败：{exc}") from exc

    prefix = (server.tool_prefix or f"mcp__{server.name}__").strip()
    if not prefix.endswith("__"):
        prefix = f"{prefix}__"
    loaded: list[LoadedMcpTool] = []
    for tool in tools:
        original = getattr(tool, "name", "") or "tool"
        namespaced = f"{prefix}{original}"
        description = (getattr(tool, "description", "") or "")[:1000]
        renamed = _wrap_tool(tool, namespaced, description)
        loaded.append(
            LoadedMcpTool(
                name=namespaced,
                original_name=original,
                description=description,
                input_schema=_schema_for(tool),
                tool=renamed,
            )
        )
    return loaded
