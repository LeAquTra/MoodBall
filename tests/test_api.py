from __future__ import annotations

import json

import pytest
from django.test import override_settings


@pytest.mark.django_db
def test_health(client, monkeypatch, tmp_path):
    async def fake_asr():
        return {"ok": True, "model": "test"}

    monkeypatch.setattr("apps.core.views._asr_check", fake_asr)
    response = client.get("/api/health/")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["db"]["ok"] is True
    assert body["asr"]["ok"] is True


@pytest.mark.django_db
def test_emotions_endpoint(client):
    response = client.get("/api/emotions/")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 33
    assert body["items"][0]["id"] == "00"


@pytest.mark.django_db
def test_settings_patch(client):
    response = client.get("/api/settings/")
    assert response.status_code == 200
    original = response.json()["settings"]

    response = client.patch(
        "/api/settings/",
        data=json.dumps({"wake_word": "你好小球", "wake_confirm_hits": 3}),
        content_type="application/json",
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["wake_word"] == "你好小球"
    assert settings["wake_confirm_hits"] == 3

    response = client.patch(
        "/api/settings/",
        data=json.dumps({"wake_word": original["wake_word"]}),
        content_type="application/json",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_conversation_crud(client):
    response = client.post(
        "/api/conversations/",
        data=json.dumps({"title": "测试会话"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    conversation_id = response.json()["conversation"]["id"]

    response = client.get("/api/conversations/")
    assert response.status_code == 200
    assert any(item["id"] == conversation_id for item in response.json()["items"])

    response = client.get(f"/api/conversations/{conversation_id}/messages/")
    assert response.status_code == 200
    assert response.json()["items"] == []

    response = client.delete(f"/api/conversations/{conversation_id}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_chat_fallback_persists(client, tmp_path):
    checkpoint = tmp_path / "checkpoints.sqlite3"
    with override_settings(CHECKPOINT_DB=checkpoint):
        response = client.post(
            "/api/chat/",
            data=json.dumps({"text": "你好，小球", "speak": False}),
            content_type="application/json",
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["assistant"]["reply"]
    assert body["assistant"]["message_id"]

    conversation_id = body["conversation_id"]
    response = client.get(f"/api/conversations/{conversation_id}/messages/")
    assert response.status_code == 200
    messages = response.json()["items"]
    assert [item["role"] for item in messages] == ["user", "assistant"]


@pytest.mark.django_db
def test_provider_api_seed_and_patch(client):
    response = client.get("/api/providers/")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 4
    assert all("api_key" in item for item in items)

    chat = next(item for item in items if item["kind"] == "chat")
    assert chat["api_key"] == "" or "****" in chat["api_key"]

    response = client.patch(
        f"/api/providers/{chat['id']}/",
        data=json.dumps({"model": "deepseek-flash", "api_key": "sk-test-1234567890"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["provider"]["api_key"].endswith("7890")


@pytest.mark.django_db
def test_invalid_base_url_rejected(client):
    response = client.post(
        "/api/providers/",
        data=json.dumps(
            {
                "kind": "chat",
                "name": "坏 URL",
                "base_url": "file:///etc/passwd",
                "model": "x",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_BASE_URL"
