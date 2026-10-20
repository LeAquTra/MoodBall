"""MCP 配置的持久化、工具缓存同步与导入导出。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from agent.mcp_client import McpError, load_mcp_tools_for

from .models import McpServer, McpTool

logger = logging.getLogger("moodball.mcp")


async def discover_server(server: McpServer) -> list[dict]:
    """启动 server 并刷新 McpTool 缓存。"""
    loaded = await load_mcp_tools_for(server)
    def _persist():
        seen = []
        for item in loaded:
            McpTool.objects.update_or_create(
                server=server,
                name=item.original_name,
                defaults={
                    "description": item.description,
                    "input_schema": item.input_schema,
                },
            )
            seen.append(item.original_name)
        McpTool.objects.filter(server=server).exclude(name__in=seen).delete()
        server.last_error = ""
        server.last_seen_at = timezone.now()
        server.save(update_fields=["last_error", "last_seen_at", "updated_at"])
        return [
            {
                "name": item.name,
                "original_name": item.original_name,
                "description": item.description,
                "input_schema": item.input_schema,
            }
            for item in loaded
        ]

    try:
        return await sync_to_async(_persist, thread_sensitive=True)()
    except McpError:
        raise
    except Exception as exc:
        def _mark_error():
            server.last_error = str(exc)[:2000]
            server.save(update_fields=["last_error", "updated_at"])

        await sync_to_async(_mark_error, thread_sensitive=True)()
        raise McpError("MCP_DISCOVERY_FAILED", f"{server.name} 工具发现失败：{exc}") from exc


async def refresh_registry() -> None:
    from agent.registry import registry

    await registry.refresh()


def load_config_file(path: Path | None = None) -> dict:
    path = path or settings.MCP_CONFIG_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise McpError("MCP_CONFIG_INVALID", f"MCP 配置文件不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise McpError("MCP_CONFIG_INVALID", "MCP 配置必须是 {name: connection} 对象")
    return data


def import_config(path: Path | None = None) -> int:
    data = load_config_file(path)
    count = 0
    for name, connection in data.items():
        if not isinstance(connection, dict):
            continue
        transport = str(connection.get("transport") or "stdio")
        McpServer.objects.update_or_create(
            name=name[:80],
            defaults={
                "transport": transport if transport in dict(McpServer.Transport.choices) else "stdio",
                "command": str(connection.get("command") or "")[:300],
                "args_json": connection.get("args") or [],
                "env_json": connection.get("env") or {},
                "url": str(connection.get("url") or "")[:500],
                "headers_json": connection.get("headers") or {},
                "enabled": bool(connection.get("enabled", True)),
                "auto_start": bool(connection.get("auto_start", True)),
                "timeout_s": int(connection.get("timeout_s", settings.MCP_DEFAULT_TIMEOUT)),
            },
        )
        count += 1
    return count


def export_config(path: Path | None = None) -> dict:
    path = path or settings.MCP_CONFIG_PATH
    data = {}
    for server in McpServer.objects.all():
        if server.transport == "stdio":
            data[server.name] = {
                "transport": "stdio",
                "command": server.command,
                "args": server.args_json,
                "env": server.env_json,
            }
        else:
            data[server.name] = {
                "transport": server.transport,
                "url": server.url,
                "headers": server.headers_json,
            }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
