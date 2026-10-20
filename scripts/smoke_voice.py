"""向 MoodBall 的 /ws/voice/ 回放一段 WAV，检查唤醒 / partial / final。

用法（先启动 Django 和 ASR 服务）：
    python scripts/smoke_voice.py .\test_zh.wav
    python scripts/smoke_voice.py .\test_zh.wav --ws ws://127.0.0.1:8000/ws/voice/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import wave
from pathlib import Path

import numpy as np
import websockets

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = int(SAMPLE_RATE * FRAME_MS / 1000) * 2


def load_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise SystemExit("只支持 16-bit PCM WAV")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and audio.size:
        target = max(1, int(audio.size / rate * SAMPLE_RATE))
        source = np.arange(audio.size, dtype=np.float32)
        index = np.linspace(0, audio.size - 1, target, dtype=np.float32)
        audio = np.interp(index, source, audio).astype(np.float32)
    return (audio * 32767.0).astype(np.int16).tobytes()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument("--ws", default="ws://127.0.0.1:8000/ws/voice/")
    parser.add_argument("--wake-word", default="小d小d")
    args = parser.parse_args()

    pcm = load_wav(args.wav)
    print(f"audio: {len(pcm) / (SAMPLE_RATE * 2):.2f}s, {args.ws}")

    async with websockets.connect(args.ws, max_size=4 * 1024 * 1024) as ws:
        print("hello:", await asyncio.wait_for(ws.recv(), 5))
        await ws.send(
            json.dumps(
                {"type": "start", "wake_word": args.wake_word, "mode": "continuous"},
                ensure_ascii=False,
            )
        )

        async def reader() -> None:
            while True:
                try:
                    raw = await ws.recv()
                except Exception:
                    return
                if isinstance(raw, str):
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind in {"ready", "phase", "partial", "wake", "final", "error", "asr_status"}:
                        print(kind, json.dumps(event, ensure_ascii=False))

        reader_task = asyncio.create_task(reader())
        # 等 ready / armed
        await asyncio.sleep(1.5)
        for index in range(0, len(pcm), FRAME_BYTES):
            await ws.send(pcm[index : index + FRAME_BYTES])
            await asyncio.sleep(FRAME_MS / 1000)
        # 尾部静音，让 VAD 收句
        silence = b"\x00\x00" * int(SAMPLE_RATE * FRAME_MS / 1000)
        for _ in range(60):
            await ws.send(silence)
            await asyncio.sleep(FRAME_MS / 1000)
        await asyncio.sleep(8)
        reader_task.cancel()
        await ws.send(json.dumps({"type": "stop"}))


if __name__ == "__main__":
    asyncio.run(main())
