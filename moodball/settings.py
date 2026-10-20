"""Django settings for MoodBall.

所有可调参数都来自 `.env`（见 `.env.example`）；这里只定义读取规则和默认值。
个人本机模式：不启用登录 / CSRF 校验 / 权限体系，API 视图统一 csrf_exempt。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# `.env` 只作为本地默认值；已存在的环境变量优先。
load_dotenv(BASE_DIR / ".env", override=False)


def env_str(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return default if value is None else value.strip()


def env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def env_int(key: str, default: int) -> int:
    try:
        return int(env_str(key, str(default)))
    except (TypeError, ValueError):
        return default


def env_float(key: str, default: float) -> float:
    try:
        return float(env_str(key, str(default)))
    except (TypeError, ValueError):
        return default


def env_list(key: str, default: str = "") -> list[str]:
    raw = env_str(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_path(key: str, default: str) -> Path:
    raw = Path(env_str(key, default)).expanduser()
    return raw if raw.is_absolute() else (BASE_DIR / raw).resolve()


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "django-insecure-moodball-local-only")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173",
)

PERSONAL_MODE = env_bool("PERSONAL_MODE", True)
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# 应用
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "channels",
    "apps.core",
    "apps.chat",
    "apps.vision",
    "apps.providers",
    "apps.mcp",
    "apps.agent",
    "apps.voice",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "moodball.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "moodball.wsgi.application"
ASGI_APPLICATION = "moodball.asgi.application"

# ---------------------------------------------------------------------------
# 数据库：业务库与 LangGraph 检查点分库
# ---------------------------------------------------------------------------
SQLITE_PATH = env_path("SQLITE_PATH", "./db.sqlite3")
CHECKPOINT_DB = env_path("CHECKPOINT_DB", "./agent_checkpoints.sqlite3")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
        "OPTIONS": {"timeout": 20},
        "CONN_MAX_AGE": 0,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# 国际化 / 静态 / 媒体
# ---------------------------------------------------------------------------
LANGUAGE_CODE = env_str("LANGUAGE_CODE", "zh-hans")
TIME_ZONE = env_str("TIME_ZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

WEB_DIST = env_path("WEB_DIST", "./web/dist")
STATICFILES_DIRS = [WEB_DIST] if WEB_DIST.exists() else []
if (BASE_DIR / "static").exists():
    STATICFILES_DIRS.append(BASE_DIR / "static")

MEDIA_ROOT = env_path("MEDIA_ROOT", "./media")
MEDIA_URL = env_str("MEDIA_URL", "/media/")

DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 12 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE
MAX_IMAGE_BYTES = env_int("MAX_IMAGE_BYTES", 2 * 1024 * 1024)

# ---------------------------------------------------------------------------
# Channels（单进程 MVP 用内存层）
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}

# ---------------------------------------------------------------------------
# DRF：个人本机模式，无需认证 / 权限
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.drf_exception_handler",
}

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = False

# ---------------------------------------------------------------------------
# 能力配置（全部来自 .env）
# ---------------------------------------------------------------------------
ASR_ENABLED = env_bool("ASR_ENABLED", True)
ASR_BASE_URL = env_str("ASR_BASE_URL", "http://127.0.0.1:9100").rstrip("/")
ASR_WS_URL = env_str("ASR_WS_URL", "ws://127.0.0.1:9100/asr/stream")
ASR_MODEL_PATH = env_str("ASR_MODEL_PATH", "./models/Qwen3-ASR-0.6B")
ASR_BACKEND = env_str("ASR_BACKEND", "auto").lower()
ASR_DEVICE = env_str("ASR_DEVICE", "auto")
ASR_DTYPE = env_str("ASR_DTYPE", "bfloat16").lower()
ASR_STREAMING = env_bool("ASR_STREAMING", True)
ASR_LANGUAGE = env_str("ASR_LANGUAGE", "Chinese")
ASR_MAX_NEW_TOKENS = env_int("ASR_MAX_NEW_TOKENS", 256)
ASR_MAX_INFERENCE_BATCH_SIZE = env_int("ASR_MAX_INFERENCE_BATCH_SIZE", 1)
ASR_PARTIAL_INTERVAL_MS = env_int("ASR_PARTIAL_INTERVAL_MS", 900)
ASR_MAX_UTTERANCE_SECONDS = env_int("ASR_MAX_UTTERANCE_SECONDS", 15)
ASR_CHUNK_MS = env_int("ASR_CHUNK_MS", 200)
ASR_CONNECT_TIMEOUT = env_float("ASR_CONNECT_TIMEOUT", 5.0)
ASR_RECONNECT_DELAY_MS = env_int("ASR_RECONNECT_DELAY_MS", 1000)
ASR_GPU_MEMORY_UTILIZATION = env_float("ASR_GPU_MEMORY_UTILIZATION", 0.7)

ZHIPU_BASE_URL = env_str("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
ZHIPU_API_KEY = env_str("ZHIPU_API_KEY", "")
ZHIPU_VISION_MODEL = env_str("ZHIPU_VISION_MODEL", "glm-4.6v-flash")
ZHIPU_TIMEOUT = env_float("ZHIPU_TIMEOUT", 25.0)

DEEPSEEK_BASE_URL = env_str("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_API_KEY = env_str("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = env_str("DEEPSEEK_MODEL", "deepseek-flash")
DEEPSEEK_TIMEOUT = env_float("DEEPSEEK_TIMEOUT", 60.0)

TTS_ENABLED = env_bool("TTS_ENABLED", True)
DASHSCOPE_BASE_URL = env_str("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
DASHSCOPE_API_KEY = env_str("DASHSCOPE_API_KEY", "")
DASHSCOPE_WORKSPACE_ID = env_str("DASHSCOPE_WORKSPACE_ID", "")
DASHSCOPE_WORKSPACE_BASE_URL = env_str(
    "DASHSCOPE_WORKSPACE_BASE_URL",
    (
        f"https://{DASHSCOPE_WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/api/v1"
        if DASHSCOPE_WORKSPACE_ID
        else ""
    ),
).rstrip("/")
TTS_MODEL = env_str("TTS_MODEL", "qwen3-tts-flash")
TTS_VOICE = env_str("TTS_VOICE", "Cherry")
TTS_FORMAT = env_str("TTS_FORMAT", "wav")
TTS_SAMPLE_RATE = env_int("TTS_SAMPLE_RATE", 24000)
TTS_PROTOCOL = env_str("TTS_PROTOCOL", "dashscope-mm")
TTS_TIMEOUT = env_float("TTS_TIMEOUT", 30.0)
TTS_MAX_CHARS = env_int("TTS_MAX_CHARS", 600)
TTS_CACHE_MAX_ITEMS = env_int("TTS_CACHE_MAX_ITEMS", 200)

CAMERA_ENABLED = env_bool("CAMERA_ENABLED", True)
CAMERA_INDEX = env_int("CAMERA_INDEX", 0)
CAMERA_BACKEND = env_str("CAMERA_BACKEND", "dshow")
CAMERA_WIDTH = env_int("CAMERA_WIDTH", 1280)
CAMERA_HEIGHT = env_int("CAMERA_HEIGHT", 720)
CAMERA_QUALITY = env_int("CAMERA_QUALITY", 82)
CAMERA_MAX_EDGE = env_int("CAMERA_MAX_EDGE", 1280)
CAMERA_WARMUP_FRAMES = env_int("CAMERA_WARMUP_FRAMES", 5)
CAMERA_IDLE_RELEASE_SECONDS = env_int("CAMERA_IDLE_RELEASE_SECONDS", 60)
CAMERA_MIN_BRIGHTNESS = env_float("CAMERA_MIN_BRIGHTNESS", 20.0)
CAMERA_MIN_SHARPNESS = env_float("CAMERA_MIN_SHARPNESS", 10.0)

WAKE_WORD = env_str("WAKE_WORD", "小d小d")
WAKE_VARIANTS = env_list("WAKE_VARIANTS", "你好小d,嗨小d,你好小滴,你好小弟")
WAKE_CHARS = env_str("WAKE_CHARS", "弟滴迪低底地第丁d的")
WAKE_CONFIRM_HITS = max(1, env_int("WAKE_CONFIRM_HITS", 2))
WAKE_CONFIRM_WINDOW_MS = env_int("WAKE_CONFIRM_WINDOW_MS", 1200)
WAKE_COOLDOWN_MS = env_int("WAKE_COOLDOWN_MS", 1500)
COMMAND_TIMEOUT_MS = env_int("COMMAND_TIMEOUT_MS", 8000)
WAKE_UTTERANCE_TIMEOUT_MS = env_int("WAKE_UTTERANCE_TIMEOUT_MS", 5000)
TTS_COOLDOWN_MS = env_int("TTS_COOLDOWN_MS", 300)
VOICE_IDLE_TIMEOUT_MS = env_int("VOICE_IDLE_TIMEOUT_MS", 30000)

AGENT_ENABLED = env_bool("AGENT_ENABLED", True)
AGENT_RECENT_MESSAGES = env_int("AGENT_RECENT_MESSAGES", 20)
AGENT_SUMMARY_AFTER = env_int("AGENT_SUMMARY_AFTER", 20)
AGENT_TEMPERATURE = env_float("AGENT_TEMPERATURE", 0.7)
AGENT_MAX_STEPS = env_int("AGENT_MAX_STEPS", 4)
AGENT_EMOTION_MIN_HOLD_MS = env_int("AGENT_EMOTION_MIN_HOLD_MS", 900)
AGENT_DEFAULT_EMOTION = env_str("AGENT_DEFAULT_EMOTION", "02")

# 长期记忆（MemoryFact）：召回、自动提取与容量上限
MEMORY_ENABLED = env_bool("MEMORY_ENABLED", True)
# 自动提取默认关闭：开启后每轮对话都会额外调用一次对话模型，可在设置页或 .env 打开
MEMORY_AUTO_EXTRACT = env_bool("MEMORY_AUTO_EXTRACT", False)
MEMORY_MAX_ITEMS = env_int("MEMORY_MAX_ITEMS", 500)
MEMORY_RECALL_LIMIT = env_int("MEMORY_RECALL_LIMIT", 5)
MEMORY_PINNED_LIMIT = env_int("MEMORY_PINNED_LIMIT", 5)
MEMORY_EXTRACT_TIMEOUT = env_float("MEMORY_EXTRACT_TIMEOUT", 25.0)
MEMORY_DEDUPE_RATIO = env_float("MEMORY_DEDUPE_RATIO", 0.9)

MCP_ENABLED = env_bool("MCP_ENABLED", True)
MCP_CONFIG_PATH = env_path("MCP_CONFIG_PATH", "./mcp_servers.json")
MCP_MAX_TOOLS_PER_TURN = env_int("MCP_MAX_TOOLS_PER_TURN", 16)
MCP_DEFAULT_TIMEOUT = env_int("MCP_DEFAULT_TIMEOUT", 30)
MCP_TOOL_TTL_SECONDS = env_int("MCP_TOOL_TTL_SECONDS", 60)
MCP_MAX_RESULT_CHARS = env_int("MCP_MAX_RESULT_CHARS", 8000)

IMAGE_RETENTION_DAYS = env_int("IMAGE_RETENTION_DAYS", 7)
VISION_RETENTION_DAYS = env_int("VISION_RETENTION_DAYS", 30)
AUDIO_RETENTION_DAYS = env_int("AUDIO_RETENTION_DAYS", 7)
EVENT_LOG_RETENTION_DAYS = env_int("EVENT_LOG_RETENTION_DAYS", 30)

# Provider 的 .env 种子（数据库没有配置时使用，不落库）
PROVIDER_DEFAULTS = {
    "chat": {
        "name": "DeepSeek",
        "base_url": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL,
        "api_key": DEEPSEEK_API_KEY,
        "extra": {"timeout": DEEPSEEK_TIMEOUT, "temperature": AGENT_TEMPERATURE},
    },
    "vision": {
        "name": "智谱视觉",
        "base_url": ZHIPU_BASE_URL,
        "model": ZHIPU_VISION_MODEL,
        "api_key": ZHIPU_API_KEY,
        "extra": {"timeout": ZHIPU_TIMEOUT},
    },
    "tts": {
        "name": "百炼 CosyVoice",
        "base_url": DASHSCOPE_BASE_URL,
        "model": TTS_MODEL,
        "api_key": DASHSCOPE_API_KEY,
        "extra": {
            "timeout": TTS_TIMEOUT,
            "voice": TTS_VOICE,
            "format": TTS_FORMAT,
            "sample_rate": TTS_SAMPLE_RATE,
            "protocol": TTS_PROTOCOL,
            "workspace_id": DASHSCOPE_WORKSPACE_ID,
            "workspace_base_url": DASHSCOPE_WORKSPACE_BASE_URL,
        },
    },
    "asr": {
        "name": "本机 Qwen3-ASR",
        "base_url": ASR_BASE_URL,
        "model": ASR_MODEL_PATH,
        "api_key": "",
        "extra": {
            "streaming": ASR_STREAMING,
            "device": ASR_DEVICE,
            "backend": ASR_BACKEND,
            "dtype": ASR_DTYPE,
            "language": ASR_LANGUAGE,
        },
    },
}

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": LOG_LEVEL,
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.channels": {"level": "INFO", "propagate": True},
        "httpx": {"level": "WARNING", "propagate": True},
        "httpcore": {"level": "WARNING", "propagate": True},
        "moodball": {"level": LOG_LEVEL, "propagate": True},
    },
}

# 个人本机不校验 Origin；需要局域网访问时再改成显式白名单。
ALLOWED_HOSTS = ALLOWED_HOSTS or ["127.0.0.1", "localhost"]
if DEBUG and "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")
