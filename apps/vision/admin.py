from django.contrib import admin

from .models import ImageAsset


@admin.register(ImageAsset)
class ImageAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "width", "height", "bytes", "created_at")
    list_filter = ("created_at",)
    search_fields = ("sha256",)
