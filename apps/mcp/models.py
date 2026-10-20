"""MCP server 配置与工具缓存。"""

from __future__ import annotations

import uuid

from django.db import models


class McpServer(models.Model):
    class Transport(models.TextChoices):
        STDIO = "stdio", "stdio"
        HTTP = "http", "http"
        SSE = "sse", "sse"
        STREAMABLE_HTTP = "streamable_http", "streamable_http"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True)
    transport = models.CharField(max_length=20, choices=Transport.choices, default=Transport.STDIO)
    command = models.CharField(max_length=300, blank=True)
    args_json = models.JSONField(default=list, blank=True)
    env_json = models.JSONField(default=dict, blank=True)
    url = models.URLField(max_length=500, blank=True)
    headers_json = models.JSONField(default=dict, blank=True)
    tool_prefix = models.CharField(max_length=40, blank=True)
    enabled = models.BooleanField(default=True)
    auto_start = models.BooleanField(default=True)
    timeout_s = models.IntegerField(default=30)
    last_error = models.TextField(blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def as_dict(self, with_tools: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": self.args_json or [],
            "env": self.env_json or {},
            "url": self.url,
            "headers": self.headers_json or {},
            "tool_prefix": self.tool_prefix,
            "enabled": self.enabled,
            "auto_start": self.auto_start,
            "timeout_s": self.timeout_s,
            "last_error": self.last_error,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "tool_count": getattr(self, "tool_count", None),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if with_tools:
            data["tools"] = [tool.as_dict() for tool in self.tools.all()]
        return data


class McpTool(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server = models.ForeignKey(McpServer, on_delete=models.CASCADE, related_name="tools")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    input_schema = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["server__name", "name"]
        constraints = [models.UniqueConstraint(fields=["server", "name"], name="uniq_mcp_tool")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.server.name}:{self.name}"

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "server": self.server.name,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema or {},
            "enabled": self.enabled,
            "last_seen_at": self.last_seen_at.isoformat(),
        }
