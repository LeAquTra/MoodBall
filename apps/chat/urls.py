from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("conversations/", views.conversations, name="conversations"),
    path("conversations/<uuid:conversation_id>/", views.conversation_detail, name="conversation"),
    path(
        "conversations/<uuid:conversation_id>/messages/",
        views.conversation_messages,
        name="messages",
    ),
    path(
        "conversations/<uuid:conversation_id>/events/",
        views.conversation_events,
        name="events",
    ),
    path(
        "conversations/<uuid:conversation_id>/export/",
        views.conversation_export,
        name="export",
    ),
    path("memories/", views.memories, name="memories"),
    path("memories/bulk-delete/", views.memories_bulk_delete, name="memories-bulk-delete"),
    path("memories/clear/", views.memories_clear, name="memories-clear"),
    path("memories/<uuid:memory_id>/", views.memory_detail, name="memory"),
    path("chat/stream/", views.chat_stream, name="chat-stream"),
    path("chat/", views.chat_once, name="chat"),
]
