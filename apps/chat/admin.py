from django.contrib import admin

from .models import Conversation, EmotionEvent, MemoryFact, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("role", "content", "emotion_id", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "updated_at", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "summary")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("role", "conversation", "emotion_id", "created_at")
    list_filter = ("role", "emotion_id")
    search_fields = ("content",)


@admin.register(EmotionEvent)
class EmotionEventAdmin(admin.ModelAdmin):
    list_display = ("emotion_id", "source", "conversation", "created_at")
    list_filter = ("source", "emotion_id")


@admin.register(MemoryFact)
class MemoryFactAdmin(admin.ModelAdmin):
    list_display = ("fact", "source", "pinned", "use_count", "confidence", "created_at")
    list_filter = ("source", "pinned")
    search_fields = ("fact", "tags")
