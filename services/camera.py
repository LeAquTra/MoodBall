"""OpenCV 摄像头单例：抓帧、质量校验、MJPEG、空闲释放。"""

from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger("moodball.camera")

try:  # OpenCV 是可选依赖：没有装时健康检查降级，不影响文字对话
    import cv2
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]


class CameraError(Exception):
    def __init__(self, code: str, message: str = "摄像头不可用") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Snapshot:
    jpeg: bytes
    width: int
    height: int


class CameraService:
    def __init__(
        self,
        index: int | None = None,
        backend: str | None = None,
        width: int | None = None,
        height: int | None = None,
        idle_release: int | None = None,
    ) -> None:
        self.index = settings.CAMERA_INDEX if index is None else index
        self.backend = settings.CAMERA_BACKEND if backend is None else backend
        self.width = settings.CAMERA_WIDTH if width is None else width
        self.height = settings.CAMERA_HEIGHT if height is None else height
        self.idle_release = settings.CAMERA_IDLE_RELEASE_SECONDS if idle_release is None else idle_release
        self._cap = None
        self._lock = threading.RLock()
        self._snap_lock = threading.Lock()
        self._last_used = 0.0
        self._last_error = ""
        self._opened_at = 0.0
        self._stop_event = threading.Event()
        self._idle_thread = threading.Thread(
            target=self._idle_loop, name="moodball-camera-idle", daemon=True
        )
        self._idle_thread.start()

    def _idle_loop(self) -> None:
        while not self._stop_event.wait(5.0):
            try:
                self.maybe_release_idle()
            except Exception:  # pragma: no cover
                logger.debug("camera idle check failed", exc_info=True)

    # -- 内部 ---------------------------------------------------------------
    def _backend_id(self) -> int | None:
        if cv2 is None:
            return None
        preferred = getattr(cv2, f"CAP_{self.backend.upper()}", None)
        if sys.platform.startswith("win"):
            return preferred or cv2.CAP_DSHOW
        return None

    def _open_locked(self) -> None:
        if cv2 is None:
            raise CameraError("CAMERA_OPENCV_MISSING", "没有安装 opencv-python，无法抓帧。")
        if self._cap is not None and self._cap.isOpened():
            return

        attempts: list[int | None] = [self._backend_id()]
        if sys.platform.startswith("win") and self._backend_id() != cv2.CAP_MSMF:
            attempts.append(cv2.CAP_MSMF)
        last_error = ""
        for backend in attempts:
            try:
                cap = (
                    cv2.VideoCapture(self.index, backend)
                    if backend is not None
                    else cv2.VideoCapture(self.index)
                )
                if cap is not None and cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception:
                        pass
                    # 预热：前几帧常常是黑的或曝光未稳定
                    for _ in range(max(0, settings.CAMERA_WARMUP_FRAMES)):
                        cap.read()
                    self._cap = cap
                    self._opened_at = time.time()
                    self._last_error = ""
                    logger.info("camera opened: index=%s backend=%s", self.index, backend)
                    return
                if cap is not None:
                    cap.release()
            except Exception as exc:  # pragma: no cover - 驱动差异
                last_error = str(exc)
        self._last_error = last_error or "无法打开摄像头（可能被占用或权限被拒）"
        raise CameraError("CAMERA_OPEN_FAILED", self._last_error)

    def _release_locked(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
            logger.info("camera released")

    def _read_frame_locked(self):
        self._open_locked()
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._last_error = "读取摄像头帧失败"
            self._release_locked()
            raise CameraError("CAMERA_READ_FAILED", "读取摄像头帧失败，请检查是否被其它程序占用。")
        self._last_used = time.time()
        return frame

    def _validate(self, frame) -> None:
        if cv2 is None:
            return
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if brightness < settings.CAMERA_MIN_BRIGHTNESS:
            raise CameraError("CAMERA_TOO_DARK", "画面太暗，请补光后再试。")
        if sharpness < settings.CAMERA_MIN_SHARPNESS:
            raise CameraError("CAMERA_BLURRY", "画面太模糊，请对准物体后再试。")

    def _encode(self, frame, quality: int, max_edge: int) -> tuple[bytes, int, int]:
        if cv2 is None:  # pragma: no cover
            raise CameraError("CAMERA_OPENCV_MISSING")
        height, width = frame.shape[:2]
        scale = min(1.0, max_edge / max(height, width))
        if scale < 1.0:
            frame = cv2.resize(
                frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA
            )
        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise CameraError("CAMERA_ENCODE_FAILED", "图片编码失败。")
        height, width = frame.shape[:2]
        return buffer.tobytes(), width, height

    # -- 公开 API -----------------------------------------------------------
    def snapshot(
        self,
        quality: int | None = None,
        max_edge: int | None = None,
        validate: bool = True,
    ) -> Snapshot:
        if not settings.CAMERA_ENABLED:
            raise CameraError("CAMERA_DISABLED", "摄像头已在配置中关闭。")
        if not self._snap_lock.acquire(timeout=2.0):
            raise CameraError("CAMERA_BUSY", "摄像头正忙，请稍后再试。")
        try:
            with self._lock:
                frame = self._read_frame_locked()
                if validate:
                    self._validate(frame)
                jpeg, width, height = self._encode(
                    frame,
                    quality if quality is not None else settings.CAMERA_QUALITY,
                    max_edge if max_edge is not None else settings.CAMERA_MAX_EDGE,
                )
                return Snapshot(jpeg=jpeg, width=width, height=height)
        finally:
            self._snap_lock.release()

    def mjpeg_frames(self, quality: int | None = None):
        while True:
            try:
                snapshot = self.snapshot(quality=quality, validate=False)
            except CameraError as exc:
                if exc.code == "CAMERA_BUSY":
                    time.sleep(0.12)
                    continue
                logger.info("camera preview stopped: %s", exc.code)
                return
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(snapshot.jpeg)).encode("ascii")
                + b"\r\n\r\n"
                + snapshot.jpeg
                + b"\r\n"
            )
            time.sleep(0.08)

    def release(self) -> None:
        with self._lock:
            self._release_locked()

    def maybe_release_idle(self) -> bool:
        with self._lock:
            if self._cap is not None and time.time() - self._last_used > self.idle_release:
                self._release_locked()
                return True
        return False

    def status(self) -> dict:
        with self._lock:
            opened = bool(self._cap is not None and self._cap.isOpened())
            width = height = 0
            if opened and cv2 is not None:
                width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            return {
                "enabled": settings.CAMERA_ENABLED,
                "opencv": cv2 is not None,
                "opened": opened,
                "index": self.index,
                "backend": self.backend,
                "width": width,
                "height": height,
                "last_used": self._last_used,
                "last_error": self._last_error,
            }


_camera: CameraService | None = None
_camera_lock = threading.Lock()


def get_camera() -> CameraService:
    global _camera
    with _camera_lock:
        if _camera is None:
            _camera = CameraService()
        return _camera


def reset_camera() -> CameraService:
    global _camera
    with _camera_lock:
        if _camera is not None:
            _camera.release()
        _camera = CameraService()
        return _camera
