from django.contrib import admin

from .models import AgentRun, ToolCall


class ToolCallInline(admin.TabularInline):
    model = ToolCall
    extra = 0
    fields = ("name", "source", "status", "duration_ms", "created_at")
    readonly_fields = ("created_at",)


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "status", "intent", "emotion_id", "latency_ms", "created_at")
    list_filter = ("status", "intent")
    search_fields = ("user_text", "reply")
    inlines = [ToolCallInline]


@admin.register(ToolCall)
class ToolCallAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "status", "duration_ms", "created_at")
    list_filter = ("source", "status")
    search_fields = ("name", "server_name")
