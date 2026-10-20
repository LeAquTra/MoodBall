"""MoodBall URL 路由。"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from apps.core.views import home

urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.chat.urls")),
    path("api/", include("apps.vision.urls")),
    path("api/", include("apps.providers.urls")),
    path("api/", include("apps.mcp.urls")),
    path("api/", include("apps.voice.urls")),
    # Vite 产物使用绝对路径 /assets 与 /vendor；本地单用户直接用 Django 提供。
    re_path(
        r"^assets/(?P<path>.*)$",
        serve,
        {"document_root": settings.WEB_DIST / "assets"},
        name="web-assets",
    ),
    re_path(
        r"^vendor/(?P<path>.*)$",
        serve,
        {"document_root": settings.WEB_DIST / "vendor"},
        name="web-vendor",
    ),
    # 本地图片 / 音频预览；个人模式，不额外做鉴权。
    re_path(
        r"^media/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
        name="media",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

