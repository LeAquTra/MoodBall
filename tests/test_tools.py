from __future__ import annotations

import pytest

from agent.registry import registry


@pytest.mark.django_db
async def test_registry_contains_builtins_and_plugin() -> None:
    await registry.refresh([])
    names = {entry.name for entry in registry.list()}
    assert {"capture_photo", "recall_memory", "remember_fact", "forget_memory", "set_emotion", "get_time"} <= names
    assert "get_disk_free" in names


@pytest.mark.django_db
async def test_search_returns_time_tool() -> None:
    await registry.refresh([])
    picked = registry.search("现在几点了 时间", k=5)
    assert picked
    assert picked[0].name == "get_time"


@pytest.mark.django_db
async def test_search_ignores_disabled_mcp() -> None:
    await registry.refresh([])
    assert all(entry.enabled for entry in registry.search("工具", k=50))


def test_mcp_namespace_helper() -> None:
    from agent.mcp_client import resolve_command

    resolved = resolve_command("python")
    assert resolved
    assert "python" in resolved.lower()
