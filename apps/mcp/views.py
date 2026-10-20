"""MCP 与工具注册表 API（个人本机模式，不做审批）。"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from asgiref.sync import sync_to_async
from django.db.models import Count
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.core.exceptions import ApiError
from apps.core.http import aread_json, json_error, json_ok

from .models import McpServer, McpTool
from .services import discover_server, export_config, import_config

logger = logging.getLogger("moodball.mcp")


def _jsonable(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _server_payload(server: McpServer, tools: list[dict] | None = None) -> dict:
    data = server.as_dict(with_tools=False)
    tool_list = tools or []
    data["tools"] = tool_list
    data["tool_count"] = len(tool_list) if tools is not None else getattr(server, "tool_count", 0) or 0
    return data


@csrf_exempt
async def mcp_servers(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        def _list():
            rows = McpServer.objects.annotate(tool_count=Count("tools")).prefetch_related("tools")
            return [
                _server_payload(row, tools=[tool.as_dict() for tool in row.tools.all()])
                for row in rows
            ]

        return json_ok({"items": await sync_to_async(_list, thread_sensitive=True)()}, request=request)

    if request.method == "POST":
        try:
            data = await aread_json(request)
        except ApiError as exc:
            return json_error(exc.code, exc.message, exc.status, exc.retryable, request)
        name = str(data.get("name") or "").strip()
        transport = str(data.get("transport") or "stdio")
        if not 1 <= len(name) <= 80:
            return json_error("INVALID_NAME", "name 长度必须在 1–80 之间", 400, request=request)
        if transport not in dict(McpServer.Transport.choices):
            return json_error("INVALID_TRANSPORT", "transport 必须是 stdio / http / sse", 400, request=request)
        command = str(data.get("command") or "").strip()
        url = str(data.get("url") or "").strip()
        if transport == "stdio" and not command:
            return json_error("MCP_COMMAND_REQUIRED", "stdio server 必须填写 command", 400, request=request)
        if transport != "stdio" and not url.startswith(("http://", "https://")):
            return json_error("MCP_URL_REQUIRED", "http / sse server 必须填写 http(s) URL", 400, request=request)

        def _create():
            return McpServer.objects.create(
                name=name,
                transport=transport,
                command=command,
                args_json=data.get("args") or [],
                env_json=data.get("env") or {},
                url=url,
                headers_json=data.get("headers") or {},
                tool_prefix=str(data.get("tool_prefix") or ""),
                enabled=bool(data.get("enabled", True)),
                auto_start=bool(data.get("auto_start", True)),
                timeout_s=max(1, int(data.get("timeout_s") or 30)),
            )

        try:
            server = await sync_to_async(_create, thread_sensitive=True)()
        except Exception as exc:
            return json_error("MCP_CREATE_FAILED", f"创建失败（名称可能重复）：{exc}", 409, request=request)
        return json_ok({"server": _server_payload(server, tools=[])}, status=201, request=request)

    return json_error("METHOD_NOT_ALLOWED", "只支持 GET / POST", 405, request=request)


@csrf_exempt
async def mcp_server_detail(request: HttpRequest, server_id) -> JsonResponse:
    def _load():
        server = McpServer.objects.filter(pk=server_id).first()
        if server is None:
            return None, []
        return server, [tool.as_dict() for tool in server.tools.all()]

    server, tool_list = await sync_to_async(_load, thread_sensitive=True)()
    if server is None:
        return json_error("MCP_NOT_FOUND", "MCP server 不存在", 404, request=request)

    if request.method == "GET":
        return json_ok({"server": _server_payload(server, tools=tool_list)}, request=request)

    if request.method == "DELETE":
        def _delete():
            server.delete()

        await sync_to_async(_delete, thread_sensitive=True)()
        from agent.registry import registry

        await registry.refresh()
        return json_ok({"deleted": str(server_id)}, request=request)

    if request.method in {"PATCH", "PUT"}:
        try:
            data = await aread_json(request)
        except ApiError as exc:
            return json_error(exc.code, exc.message, exc.status, exc.retryable, request)
        for field in (
            "name",
            "transport",
            "command",
            "url",
            "tool_prefix",
        ):
            if field in data:
                setattr(server, field, str(data[field])[:500])
        if server.transport not in dict(McpServer.Transport.choices):
            return json_error("INVALID_TRANSPORT", "transport 必须是 stdio / http / sse", 400, request=request)
        if "args" in data:
            server.args_json = data["args"] if isinstance(data["args"], list) else []
        if "env" in data:
            server.env_json = data["env"] if isinstance(data["env"], dict) else {}
        if "headers" in data:
            server.headers_json = data["headers"] if isinstance(data["headers"], dict) else {}
        if "enabled" in data:
            server.enabled = bool(data["enabled"])
        if "auto_start" in data:
            server.auto_start = bool(data["auto_start"])
        if "timeout_s" in data:
            server.timeout_s = max(1, int(data["timeout_s"]))

        def _save():
            server.save()

        await sync_to_async(_save, thread_sensitive=True)()
        from agent.registry import registry

        await registry.refresh()
        return json_ok({"server": _server_payload(server, tools=tool_list)}, request=request)

    return json_error("METHOD_NOT_ALLOWED", "只支持 GET / PATCH / DELETE", 405, request=request)


@csrf_exempt
async def mcp_server_test(request: HttpRequest, server_id) -> JsonResponse:
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        server = await sync_to_async(McpServer.objects.get, thread_sensitive=True)(pk=server_id)
    except McpServer.DoesNotExist:
        return json_error("MCP_NOT_FOUND", "MCP server 不存在", 404, request=request)

    started = time.perf_counter()
    try:
        tools = await asyncio.wait_for(discover_server(server), timeout=max(3, server.timeout_s))
    except asyncio.TimeoutError:
        server.last_error = f"测试超时（{server.timeout_s}s）"
        await sync_to_async(server.save, thread_sensitive=True)(update_fields=["last_error", "updated_at"])
        return json_error(
            "MCP_TIMEOUT", f"启动 / 发现工具超时（{server.timeout_s}s）", 504, True, request
        )
    except Exception as exc:
        return json_error("MCP_TEST_FAILED", str(exc), 502, True, request)

    return json_ok(
        {
            "tools": tools,
            "tool_count": len(tools),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        },
        request=request,
    )


@csrf_exempt
async def mcp_server_refresh(request: HttpRequest, server_id) -> JsonResponse:
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        server = await sync_to_async(McpServer.objects.get, thread_sensitive=True)(pk=server_id)
    except McpServer.DoesNotExist:
        return json_error("MCP_NOT_FOUND", "MCP server 不存在", 404, request=request)

    try:
        tools = await asyncio.wait_for(discover_server(server), timeout=max(3, server.timeout_s))
    except Exception as exc:
        return json_error("MCP_REFRESH_FAILED", str(exc), 502, True, request)

    from agent.registry import registry

    await registry.refresh()
    return json_ok(
        {"tools": tools, "tool_count": len(tools), "registry_size": len(registry.list())},
        request=request,
    )


@csrf_exempt
async def mcp_import(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        data = await aread_json(request)
    except ApiError as exc:
        return json_error(exc.code, exc.message, exc.status, exc.retryable, request)
    if isinstance(data, dict) and data.get("servers"):
        servers = data["servers"]
        def _import_inline():
            count = 0
            for name, connection in servers.items():
                if not isinstance(connection, dict):
                    continue
                McpServer.objects.update_or_create(
                    name=str(name)[:80],
                    defaults={
                        "transport": connection.get("transport", "stdio"),
                        "command": str(connection.get("command") or "")[:300],
                        "args_json": connection.get("args") or [],
                        "env_json": connection.get("env") or {},
                        "url": str(connection.get("url") or "")[:500],
                        "headers_json": connection.get("headers") or {},
                    },
                )
                count += 1
            return count

        count = await sync_to_async(_import_inline, thread_sensitive=True)()
    else:
        count = await sync_to_async(import_config, thread_sensitive=True)()
    from agent.registry import registry

    await registry.refresh()
    return json_ok({"imported": count}, request=request)


@csrf_exempt
async def mcp_export(request: HttpRequest) -> JsonResponse:
    data = await sync_to_async(export_config, thread_sensitive=True)()
    return json_ok({"config": data}, request=request)


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------
@csrf_exempt
async def tools_view(request: HttpRequest) -> JsonResponse:
    from agent.registry import registry

    await registry.refresh_if_stale()
    return json_ok(
        {
            "items": [entry.as_dict() for entry in registry.list()],
            "last_error": registry.last_error,
        },
        request=request,
    )


@csrf_exempt
async def tools_refresh(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    from agent.registry import registry

    await registry.refresh()
    return json_ok(
        {"items": [entry.as_dict() for entry in registry.list()], "last_error": registry.last_error},
        request=request,
    )


@csrf_exempt
async def tool_toggle(request: HttpRequest, name: str) -> JsonResponse:
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        data = await aread_json(request)
    except ApiError as exc:
        return json_error(exc.code, exc.message, exc.status, exc.retryable, request)
    enabled = bool(data.get("enabled", True))

    def _toggle():
        tool = McpTool.objects.filter(name=name).first()
        if tool is None:
            tool = McpTool.objects.filter(name__endswith=f"{name.split('__')[-1]}").first()
        if tool is None:
            return None
        tool.enabled = enabled
        tool.save(update_fields=["enabled", "last_seen_at"])
        return tool.as_dict()

    result = await sync_to_async(_toggle, thread_sensitive=True)()
    if result is None:
        return json_error("TOOL_NOT_MCP", "只有 MCP 工具支持在设置页启停", 400, request=request)
    from agent.registry import registry

    await registry.refresh()
    return json_ok({"tool": result}, request=request)


@csrf_exempt
async def tool_invoke(request: HttpRequest, name: str) -> JsonResponse:
    if request.method != "POST":
        return json_error("METHOD_NOT_ALLOWED", "只支持 POST", 405, request=request)
    try:
        data = await aread_json(request)
    except ApiError as exc:
        return json_error(exc.code, exc.message, exc.status, exc.retryable, request)
    args = data.get("args") if isinstance(data.get("args"), dict) else {}

    from agent.registry import registry

    if registry.get(name) is None:
        await registry.refresh()
    entry = registry.get(name)
    if entry is None:
        return json_error("TOOL_NOT_FOUND", f"工具不存在：{name}", 404, request=request)

    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            entry.tool.ainvoke(args), timeout=max(3, settings_timeout())
        )
        status = "ok"
        error = None
    except asyncio.TimeoutError:
        result = None
        status = "timeout"
        error = "工具执行超时"
    except Exception as exc:
        result = None
        status = "error"
        error = str(exc)

    payload = {
        "name": name,
        "status": status,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "result": _jsonable(result),
        "error": error,
    }

    def _log():
        from apps.core.models import EventLog

        EventLog.log(
            "tool.invoke",
            actor="tools",
            level="info" if status == "ok" else "error",
            detail={**payload, "args": args},
        )

    await sync_to_async(_log, thread_sensitive=True)()
    return json_ok(payload, request=request)


def settings_timeout() -> int:
    from django.conf import settings

    return settings.MCP_DEFAULT_TIMEOUT
