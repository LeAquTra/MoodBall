from django.contrib import admin

from .models import TTSAsset, VoiceSession


@admin.register(TTSAsset)
class TTSAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "voice", "model", "bytes", "duration_ms", "created_at")
    list_filter = ("voice", "model")
    search_fields = ("text",)


@admin.register(VoiceSession)
class VoiceSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "status", "wake_count", "final_count", "started_at")
    list_filter = ("status",)
