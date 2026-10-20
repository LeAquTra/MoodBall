"""MoodBall ASGI 入口：HTTP 交给 Django，WebSocket 交给 Channels。"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moodball.settings")

from django.conf import settings
from django.core.asgi import get_asgi_application

# 必须先初始化 Django，再导入依赖 app registry 的模块。
django_asgi = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from apps.voice.routing import websocket_urlpatterns as voice_ws  # noqa: E402

http_application = django_asgi
if settings.DEBUG:
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

    http_application = ASGIStaticFilesHandler(django_asgi)

# 个人本机模式：不启用登录 / Origin 校验。
application = ProtocolTypeRouter(
    {
        "http": http_application,
        "websocket": URLRouter(voice_ws),
    }
)
