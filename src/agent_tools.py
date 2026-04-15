"""Tools the agent can call.

Each factory takes the *state accessors* the tool needs (e.g. a callable
that returns the currently-loaded Draft) and returns a ``Tool`` the agent
can register. Keeping state out of the tool signature itself means tools
stay testable without spinning up a full REPL.

Preserve-child-voice lives in the tool *surface*: this module only adds
read-only or user-approved tools. No tool here rewrites page text.
"""

from __future__ import annotations

from typing import Callable

from src.agent import Tool
from src.draft import Draft


def read_draft_tool(get_draft: Callable[[], Draft | None]) -> Tool:
    """Tool: summarise the loaded PDF draft for the agent.

    Read-only. Returns the child's text verbatim so the agent can see
    exactly what was written, including typos and invented words — the
    agent decides what to flag for the user.
    """

    def handler(_input: dict) -> str:
        draft = get_draft()
        if draft is None:
            return "No draft is loaded. Ask the user to provide a PDF."
        lines: list[str] = []
        title = draft.title.strip() or "(unset — ask the user)"
        author = draft.author.strip() or "(unset — ask the user)"
        lines.append(f"Title: {title}")
        lines.append(f"Author: {author}")
        lines.append(f"{len(draft.pages)} pages:")
        for i, page in enumerate(draft.pages, start=1):
            marker = "drawing" if page.image is not None else "no drawing"
            text = page.text.strip().replace("\n", " ")
            lines.append(f"  Page {i} ({marker}): {text}")
        return "\n".join(lines)

    return Tool(
        name="read_draft",
        description=(
            "Read the currently-loaded PDF draft. Returns the title, author, "
            "page count, and for each page whether it has a drawing and the "
            "child's exact text. Call this at the start of a session to see "
            "what you're working with."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=handler,
    )
