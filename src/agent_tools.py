"""Tools the agent can call.

Each factory takes the *state accessors* the tool needs (e.g. a callable
that returns the currently-loaded Draft) and returns a ``Tool`` the agent
can register. Keeping state out of the tool signature itself means tools
stay testable without spinning up a full REPL.

Preserve-child-voice lives in the tool *surface*: there is **no tool that
rewrites page text freely**. The only way page text ever changes is
``propose_typo_fix``, which requires a user y/n and rejects anything
beyond mechanical substring substitutions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from src.agent import Tool
from src.draft import Draft
from src.schema import VALID_LAYOUTS


_METADATA_FIELDS = {"title", "author", "cover_subtitle", "back_cover_text"}
# set_metadata preserves whitespace on these fields — they carry the
# child's own words (cover subtitle, back-cover blurb) and should not
# be silently mutated. Title / author are conventional metadata and
# can be trimmed.
_CHILD_VOICE_FIELDS = {"cover_subtitle", "back_cover_text"}
# "Typo" caps — anything beyond a short phrase is a story edit in disguise.
_MAX_TYPO_CHARS = 30
_MAX_TYPO_WORDS = 3
# How many characters of surrounding page text to show in the y/n prompt
# so the user sees what they're actually approving (not just a→b).
_TYPO_CONTEXT_CHARS = 25


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
        cover = "yes" if draft.cover_image is not None else "(unset — ask the user)"
        lines.append(f"Title: {title}")
        lines.append(f"Author: {author}")
        lines.append(f"Cover drawing set: {cover}")
        lines.append(f"{len(draft.pages)} pages:")
        for i, page in enumerate(draft.pages, start=1):
            marker = "drawing" if page.image is not None else "no drawing"
            text = page.text.strip().replace("\n", " ")
            lines.append(f"  Page {i} ({marker}, layout={page.layout}): {text}")
        return "\n".join(lines)

    return Tool(
        name="read_draft",
        description=(
            "Read the currently-loaded PDF draft. Returns the title, author, "
            "cover status, page count, and for each page whether it has a "
            "drawing, its layout, and the child's exact text. Call this at "
            "the start of a session to see what you're working with."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=handler,
    )


def propose_typo_fix_tool(
    get_draft: Callable[[], Draft | None],
    confirm: Callable[[str], bool],
) -> Tool:
    """Tool: offer a mechanical typo / OCR-misread fix on one page.

    Only a substring substitution is allowed — and the total edit is
    bounded to a short run of characters so the agent can't funnel a
    sentence-level rewrite through this tool. The user must say yes
    before anything is written to the draft.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return "No draft loaded. Ask the user to provide a PDF first."
        page_n = int(input_["page"])
        before = str(input_["before"])
        after = str(input_["after"])
        reason = str(input_.get("reason", ""))

        if page_n < 1 or page_n > len(draft.pages):
            return (
                f"Page {page_n} is out of range — the draft has "
                f"{len(draft.pages)} pages."
            )
        if not before:
            return (
                "Rejected: 'before' must not be empty. propose_typo_fix "
                "corrects an existing typo — it does NOT insert new text "
                "into the child's page. If you want to add something, ask "
                "the user to write it themselves."
            )
        if (
            len(before) > _MAX_TYPO_CHARS
            or len(after) > _MAX_TYPO_CHARS
            or len(before.split()) > _MAX_TYPO_WORDS
            or len(after.split()) > _MAX_TYPO_WORDS
        ):
            return (
                "Rejected: typo fixes must be small mechanical substitutions "
                f"(≤{_MAX_TYPO_CHARS} chars and ≤{_MAX_TYPO_WORDS} words per "
                "side). For anything larger, ask the user to approve the "
                "change in conversation — don't route story edits through "
                "propose_typo_fix."
            )

        page = draft.pages[page_n - 1]
        # Word-boundary match so 'cat' → 'dog' never rewrites 'scatter'.
        pattern = r"(?<!\w)" + re.escape(before) + r"(?!\w)"
        match = re.search(pattern, page.text)
        if match is None:
            return (
                f"Rejected: the word '{before}' does not appear on page "
                f"{page_n} as a whole word. Don't invent substitutions — "
                "propose a fix only when you can see the typo verbatim in "
                "the child's text."
            )

        # Surface surrounding context so the user knows what they're
        # approving, not just `a → b`.
        start = max(0, match.start() - _TYPO_CONTEXT_CHARS)
        end = min(len(page.text), match.end() + _TYPO_CONTEXT_CHARS)
        context = page.text[start:end].replace("\n", " ")
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(page.text) else ""
        prompt = (
            f"Page {page_n}: fix '{before}' → '{after}'"
            + (f" ({reason})" if reason else "")
            + f" in: {prefix}{context}{suffix}"
        )
        if not confirm(prompt):
            return (
                f"User declined. Keep page {page_n} exactly as the child wrote it."
            )

        page.text = (
            page.text[: match.start()] + after + page.text[match.end():]
        )
        return f"Applied on page {page_n}. New text: {page.text!r}"

    return Tool(
        name="propose_typo_fix",
        description=(
            "Propose a mechanical typo / OCR-misread fix on one page. Only "
            "substring substitutions (≤30 chars each side) are allowed. The "
            "user must confirm before the draft is changed. Do NOT use this "
            "to rewrite sentences or 'polish' the child's voice."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1},
                "before": {"type": "string"},
                "after": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["page", "before", "after", "reason"],
        },
        handler=handler,
    )


def set_metadata_tool(get_draft: Callable[[], Draft | None]) -> Tool:
    """Tool: set a top-level metadata field on the draft.

    Allowed fields: ``title``, ``author``, ``cover_subtitle``,
    ``back_cover_text``. Page text is **intentionally** not a valid field
    — use ``propose_typo_fix`` for that.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return "No draft loaded. Ask the user to provide a PDF first."
        field_ = str(input_["field"])
        raw_value = str(input_.get("value", ""))
        if field_ not in _METADATA_FIELDS:
            return (
                f"Invalid field '{field_}'. Allowed fields: "
                f"{sorted(_METADATA_FIELDS)}. Page text is NOT a metadata "
                "field — use propose_typo_fix for that."
            )
        # Preserve child-voice content verbatim; only clean up admin fields.
        value = raw_value if field_ in _CHILD_VOICE_FIELDS else raw_value.strip()
        setattr(draft, field_, value)
        return f"{field_} set to: {value!r}"

    return Tool(
        name="set_metadata",
        description=(
            "Set a top-level metadata field on the draft. Allowed fields: "
            "title, author, cover_subtitle, back_cover_text. Ask the user "
            "for the value first — this tool does NOT prompt. Page text "
            "cannot be changed through this tool."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": sorted(_METADATA_FIELDS),
                },
                "value": {"type": "string"},
            },
            "required": ["field", "value"],
        },
        handler=handler,
    )


def set_cover_tool(get_draft: Callable[[], Draft | None]) -> Tool:
    """Tool: use one of the page drawings as the cover image."""

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return "No draft loaded. Ask the user to provide a PDF first."
        page_n = int(input_["page"])
        if page_n < 1 or page_n > len(draft.pages):
            return (
                f"Page {page_n} is out of range — the draft has "
                f"{len(draft.pages)} pages."
            )
        page = draft.pages[page_n - 1]
        if page.image is None:
            return f"Page {page_n} has no drawing — can't use it as the cover."
        draft.cover_image = page.image
        return f"Cover set to page {page_n}'s drawing ({page.image})."

    return Tool(
        name="set_cover",
        description=(
            "Use one of the draft's page drawings as the book's cover image. "
            "The user should have already picked which page — this tool "
            "doesn't ask."
        ),
        input_schema={
            "type": "object",
            "properties": {"page": {"type": "integer", "minimum": 1}},
            "required": ["page"],
        },
        handler=handler,
    )


def choose_layout_tool(get_draft: Callable[[], Draft | None]) -> Tool:
    """Tool: set the per-page layout.

    Enforces the first rule of the select-page-layout skill: a page with
    no image must render as ``text-only``. Agent can pick among the four
    valid layouts for pages that do have an image.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return "No draft loaded. Ask the user to provide a PDF first."
        page_n = int(input_["page"])
        layout = str(input_["layout"])
        reason = str(input_.get("reason", ""))

        if layout not in VALID_LAYOUTS:
            return (
                f"Invalid layout '{layout}'. Valid layouts: "
                f"{sorted(VALID_LAYOUTS)}."
            )
        if page_n < 1 or page_n > len(draft.pages):
            return (
                f"Page {page_n} is out of range — the draft has "
                f"{len(draft.pages)} pages."
            )
        page = draft.pages[page_n - 1]
        if page.image is None and layout != "text-only":
            return (
                f"Page {page_n} has no drawing — it must be text-only. "
                "Can't apply image-* layouts to an imageless page."
            )
        page.layout = layout
        suffix = f" ({reason})" if reason else ""
        return f"Page {page_n} layout set to {layout}{suffix}."

    return Tool(
        name="choose_layout",
        description=(
            "Set the per-page layout. Valid: image-top, image-bottom, "
            "image-full, text-only. Pages without a drawing must be "
            "text-only. Include a short reason so the user sees why."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1},
                "layout": {"type": "string", "enum": sorted(VALID_LAYOUTS)},
                "reason": {"type": "string"},
            },
            "required": ["page", "layout", "reason"],
        },
        handler=handler,
    )
