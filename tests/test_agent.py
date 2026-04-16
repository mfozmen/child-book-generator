"""Agent loop unit tests.

The Agent drives a tool-use conversation with an LLM. These tests use a
scriptable fake LLM so the loop's behaviour is pinned without a network.
"""

import io

from rich.console import Console

from src.agent import Agent, AgentResponse, Tool


class _ScriptedLLM:
    """Returns a queued list of AgentResponses in order.

    Tests script what the LLM 'would say' and then assert on the
    resulting tool calls / conversation.
    """

    def __init__(self, responses: list[AgentResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []  # (messages, tool_names) each call

    def turn(self, messages, tools):
        self.calls.append(
            {"messages": list(messages), "tool_names": [t.name for t in tools]}
        )
        if not self._responses:
            raise AssertionError("scripted LLM ran out of responses")
        return self._responses.pop(0)


def _text(*chunks: str) -> AgentResponse:
    return AgentResponse(
        content=[{"type": "text", "text": t} for t in chunks],
        stop_reason="end_turn",
    )


def _tool_call(tool_id: str, name: str, input_: dict) -> AgentResponse:
    return AgentResponse(
        content=[{"type": "tool_use", "id": tool_id, "name": name, "input": input_}],
        stop_reason="tool_use",
    )


def _make_agent(llm, tools=None):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    return Agent(llm=llm, tools=tools or [], console=console), buf


def test_agent_say_prints_plain_text_response():
    llm = _ScriptedLLM([_text("hello there")])
    agent, buf = _make_agent(llm)

    agent.say("hi")

    assert "hello there" in buf.getvalue()
    assert len(llm.calls) == 1


def test_agent_loops_on_tool_use_until_text_response():
    def handler(_input):
        return "42"

    tool = Tool(
        name="answer",
        description="Returns the answer",
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )
    llm = _ScriptedLLM(
        [
            _tool_call("call-1", "answer", {}),
            _text("the answer is 42"),
        ]
    )
    agent, buf = _make_agent(llm, tools=[tool])

    agent.say("what's the answer?")

    assert "the answer is 42" in buf.getvalue()
    # Two LLM round-trips: one asked for the tool, one replied after the result.
    assert len(llm.calls) == 2
    # Second call's messages include the tool_use and the tool_result.
    second = llm.calls[1]["messages"]
    # tool_use block present in assistant turn
    assistant_blocks = [m for m in second if m["role"] == "assistant"]
    assert any(
        b.get("type") == "tool_use"
        for m in assistant_blocks
        for b in (m["content"] if isinstance(m["content"], list) else [])
    )
    # tool_result present in user turn
    user_blocks = [m for m in second if m["role"] == "user"]
    assert any(
        isinstance(m["content"], list)
        and any(b.get("type") == "tool_result" for b in m["content"])
        for m in user_blocks
    )


def test_agent_captures_tool_result_text_verbatim():
    def handler(input_):
        return f"echoed: {input_['msg']}"

    tool = Tool(
        name="echo",
        description="Echo back the input",
        input_schema={
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        },
        handler=handler,
    )
    llm = _ScriptedLLM(
        [
            _tool_call("c1", "echo", {"msg": "preserve this verbatim"}),
            _text("done"),
        ]
    )
    agent, _ = _make_agent(llm, tools=[tool])

    agent.say("echo something")

    # The tool result block carries the exact string the handler returned,
    # with no reformatting / rewriting by the agent layer.
    second = llm.calls[1]["messages"]
    for msg in second:
        if msg["role"] == "user" and isinstance(msg["content"], list):
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    assert block["content"] == "echoed: preserve this verbatim"
                    return
    raise AssertionError("tool_result block not found")


def test_unknown_tool_name_reports_error_without_crashing():
    llm = _ScriptedLLM(
        [
            _tool_call("c1", "does_not_exist", {}),
            _text("sorry"),
        ]
    )
    agent, _ = _make_agent(llm)

    # Must not raise — the agent should inject an error tool_result and
    # let the LLM recover.
    agent.say("hi")

    second = llm.calls[1]["messages"]
    for msg in second:
        if msg["role"] == "user" and isinstance(msg["content"], list):
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    assert "error" in block["content"].lower()
                    return
    raise AssertionError("error tool_result block not found")


def test_tool_handler_exception_becomes_error_tool_result():
    def boom(_input):
        raise RuntimeError("disk full")

    tool = Tool(
        name="boom",
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=boom,
    )
    llm = _ScriptedLLM(
        [
            _tool_call("c1", "boom", {}),
            _text("recovered"),
        ]
    )
    agent, _ = _make_agent(llm, tools=[tool])

    agent.say("try it")

    # The exception text surfaces in the tool_result so the LLM can react.
    second = llm.calls[1]["messages"]
    for msg in second:
        if msg["role"] == "user" and isinstance(msg["content"], list):
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    assert "disk full" in block["content"]
                    return
    raise AssertionError("error tool_result block not found")


def test_agent_remembers_previous_turns():
    llm = _ScriptedLLM([_text("one"), _text("two")])
    agent, _ = _make_agent(llm)

    agent.say("first")
    agent.say("second")

    # Second call's messages include the first user turn and assistant reply.
    second_call = llm.calls[1]["messages"]
    contents = [m for m in second_call]
    assert contents[0] == {"role": "user", "content": "first"}
    # Assistant reply from first turn is preserved.
    assert contents[1]["role"] == "assistant"


def test_assistant_response_with_text_and_tool_use_mixed():
    """Claude can emit text *and* a tool_use in the same response
    ("let me check..." → call tool). Both must be handled: the text
    block prints, the tool_use fires, and non-tool_use blocks are
    skipped when building tool_results."""
    results = []

    def handler(_input):
        results.append("ran")
        return "ok"

    tool = Tool(
        name="collect",
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )
    mixed = AgentResponse(
        content=[
            {"type": "text", "text": "let me check"},
            {"type": "tool_use", "id": "a", "name": "collect", "input": {}},
        ],
        stop_reason="tool_use",
    )
    llm = _ScriptedLLM([mixed, _text("done")])
    agent, buf = _make_agent(llm, tools=[tool])

    agent.say("do it")

    assert results == ["ran"]
    assert "let me check" in buf.getvalue()


def test_multiple_tool_calls_in_one_turn_all_executed():
    """Some LLM responses contain several tool_use blocks at once."""
    results = []

    def handler(input_):
        results.append(input_["x"])
        return "ok"

    tool = Tool(
        name="collect",
        description="",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        },
        handler=handler,
    )
    multi = AgentResponse(
        content=[
            {"type": "tool_use", "id": "a", "name": "collect", "input": {"x": "one"}},
            {"type": "tool_use", "id": "b", "name": "collect", "input": {"x": "two"}},
        ],
        stop_reason="tool_use",
    )
    llm = _ScriptedLLM([multi, _text("done")])
    agent, _ = _make_agent(llm, tools=[tool])

    agent.say("do both")

    assert results == ["one", "two"]
