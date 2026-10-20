"""统一工具注册表：内置 + Python 插件 + MCP。"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

from asgiref.sync import sync_to_async
from django.conf import settings
from langchain_core.tools import BaseTool

from .mcp_client import load_mcp_tools_for
from .plugins import discover_plugin_tools
from .plugins.builtin_tools import BUILTIN_TOOLS

logger = logging.getLogger("moodball.tools")

_CJK = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class ToolEntry:
    name: str
    tool: BaseTool
    source: str  # builtin / plugin / mcp
    server: str | None = None
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    enabled: bool = True
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source,
            "server": self.server,
            "description": self.description,
            "input_schema": self.input_schema,
            "enabled": self.enabled,
            "tags": list(self.tags),
        }


class ToolRegistry:
    def __init__(self, ttl_s: int | None = None) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._last_refresh = 0.0
        self._ttl = settings.MCP_TOOL_TTL_SECONDS if ttl_s is None else ttl_s
        self._lock = asyncio.Lock()
        self.last_error: str = ""

    async def _enabled_servers(self) -> list:
        from apps.mcp.models import McpServer

        def _query():
            return list(McpServer.objects.filter(enabled=True).order_by("name"))

        return await sync_to_async(_query, thread_sensitive=True)()

    async def _disabled_mcp(self) -> set[tuple[str, str]]:
        from apps.mcp.models import McpTool

        def _query():
            return set(
                McpTool.objects.filter(enabled=False).values_list("server__name", "name")
            )

        return await sync_to_async(_query, thread_sensitive=True)()

    async def refresh(self, servers=None) -> None:
        if not settings.MCP_ENABLED:
            servers = []
        elif servers is None:
            servers = await self._enabled_servers()

        disabled = await self._disabled_mcp()
        async with self._lock:
            entries: list[ToolEntry] = []
            for tool in BUILTIN_TOOLS:
                entries.append(
                    ToolEntry(
                        name=tool.name,
                        tool=tool,
                        source="builtin",
                        description=(tool.description or "")[:1000],
                        input_schema=_tool_schema(tool),
                        tags=("builtin",),
                    )
                )
            for tool in discover_plugin_tools():
                entries.append(
                    ToolEntry(
                        name=tool.name,
                        tool=tool,
                        source="plugin",
                        description=(tool.description or "")[:1000],
                        input_schema=_tool_schema(tool),
                        tags=("plugin",),
                    )
                )

            errors: list[str] = []
            for server in servers:
                if not getattr(server, "enabled", True):
                    continue
                try:
                    loaded = await load_mcp_tools_for(server)
                except Exception as exc:
                    logger.warning("mcp server %s failed: %s", server.name, exc)
                    errors.append(f"{server.name}: {exc}")
                    continue
                for item in loaded:
                    if item.tool is None:
                        continue
                    entries.append(
                        ToolEntry(
                            name=item.name,
                            tool=item.tool,
                            source="mcp",
                            server=server.name,
                            description=item.description,
                            input_schema=item.input_schema,
                            enabled=(server.name, item.original_name) not in disabled,
                            tags=("mcp", server.name),
                        )
                    )

            self._tools = {entry.name: entry for entry in entries}
            self._last_refresh = time.time()
            self.last_error = "; ".join(errors)

    async def refresh_if_stale(self, servers=None) -> None:
        if time.time() - self._last_refresh > self._ttl:
            await self.refresh(servers)

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def list(self) -> list[ToolEntry]:
        return sorted(self._tools.values(), key=lambda item: (item.source, item.name))

    def search(self, query: str, k: int | None = None) -> list[ToolEntry]:
        limit = settings.MCP_MAX_TOOLS_PER_TURN if k is None else k
        query = (query or "").lower().strip()
        candidates = [entry for entry in self._tools.values() if entry.enabled]
        if not query:
            return candidates[:limit]

        tokens = [token for token in re.split(r"\s+", query) if token]
        if _CJK.search(query):
            compact = "".join(_CJK.findall(query))
            tokens.extend(compact[i : i + 2] for i in range(max(0, len(compact) - 1)))

        scored: list[tuple[int, ToolEntry]] = []
        for entry in candidates:
            hay = f"{entry.name} {entry.description} {' '.join(entry.tags)}".lower()
            score = 0
            if query in hay:
                score += 6
            for token in tokens:
                if token and token in hay:
                    score += 2
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [entry for _, entry in scored[:limit]]


def _tool_schema(tool: BaseTool) -> dict:
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


registry = ToolRegistry()
