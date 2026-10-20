from django.urls import path, re_path

from . import views

app_name = "core"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("settings/", views.settings_view, name="settings"),
    path("emotions/", views.emotions, name="emotions"),
    path("meta/", views.index_meta, name="meta"),
    re_path(r"^media/(?P<path>.+)$", views.media_file, name="media-file"),
]
