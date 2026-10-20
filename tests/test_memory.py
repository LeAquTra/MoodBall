from __future__ import annotations

import json
import uuid

import pytest
from asgiref.sync import sync_to_async

from apps.chat import memory_service
from apps.chat.models import MemoryFact
from apps.core.models import AppSetting


def _create(client, fact: str, **extra):
    payload = {"fact": fact, **extra}
    response = client.post(
        "/api/memories/",
        data=json.dumps(payload, ensure_ascii=False),
        content_type="application/json",
    )
    assert response.status_code in {200, 201}, response.content
    return response.json()


@pytest.mark.django_db
def test_memory_crud_and_search(client):
    created = _create(client, "我喜欢喝冰美式", tags="咖啡,偏好", pinned=True)
    item = created["memory"]
    assert created["created"] is True
    assert item["pinned"] is True
    assert item["source"] == "manual"
    assert "咖啡" in item["tag_list"]

    listing = client.get("/api/memories/").json()
    assert listing["total"] == 1
    assert listing["stats"]["total"] == 1
    assert listing["settings"]["enabled"] is True
    assert listing["tags"][0]["tag"] in {"咖啡", "偏好"}

    filtered = client.get("/api/memories/?q=咖啡").json()
    assert filtered["total"] == 1
    assert client.get("/api/memories/?tag=偏好").json()["total"] == 1
    assert client.get("/api/memories/?sort=used").json()["items"]

    memory_id = item["id"]
    response = client.patch(
        f"/api/memories/{memory_id}/",
        data=json.dumps({"fact": "我喜欢喝热美式", "pinned": False, "tags": ["咖啡"]}, ensure_ascii=False),
        content_type="application/json",
    )
    assert response.status_code == 200
    updated = response.json()["memory"]
    assert updated["fact"] == "我喜欢喝热美式"
    assert updated["pinned"] is False
    assert updated["tags"] == "咖啡"

    response = client.delete(f"/api/memories/{memory_id}/")
    assert response.status_code == 200
    assert client.get("/api/memories/").json()["total"] == 0


@pytest.mark.django_db
def test_memory_deduplicates_similar_facts(client):
    first = _create(client, "用户住在杭州", tags="城市")
    second = _create(client, "用户住在杭州。", tags="常住")
    assert second["created"] is False
    assert second["memory"]["id"] == first["memory"]["id"]
    assert MemoryFact.objects.count() == 1
    assert "常住" in second["memory"]["tags"]


@pytest.mark.django_db
def test_memory_bulk_delete_and_clear(client):
    ids = [
        _create(client, f"记忆条目 {index}", tags="批处理")["memory"]["id"]
        for index in range(3)
    ]
    pinned = _create(client, "置顶记忆", pinned=True)["memory"]["id"]

    response = client.post(
        "/api/memories/bulk-delete/",
        data=json.dumps({"ids": ids[:2]}),
        content_type="application/json",
    )
    assert response.json()["deleted"] == 2
    assert MemoryFact.objects.count() == 2

    response = client.post(
        "/api/memories/clear/",
        data=json.dumps({"keep_pinned": True}),
        content_type="application/json",
    )
    assert response.json()["deleted"] == 1
    assert MemoryFact.objects.count() == 1
    assert MemoryFact.objects.get().id == uuid.UUID(pinned)

    response = client.post(
        "/api/memories/clear/",
        data=json.dumps({"keep_pinned": False}),
        content_type="application/json",
    )
    assert response.json()["deleted"] == 1
    assert MemoryFact.objects.count() == 0


@pytest.mark.django_db
def test_memory_recall_marks_usage(client):
    _create(client, "用户喜欢下雨天散步", tags="天气,习惯")
    _create(client, "用户的猫叫团子", tags="宠物,猫")

    recalled = memory_service.recall("猫")
    assert recalled
    assert recalled[0]["fact"] == "用户的猫叫团子"
    row = MemoryFact.objects.get(pk=recalled[0]["id"])
    assert row.use_count == 1
    assert row.last_used_at is not None

    stats = memory_service.memory_stats()
    assert stats["used"] == 1
    assert stats["used_7d"] == 1


@pytest.mark.django_db
def test_memory_recall_strips_question_phrases(client):
    _create(client, "我每天早上喝一杯冰美式", tags="偏好,咖啡")
    _create(client, "我的猫叫团子，是一只橘猫", tags="宠物,猫")

    recalled = memory_service.recall("你还记得我每天早上喝什么吗？")
    assert recalled
    assert recalled[0]["fact"] == "我每天早上喝一杯冰美式"

    assert memory_service.forget_matching("忘掉猫") == 1
    assert MemoryFact.objects.count() == 1


@pytest.mark.django_db
def test_memory_forget_tool_matching(client):
    _create(client, "用户对花生过敏", tags="健康")
    _create(client, "用户喜欢猫", tags="宠物")

    assert memory_service.forget_matching("花生") == 1
    assert MemoryFact.objects.count() == 1
    assert memory_service.forget_matching("") == 0


@pytest.mark.django_db
async def test_auto_extract_is_opt_in_and_deduped(monkeypatch):
    async def fake_extract(user_text: str, reply: str) -> list[str]:
        return ["用户喜欢猫", "用户喜欢猫"]

    monkeypatch.setattr(memory_service, "extract_facts", fake_extract)
    await AppSetting.objects.acreate(key="memory_enabled", value_json=True)
    await AppSetting.objects.acreate(key="memory_auto_extract", value_json=False)

    assert await memory_service.maybe_auto_extract(None, "我喜欢猫", "记住啦") == []
    assert await MemoryFact.objects.acount() == 0

    await AppSetting.objects.filter(key="memory_auto_extract").aupdate(value_json=True)
    created = await memory_service.maybe_auto_extract(None, "我喜欢猫", "记住啦")
    assert len(created) == 1
    assert created[0]["source"] == "auto"
    assert await MemoryFact.objects.acount() == 1

    await AppSetting.objects.filter(key="memory_enabled").aupdate(value_json=False)
    assert await sync_to_async(memory_service.is_enabled)() is False
    assert await memory_service.maybe_auto_extract(None, "我又来了一句话", "好的") == []


@pytest.mark.django_db
def test_memory_settings_patch(client):
    response = client.patch(
        "/api/settings/",
        data=json.dumps({"memory_auto_extract": True, "memory_max_items": 120}),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()["settings"]
    assert payload["memory_auto_extract"] is True
    assert payload["memory_max_items"] == 120

    listing = client.get("/api/memories/").json()
    assert listing["settings"]["auto_extract"] is True
    assert listing["settings"]["max_items"] == 120
