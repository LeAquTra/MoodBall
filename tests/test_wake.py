from __future__ import annotations

import pytest

from services.wake import WakeMatcher, normalize, strip_wake_prefix


@pytest.fixture()
def matcher() -> WakeMatcher:
    return WakeMatcher(
        wake_word="小d小d",
        variants=["你好小d", "嗨小d", "你好小滴", "你好小弟"],
        chars="弟滴迪低底地第丁d的",
        confirm_hits=2,
        confirm_window_ms=1200,
        cooldown_ms=1500,
    )


@pytest.mark.parametrize(
    "text,wake,remainder",
    [
        ("小弟 小弟", True, ""),
        ("小滴 小滴", True, ""),
        ("小迪 小迪", True, ""),
        ("小丁 小的", True, ""),
        ("小d小d", True, ""),
        ("你好 小d", True, ""),
        ("今天天气不错", False, ""),
        ("小d", False, ""),
        ("小弟 小弟 切换 主题", True, "切换主题"),
        ("小 弟 小 弟", True, ""),
    ],
)
def test_wake_detection(matcher: WakeMatcher, text: str, wake: bool, remainder: str) -> None:
    hit = matcher.detect(text, final=True)
    assert (hit is not None) is wake
    if hit is not None:
        assert hit.remainder == remainder


def test_normalize_strips_punctuation_and_spaces() -> None:
    assert normalize("小 弟，小 弟！") == "小弟小弟"
    assert normalize("小D小D") == "小d小d"


def test_partial_needs_two_confirmations(matcher: WakeMatcher) -> None:
    now = 100.0
    assert matcher.feed("小弟 小弟", final=False, now=now) is None
    event = matcher.feed("小弟 小弟 看看", final=False, now=now + 0.3)
    assert event is not None
    assert event.heard == "小弟小弟"
    assert event.remainder == "看看"


def test_final_wakes_immediately(matcher: WakeMatcher) -> None:
    event = matcher.feed("小弟 小弟", final=True, now=10.0)
    assert event is not None
    assert event.final is True


def test_cooldown_suppresses_repeat(matcher: WakeMatcher) -> None:
    now = 10.0
    assert matcher.feed("小弟 小弟", final=True, now=now) is not None
    assert matcher.feed("小弟 小弟", final=True, now=now + 0.2) is None
    assert matcher.feed("小弟 小弟", final=True, now=now + 2.0) is not None


def test_partial_wake_requires_tail_window(matcher: WakeMatcher) -> None:
    hit = matcher.detect("小弟小弟" + "很长的一段话" * 10, final=False)
    assert hit is None
    hit = matcher.detect("很长的一段话" * 10 + "小弟小弟", final=False)
    assert hit is not None


def test_strip_wake_prefix(matcher: WakeMatcher) -> None:
    assert strip_wake_prefix("小弟 小弟 打开 设置", matcher=matcher) == "打开设置"
    assert strip_wake_prefix("打开 设置", matcher=matcher) == "打开设置"
