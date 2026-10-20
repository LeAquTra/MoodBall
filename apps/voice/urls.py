from django.urls import path

from . import views

app_name = "voice"

urlpatterns = [
    path("tts/preview/", views.tts_preview, name="tts-preview"),
    path("audio/<uuid:audio_id>/", views.audio_detail, name="audio"),
    path("voice/sessions/", views.voice_sessions, name="sessions"),
    path("voice/status/", views.voice_status, name="status"),
]
