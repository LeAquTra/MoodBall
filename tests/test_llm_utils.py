from __future__ import annotations

import pytest

from apps.providers.services import validate_base_url
from services.base import ProviderError
from services.llm import JsonReplyExtractor, parse_json_object
from services.secrets import mask_key


def test_base_url_schemes() -> None:
    assert validate_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert validate_base_url("https://api.deepseek.com/") == "https://api.deepseek.com"
    with pytest.raises(ProviderError):
        validate_base_url("file:///etc/passwd")
    with pytest.raises(ProviderError):
        validate_base_url("javascript:alert(1)")


def test_private_ip_is_allowed_in_personal_mode() -> None:
    assert validate_base_url("http://169.254.169.254") == "http://169.254.169.254"
    assert validate_base_url("http://192.168.1.10:9100") == "http://192.168.1.10:9100"


def test_mask_key() -> None:
    assert mask_key("") == ""
    assert mask_key("short") == "****"
    assert mask_key("sk-1234567890abcd") == "sk-****abcd"


def test_parse_json_object_from_markdown() -> None:
    data = parse_json_object('```json\n{"reply":"你好","emotionId":"10"}\n```')
    assert data == {"reply": "你好", "emotionId": "10"}
    assert parse_json_object("not json") is None


def test_streaming_json_reply_extractor() -> None:
    extractor = JsonReplyExtractor()
    chunks = ['{"reply": "你', '好，', '世界", "emotionId": "10"}']
    output = "".join(extractor.feed(chunk) for chunk in chunks)
    assert output == "你好，世界"
    data, reply = extractor.finalize()
    assert data is not None
    assert data["emotionId"] == "10"
    assert reply == "你好，世界"


def test_streaming_extractor_handles_escapes() -> None:
    extractor = JsonReplyExtractor()
    text = '{"reply":"第一行\\n第二行 \\"引号\\"","emotionId":"02"}'
    output = "".join(extractor.feed(text[index : index + 4]) for index in range(0, len(text), 4))
    assert "第一行\n第二行" in output
    assert '\\"' not in output
