"""唤醒词归一化、正则匹配、二次确认与冷却。

不依赖独立 KWS：ASR 的 partial / final 文本就是输入。
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from django.conf import settings

DEFAULT_WAKE_CHARS = "弟滴迪低底地第丁d的"


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value, flags=re.UNICODE)


@dataclass
class WakeHit:
    start: int
    end: int
    heard: str
    remainder: str


@dataclass
class WakeEvent:
    heard: str
    remainder: str
    text: str
    final: bool


class WakeMatcher:
    def __init__(
        self,
        wake_word: str | None = None,
        variants: list[str] | None = None,
        chars: str | None = None,
        confirm_hits: int | None = None,
        confirm_window_ms: int | None = None,
        cooldown_ms: int | None = None,
    ) -> None:
        self.wake_word = wake_word or settings.WAKE_WORD
        self.variants = list(variants if variants is not None else settings.WAKE_VARIANTS)
        self.chars = chars or settings.WAKE_CHARS or DEFAULT_WAKE_CHARS
        self.confirm_hits = max(1, confirm_hits or settings.WAKE_CONFIRM_HITS)
        self.confirm_window_ms = confirm_window_ms or settings.WAKE_CONFIRM_WINDOW_MS
        self.cooldown_ms = cooldown_ms if cooldown_ms is not None else settings.WAKE_COOLDOWN_MS

        patterns: list[str] = []
        if self.chars:
            char_class = "[" + re.escape(self.chars) + "]"
            patterns.append(f"小{char_class}小{char_class}")
        for variant in self.variants:
            normalized = normalize(variant)
            if normalized:
                patterns.append(re.escape(normalized))
        # 去重并保持顺序
        self._patterns = [re.compile(pattern, re.IGNORECASE) for pattern in dict.fromkeys(patterns)]

        self._hits = 0
        self._first_hit_at = 0.0
        self._last_wake_at = 0.0
        self._last_text = ""

    # -- 纯匹配 -------------------------------------------------------------
    def detect(self, text: str, final: bool = False) -> WakeHit | None:
        value = normalize(text)
        if not value:
            return None
        tail_start = 0 if final else max(0, len(value) - 16)
        best: re.Match | None = None
        for pattern in self._patterns:
            for match in pattern.finditer(value):
                if final or match.end() > tail_start:
                    if best is None or match.end() > best.end():
                        best = match
        if best is None:
            return None
        return WakeHit(
            start=best.start(),
            end=best.end(),
            heard=value[best.start() : best.end()],
            remainder=value[best.end() :],
        )

    # -- 带状态机的匹配 -----------------------------------------------------
    def feed(self, text: str, final: bool = False, now: float | None = None) -> WakeEvent | None:
        """partial 命中需要 confirm_hits 次确认；final 命中直接触发。"""
        now = time.monotonic() if now is None else now
        self._last_text = text

        if now - self._last_wake_at < self.cooldown_ms / 1000.0:
            return None

        hit = self.detect(text, final=final)
        if hit is None:
            # 文本里已经没有唤醒词，重置未确认计数
            if not final and not self.detect(text, final=True):
                self._hits = 0
            return None

        if final or self.confirm_hits <= 1:
            return self._trigger(hit, text, final, now)

        if self._hits == 0 or now - self._first_hit_at > self.confirm_window_ms / 1000.0:
            self._hits = 1
            self._first_hit_at = now
            return None

        self._hits += 1
        if self._hits >= self.confirm_hits:
            return self._trigger(hit, text, final, now)
        return None

    def _trigger(self, hit: WakeHit, text: str, final: bool, now: float) -> WakeEvent:
        self._hits = 0
        self._first_hit_at = 0.0
        self._last_wake_at = now
        return WakeEvent(heard=hit.heard, remainder=hit.remainder, text=normalize(text), final=final)

    def reset(self) -> None:
        self._hits = 0
        self._first_hit_at = 0.0
        self._last_wake_at = 0.0

    def reset_confirmation(self) -> None:
        """只清空未确认命中，保留冷却时间。"""
        self._hits = 0
        self._first_hit_at = 0.0


def strip_wake_prefix(text: str, matcher: WakeMatcher | None = None, final: bool = True) -> str:
    matcher = matcher or WakeMatcher()
    hit = matcher.detect(text, final=final)
    if hit is None:
        return normalize(text)
    return hit.remainder
