from django.contrib import admin

from .models import AppSetting, EventLog


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "updated_at")
    search_fields = ("key",)


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "level", "created_at")
    list_filter = ("level", "actor")
    search_fields = ("action",)
    date_hierarchy = "created_at"
