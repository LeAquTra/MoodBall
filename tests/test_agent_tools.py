from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent.nodes import execute_tool, tools_condition
from agent.registry import registry
from apps.agent.models import AgentRun, ToolCall
from apps.chat.models import Conversation


@pytest.mark.django_db
async def test_execute_tool_writes_tool_message_and_record() -> None:
    conversation = await Conversation.objects.acreate(title="工具测试")
    run = await AgentRun.objects.acreate(
        conversation=conversation,
        thread_id=str(conversation.id),
        user_text="几点了",
    )
    await registry.refresh([])

    state = {
        "conversation_id": str(conversation.id),
        "run_id": str(run.id),
        "messages": [
            HumanMessage(content="几点了"),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_time", "args": {}, "id": "call_1", "type": "tool_call"}],
            ),
        ],
        "tool_events": [],
    }
    assert tools_condition(state) == "tools"
    result = await execute_tool(state)
    assert len(result["messages"]) == 1
    assert "20" in result["messages"][0].content
    assert result["tool_events"][0]["status"] == "ok"
    assert result["steps"] == 1

    record = await ToolCall.objects.filter(run=run).afirst()
    assert record is not None
    assert record.name == "get_time"
    assert record.status == "ok"


@pytest.mark.django_db
async def test_execute_unknown_tool_returns_error_message() -> None:
    conversation = await Conversation.objects.acreate(title="未知工具")
    run = await AgentRun.objects.acreate(
        conversation=conversation, thread_id=str(conversation.id), user_text="x"
    )
    await registry.refresh([])
    state = {
        "run_id": str(run.id),
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "not_a_tool", "args": {}, "id": "call_x", "type": "tool_call"}],
            )
        ],
        "tool_events": [],
    }
    result = await execute_tool(state)
    assert result["tool_events"][0]["status"] == "error"
    assert "TOOL_ERROR" in result["messages"][0].content
