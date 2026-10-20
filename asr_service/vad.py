"""VAD：优先 Silero，缺失时退化为能量阈值。

ASR 服务用它判断 speech_start / speech_end；Django 只消费事件。
"""

from __future__ import annotations

import logging
import os

import numpy as np

logger = logging.getLogger("moodball.asr.vad")

SAMPLE_RATE = 16000


class EnergyVAD:
    def __init__(self, threshold: float = 0.012) -> None:
        self.threshold = float(os.getenv("ASR_VAD_THRESHOLD", threshold))
        self.speech_ms = 0
        self.silence_ms = 0
        self.in_speech = False

    def reset(self) -> None:
        self.speech_ms = 0
        self.silence_ms = 0
        self.in_speech = False

    def push(self, pcm16: bytes) -> list[str]:
        """返回本帧触发的事件：speech_start / speech_end。"""
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return []
        frame_ms = int(audio.size / SAMPLE_RATE * 1000)
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        events: list[str] = []
        if rms >= self.threshold:
            self.speech_ms += frame_ms
            self.silence_ms = 0
            if not self.in_speech and self.speech_ms >= int(os.getenv("ASR_VAD_MIN_SPEECH_MS", "250")):
                self.in_speech = True
                events.append("speech_start")
        else:
            self.silence_ms += frame_ms
            if self.in_speech and self.silence_ms >= int(os.getenv("ASR_VAD_MIN_SILENCE_MS", "700")):
                self.in_speech = False
                self.speech_ms = 0
                events.append("speech_end")
        return events


class SileroVAD:
    def __init__(self) -> None:
        self._model = None
        self._available = False
        self._fallback = EnergyVAD()
        try:
            from silero_vad import load_silero_vad

            self._model = load_silero_vad()
            self._available = True
            logger.info("Silero VAD loaded")
        except Exception:
            logger.info("Silero VAD unavailable, using energy VAD")

    def reset(self) -> None:
        if self._available and self._model is not None:
            try:
                self._model.reset_states()
            except Exception:
                pass
        self._fallback.reset()

    def push(self, pcm16: bytes) -> list[str]:
        if not self._available or self._model is None:
            return self._fallback.push(pcm16)
        try:
            import torch

            audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
            tensor = torch.from_numpy(audio)
            prob = float(self._model(tensor, SAMPLE_RATE).item())
            if prob >= 0.5:
                return ["speech_start"] if not getattr(self, "_in_speech", False) else []
            return ["speech_end"] if getattr(self, "_in_speech", False) else []
        except Exception:
            return self._fallback.push(pcm16)


def create_vad():
    if os.getenv("ASR_VAD", "1") in {"0", "false", "False"}:
        return None
    return SileroVAD()
