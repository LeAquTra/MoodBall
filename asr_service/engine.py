"""Qwen3-ASR 引擎封装。

Windows / 小显存默认走 transformers 后端（VAD 分段 + 离线识别，部分文本靠定时重转写）；
Linux + vLLM 可切换到真正的流式后端。没有模型/依赖时服务仍能启动，
/health 返回 loaded=false，WebSocket 返回可读错误，前端自动降级到 PTT。
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - ASR venv 可选装
    load_dotenv = None  # type: ignore[assignment]

logger = logging.getLogger("moodball.asr.engine")

ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(ROOT / ".env", override=False)

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]

SAMPLE_RATE = 16000


@dataclass
class MockState:
    text: str = ""
    language: str = "Chinese"
    fed_bytes: int = 0
    started_at: float = field(default_factory=time.monotonic)


@dataclass
class BufferedState:
    audio: object = None
    text: str = ""
    language: str | None = None
    fed_bytes: int = 0
    last_partial_bytes: int = 0
    started_at: float = field(default_factory=time.monotonic)


class ASREngine:
    def __init__(self) -> None:
        raw_path = os.getenv("ASR_MODEL_PATH", "./models/Qwen3-ASR-0.6B")
        model_path = Path(raw_path).expanduser()
        self.model_path = str(model_path if model_path.is_absolute() else (ROOT / model_path).resolve())
        self.backend = os.getenv("ASR_BACKEND", "auto").strip().lower()
        self.backend_actual = self.backend
        self.device = os.getenv("ASR_DEVICE", "auto").strip().lower()
        self.device_actual = self.device
        self.dtype = os.getenv("ASR_DTYPE", "bfloat16").strip().lower()
        self.streaming = os.getenv("ASR_STREAMING", "0") not in {"0", "false", "False"}
        self.language = os.getenv("ASR_LANGUAGE", "Chinese").strip() or None
        self.max_new_tokens = int(os.getenv("ASR_MAX_NEW_TOKENS", "256"))
        self.max_batch = int(os.getenv("ASR_MAX_INFERENCE_BATCH_SIZE", "1"))
        self.partial_interval_ms = int(os.getenv("ASR_PARTIAL_INTERVAL_MS", "900"))
        self.max_utterance_seconds = int(os.getenv("ASR_MAX_UTTERANCE_SECONDS", "15"))
        self.gpu_memory_utilization = float(os.getenv("ASR_GPU_MEMORY_UTILIZATION", "0.55"))
        self.mock = os.getenv("ASR_MOCK", "0") in {"1", "true", "True"}
        self.mock_text = os.getenv("ASR_MOCK_TEXT", "小d小d 看看 我 桌上 是 什么")

        self.model = None
        self.loaded = False
        self.cuda = False
        self.error = ""
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    def load(self) -> None:
        if self.mock:
            self.loaded = True
            self.cuda = False
            self.backend_actual = "mock"
            logger.info("ASR running in mock mode")
            return
        if np is None:
            self.error = "numpy 未安装"
            logger.error(self.error)
            return
        try:
            import torch
        except Exception as exc:
            self.error = f"torch 未安装或不可用：{exc}"
            logger.exception(self.error)
            return

        if not Path(self.model_path).exists():
            self.error = f"ASR 模型目录不存在：{self.model_path}"
            logger.error(self.error)
            return

        self.cuda = bool(torch.cuda.is_available()) and not self.device.startswith("cpu")
        if self.device in {"auto", ""}:
            self.device_actual = "cuda:0" if self.cuda else "cpu"
        elif self.cuda:
            self.device_actual = self.device
        else:
            self.device_actual = "cpu"
            self.cuda = False

        backend = self.backend
        if backend == "auto":
            backend = "vllm" if self._vllm_available() else "transformers"
        if backend == "vllm" and platform.system().lower() == "windows":
            logger.warning("vLLM 后端在原生 Windows 上通常不可用，回退 transformers")
            backend = "transformers"

        if backend == "vllm":
            try:
                self._load_vllm()
                self.backend_actual = "vllm"
            except Exception as exc:
                logger.exception("vLLM 加载失败，尝试 transformers：%s", exc)
                backend = "transformers"
        if backend == "transformers":
            self._load_transformers(torch)

    def _vllm_available(self) -> bool:
        try:
            import vllm  # noqa: F401

            return True
        except Exception:
            return False

    def _load_vllm(self) -> None:
        from qwen_asr import Qwen3ASRModel

        self.model = Qwen3ASRModel.LLM(
            model=self.model_path,
            gpu_memory_utilization=self.gpu_memory_utilization,
            max_inference_batch_size=self.max_batch,
            max_new_tokens=max(32, self.max_new_tokens),
        )
        self.loaded = True
        self.error = ""
        self.streaming = True
        logger.info("ASR vLLM loaded: %s (cuda=%s)", self.model_path, self.cuda)

    def _load_transformers(self, torch) -> None:
        from qwen_asr import Qwen3ASRModel

        dtype = getattr(torch, self.dtype, None)
        if dtype is None or not self.cuda:
            dtype = torch.float32 if not self.cuda else torch.bfloat16
        device_map = self.device_actual if self.cuda else "cpu"

        attempts = []
        if self.cuda:
            attempts.append((device_map, dtype, True))
            attempts.append(("cpu", torch.float32, False))
        else:
            attempts.append(("cpu", torch.float32, False))

        last_exc: Exception | None = None
        for target, target_dtype, cuda in attempts:
            try:
                self.model = Qwen3ASRModel.from_pretrained(
                    self.model_path,
                    dtype=target_dtype,
                    device_map=target,
                    max_inference_batch_size=max(1, self.max_batch),
                    max_new_tokens=max(32, self.max_new_tokens),
                )
                self.loaded = True
                self.cuda = cuda
                self.device_actual = target
                self.backend_actual = "transformers"
                self.streaming = False
                self.error = ""
                logger.info(
                    "ASR transformers loaded: %s (device=%s dtype=%s)",
                    self.model_path,
                    target,
                    target_dtype,
                )
                return
            except Exception as exc:
                last_exc = exc
                logger.exception("ASR transformers load failed on %s", target)
                self.model = None
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

        self.error = f"ASR 模型加载失败：{last_exc}"
        logger.error(self.error)

    # ------------------------------------------------------------------
    # 健康 / 状态
    # ------------------------------------------------------------------
    def health(self) -> dict:
        return {
            "ok": self.loaded and not self.error,
            "engine": "mock" if self.mock else "qwen3-asr",
            "backend": self.backend_actual,
            "model": self.model_path,
            "loaded": self.loaded,
            "cuda": self.cuda,
            "device": self.device_actual,
            "dtype": self.dtype,
            "streaming": self.streaming,
            "language": self.language,
            "error": self.error,
        }

    # ------------------------------------------------------------------
    # 转写
    # ------------------------------------------------------------------
    def _normalize_result(self, result) -> str:
        if result is None:
            return ""
        if isinstance(result, list):
            if not result:
                return ""
            result = result[0]
        if isinstance(result, str):
            return result.strip()
        if isinstance(result, dict):
            return str(result.get("text", "")).strip()
        text = getattr(result, "text", None)
        if isinstance(text, str):
            return text.strip()
        if isinstance(result, tuple) and len(result) >= 2 and isinstance(result[-1], str):
            return result[-1].strip()
        return str(result).strip()

    def _transcribe_sync(self, audio) -> str:
        audio = np.asarray(audio, dtype=np.float32)
        results = self.model.transcribe(
            audio=(audio, SAMPLE_RATE),
            language=self.language,
        )
        return self._normalize_result(results)

    async def transcribe_array(self, audio) -> str:
        if self.mock:
            return self.mock_text
        if not self.loaded or self.model is None:
            raise RuntimeError(self.error or "ASR 模型未加载")
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_sync, audio)

    # ------------------------------------------------------------------
    # 会话状态
    # ------------------------------------------------------------------
    async def new_state(self):
        if self.mock:
            return MockState()
        if not self.loaded or self.model is None:
            raise RuntimeError(self.error or "ASR 模型未加载")
        if self.backend_actual == "vllm" and hasattr(self.model, "init_streaming_state"):
            return self.model.init_streaming_state(
                unfixed_chunk_num=2,
                unfixed_token_num=5,
                chunk_size_sec=0.8,
            )
        if np is None:
            raise RuntimeError("numpy 未安装")
        return BufferedState(audio=np.zeros(0, dtype=np.float32))

    async def feed(self, state, pcm16: bytes) -> str:
        if self.mock:
            state.fed_bytes += len(pcm16)
            if state.fed_bytes >= 3200 * 2:
                state.text = self.mock_text.split()[0] if self.mock_text.split() else "小d小d"
            if state.fed_bytes >= 3200 * 2 * 2:
                state.text = self.mock_text
            return state.text
        if np is None:
            raise RuntimeError("numpy 未安装")
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0

        if isinstance(state, BufferedState):
            async with self._lock:
                await asyncio.to_thread(self._feed_buffered, state, audio)
            return state.text

        if hasattr(state, "text"):
            async with self._lock:
                await asyncio.to_thread(self.model.streaming_transcribe, audio, state)
                return state.text
        return ""

    def _feed_buffered(self, state: BufferedState, audio) -> None:
        if state.audio is None:
            state.audio = np.zeros(0, dtype=np.float32)
        state.audio = np.concatenate([state.audio, audio])[-SAMPLE_RATE * self.max_utterance_seconds :]
        state.fed_bytes += int(audio.size)
        if self.partial_interval_ms <= 0:
            return
        threshold = int(SAMPLE_RATE * self.partial_interval_ms / 1000)
        if state.audio.size - state.last_partial_bytes < threshold:
            return
        state.last_partial_bytes = state.audio.size
        try:
            state.text = self._transcribe_sync(state.audio)
        except Exception:
            logger.warning("partial transcribe failed", exc_info=True)

    async def finish(self, state) -> str:
        if self.mock:
            return state.text
        if isinstance(state, BufferedState):
            async with self._lock:
                if state.audio is not None and state.audio.size:
                    try:
                        state.text = await asyncio.to_thread(self._transcribe_sync, state.audio)
                    except Exception:
                        logger.warning("final transcribe failed", exc_info=True)
                return state.text
        if hasattr(state, "text") and hasattr(self.model, "finish_streaming_transcribe"):
            async with self._lock:
                await asyncio.to_thread(self.model.finish_streaming_transcribe, state)
                return state.text
        if isinstance(state, dict) and state.get("audio") is not None and len(state["audio"]):
            async with self._lock:
                result = await asyncio.to_thread(self._transcribe_sync, state["audio"])
                state["text"] = result
                return result
        return state.get("text", "") if isinstance(state, dict) else ""


engine = ASREngine()
