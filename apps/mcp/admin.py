from django.contrib import admin

from .models import McpServer, McpTool


class McpToolInline(admin.TabularInline):
    model = McpTool
    extra = 0
    fields = ("name", "enabled", "last_seen_at")
    readonly_fields = ("last_seen_at",)


@admin.register(McpServer)
class McpServerAdmin(admin.ModelAdmin):
    list_display = ("name", "transport", "enabled", "auto_start", "last_seen_at")
    list_filter = ("transport", "enabled", "auto_start")
    search_fields = ("name", "command", "url")
    inlines = [McpToolInline]
