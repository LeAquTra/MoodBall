from django.contrib import admin

from .models import ProviderProfile


@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    list_display = ("kind", "name", "model", "base_url", "enabled", "is_default")
    list_filter = ("kind", "enabled", "is_default")
    search_fields = ("name", "model", "base_url")
