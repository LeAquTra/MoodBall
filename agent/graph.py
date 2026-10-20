"""LangGraph 图组装。"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from .nodes import (
    analyze_vision,
    capture_vision,
    compose,
    execute_tool,
    fallback_reply,
    load_context,
    load_tools,
    persist,
    plan_emotion,
    recall_memory,
    route,
    select_tools,
    tools_condition,
)
from .state import AgentState


def _route_decision(state: AgentState) -> str:
    intent = state.get("intent") or "chat"
    if intent == "vision":
        return "vision"
    if intent == "memory":
        return "memory"
    return "direct"


def _vision_next(state: AgentState) -> str:
    return "fallback" if state.get("error") else "tools"


def _build_builder() -> StateGraph:
    builder = StateGraph(AgentState)
    for name, fn in {
        "load_context": load_context,
        "load_tools": load_tools,
        "route": route,
        "capture_vision": capture_vision,
        "analyze_vision": analyze_vision,
        "recall_memory": recall_memory,
        "select_tools": select_tools,
        "compose": compose,
        "execute_tool": execute_tool,
        "plan_emotion": plan_emotion,
        "persist": persist,
        "fallback_reply": fallback_reply,
    }.items():
        builder.add_node(name, fn)

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "load_tools")
    builder.add_edge("load_tools", "route")
    builder.add_conditional_edges(
        "route",
        _route_decision,
        {"vision": "capture_vision", "memory": "recall_memory", "direct": "select_tools"},
    )
    builder.add_edge("capture_vision", "analyze_vision")
    builder.add_conditional_edges(
        "analyze_vision",
        _vision_next,
        {"fallback": "fallback_reply", "tools": "select_tools"},
    )
    builder.add_edge("recall_memory", "select_tools")
    builder.add_edge("select_tools", "compose")
    builder.add_conditional_edges(
        "compose",
        tools_condition,
        {"tools": "execute_tool", "end": "plan_emotion"},
    )
    builder.add_edge("execute_tool", "compose")
    builder.add_edge("fallback_reply", "plan_emotion")
    builder.add_edge("plan_emotion", "persist")
    builder.add_edge("persist", END)
    return builder


@lru_cache(maxsize=1)
def _builder() -> StateGraph:
    return _build_builder()


def build_graph(checkpointer=None):
    return _builder().compile(checkpointer=checkpointer)
