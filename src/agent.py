"""Agent loop — drive a tool-use conversation with an LLM.

The Agent is deliberately small. It owns:

- The conversation history (messages).
- A tool registry (name → handler).
- One method ``say(text)`` that advances the loop until the LLM stops
  requesting tools.

Tool results are fed back verbatim; preserve-child-voice is enforced at
the *tool surface* — the agent never has a tool that rewrites page text.
Typo/OCR fixes are proposed tools that must surface to the user.

Format follows Anthropic's tool-use wire shape (content blocks with
``type`` = ``text`` / ``tool_use`` / ``tool_result``). Other providers
translate in their adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rich.console import Console


@dataclass
class Tool:
    """A callable the agent can ask the LLM to invoke.

    ``input_schema`` is a JSON Schema object describing the ``input`` dict
    the handler receives. ``handler`` returns a plain-text result the
    agent forwards to the LLM untouched.
    """

    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], str]


@dataclass
class AgentResponse:
    """Shape returned by ``LLMProvider.turn``.

    ``content`` is a list of content blocks in Anthropic's format:
    ``{"type": "text", "text": ...}`` or
    ``{"type": "tool_use", "id": ..., "name": ..., "input": ...}``.
    """

    content: list[dict]
    stop_reason: str  # "end_turn" | "tool_use" (| others we don't handle yet)


class Agent:
    def __init__(
        self,
        llm,
        tools: list[Tool],
        console: Console,
    ) -> None:
        self._llm = llm
        self._tools: dict[str, Tool] = {t.name: t for t in tools}
        self._tool_list: list[Tool] = list(tools)
        self._console = console
        self._messages: list[dict] = []

    @property
    def messages(self) -> list[dict]:
        return self._messages

    def say(self, user_text: str) -> None:
        """Append a user message and drive the loop until the LLM stops."""
        self._messages.append({"role": "user", "content": user_text})
        self._drive()

    def _drive(self) -> None:
        while True:
            response = self._llm.turn(self._messages, self._tool_list)
            self._messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if block.get("type") == "text":
                    self._console.print(block["text"])
            if response.stop_reason != "tool_use":
                return
            tool_results: list[dict] = []
            for block in response.content:
                if block.get("type") != "tool_use":
                    continue
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": self._run_tool(block["name"], block.get("input", {})),
                    }
                )
            self._messages.append({"role": "user", "content": tool_results})

    def _run_tool(self, name: str, input_: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: no such tool: {name}"
        try:
            return tool.handler(input_)
        except Exception as e:
            return f"Error: {e}"
