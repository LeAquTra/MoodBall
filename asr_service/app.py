"""本机 ASR 服务：FastAPI + WebSocket。

启动：
    uvicorn asr_service.app:app --host 127.0.0.1 --port 9100
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import time
import wave
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from . import protocol
from .engine import engine
from .vad import create_vad

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("moodball.asr")

SAMPLE_RATE = 16000
SAMPLE_BYTES = 2


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(engine.load)
    yield


app = FastAPI(title="MoodBall ASR", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return engine.health()


@app.get("/")
async def root():
    return {"ok": True, "service": "moodball-asr", **engine.health()}


@app.post("/asr/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """离线转写一段 WAV，便于没有麦克风时调试。自动转 mono / 16 kHz。"""
    data = await file.read()
    try:
        import numpy as np

        with wave.open(io.BytesIO(data), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
        if width != 2:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "ASR_BAD_AUDIO", "message": "只支持 16-bit PCM WAV"}},
            )
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        if rate != SAMPLE_RATE and audio.size:
            duration = audio.size / rate
            target = max(1, int(duration * SAMPLE_RATE))
            source = np.arange(audio.size, dtype=np.float32)
            target_index = np.linspace(0, audio.size - 1, target, dtype=np.float32)
            audio = np.interp(target_index, source, audio).astype(np.float32)
        text = await engine.transcribe_array(audio)
        return {"ok": True, "text": text}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "ASR_TRANSCRIBE_FAILED", "message": str(exc)}},
        )


@app.websocket("/asr/stream")
async def asr_stream(ws: WebSocket):
    await ws.accept()
    if not engine.loaded:
        await ws.send_text(json.dumps(protocol.error("ASR_NOT_READY", engine.error or "模型未加载", True)))
        await ws.close()
        return

    try:
        state = await engine.new_state()
    except Exception as exc:
        await ws.send_text(json.dumps(protocol.error("ASR_STATE_FAILED", str(exc), True)))
        await ws.close()
        return

    await ws.send_text(
        json.dumps(
            protocol.ready(
                engine="mock" if engine.mock else "qwen3-asr-0.6b",
                cuda=engine.cuda,
                streaming=engine.streaming,
                model=engine.model_path,
                backend=engine.backend_actual,
                device=engine.device_actual,
            ),
            ensure_ascii=False,
        )
    )

    chunk_ms = 200
    buffer = bytearray()
    last_text = ""
    muted = False
    vad = create_vad()
    speech_started_at: float | None = None
    started = time.monotonic()

    def chunk_bytes() -> int:
        return int(SAMPLE_RATE * chunk_ms / 1000) * SAMPLE_BYTES

    async def reset_state():
        nonlocal state, buffer, last_text, speech_started_at
        buffer = bytearray()
        last_text = ""
        speech_started_at = None
        if vad is not None:
            vad.reset()
        state = await engine.new_state()

    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("bytes"):
                if muted:
                    continue
                buffer.extend(message["bytes"])
                while len(buffer) >= chunk_bytes():
                    chunk = bytes(buffer[: chunk_bytes()])
                    del buffer[: chunk_bytes()]
                    text = await engine.feed(state, chunk)
                    if vad is not None:
                        for event in vad.push(chunk):
                            at_ms = int((time.monotonic() - started) * 1000)
                            if event == "speech_start" and speech_started_at is None:
                                speech_started_at = time.monotonic()
                                await ws.send_text(
                                    json.dumps({"type": "speech_start", "at_ms": at_ms})
                                )
                            elif event == "speech_end":
                                await ws.send_text(json.dumps({"type": "speech_end", "at_ms": at_ms}))
                                final_text = await engine.finish(state)
                                await ws.send_text(
                                    json.dumps(
                                        protocol.final(final_text, getattr(state, "language", None), "vad"),
                                        ensure_ascii=False,
                                    )
                                )
                                await reset_state()
                                break
                    if text and text != last_text:
                        last_text = text
                        await ws.send_text(
                            json.dumps(
                                protocol.partial(text, getattr(state, "language", None)),
                                ensure_ascii=False,
                            )
                        )
                continue

            payload = json.loads(message.get("text") or "{}")
            kind = payload.get("type")
            if kind == "finish":
                final_text = await engine.finish(state)
                await ws.send_text(
                    json.dumps(
                        protocol.final(final_text, getattr(state, "language", None), "finish"),
                        ensure_ascii=False,
                    )
                )
                await reset_state()
            elif kind == "mute":
                muted = bool(payload.get("value"))
            elif kind == "chunk_ms":
                chunk_ms = max(40, min(int(payload.get("chunk_ms", 200)), 1000))
            elif kind == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif kind == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("asr websocket failed")
        try:
            await ws.send_text(json.dumps(protocol.error("ASR_STREAM_FAILED", str(exc), True)))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
