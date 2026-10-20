from django.urls import path

from . import views

app_name = "vision"

urlpatterns = [
    path("camera/snapshot/", views.snapshot, name="snapshot"),
    path("camera/preview/", views.preview, name="preview"),
    path("camera/release/", views.release, name="release"),
    path("camera/status/", views.camera_status, name="status"),
    path("vision/analyze/", views.analyze, name="analyze"),
    path("images/", views.images, name="images"),
    path("images/<uuid:image_id>/", views.image_detail, name="image"),
]
