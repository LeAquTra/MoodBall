"""LangGraph AgentState。"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    conversation_id: str
    user_message_id: str | None
    user_text: str
    image_ref: str | None
    with_vision: bool
    vision: dict | None
    memory: list[dict]
    pinned_memory: list[dict]
    history: list[dict]
    summary: str
    intent: Literal["chat", "vision", "tool", "memory", "direct"]
    available_tools: list[dict]
    selected_tools: list[str]
    tool_events: list[dict]
    emotion: str
    emotion_source: str
    intensity: float
    tips: str
    reply: str
    error: str | None
    speak: bool
    run_id: str
    assistant_message_id: str | None
    steps: int
    usage: dict
    timings: dict
