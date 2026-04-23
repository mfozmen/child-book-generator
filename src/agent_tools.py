"""Tools the agent can call.

Each factory takes the *state accessors* the tool needs (e.g. a callable
that returns the currently-loaded Draft) and returns a ``Tool`` the agent
can register. Keeping state out of the tool signature itself means tools
stay testable without spinning up a full REPL.

**Preserve-child-voice is enforced by two invariants**, not by per-call
confirm gates:

1. **The input is immutable.** Nothing in this module deletes, rewrites,
   or renames the mirrored source PDF under ``.book-gen/input/`` or the
   per-page drawings ``pdf_ingest`` extracts to
   ``.book-gen/images/page-NN.*``. ``restore_page`` relies on them still
   being on disk.

2. **The child's words reach the printed page verbatim.** Every path
   that writes ``page.text`` either goes through a verbatim-only prompt
   (``transcribe_page`` asks the vision model for a byte-for-byte
   transcription, three-sentinel classifier; ``propose_typo_fix`` is
   bounded to 3 words / 30 chars per side so it can't funnel a rewrite)
   or copies a user-supplied string with NO model in between
   (``apply_text_correction``).

Per-mutation y/n confirm callbacks are gone. The tools that used to
carry them auto-apply; the user audits the finished PDF in the
post-render review turn and corrects any mistake via
``apply_text_correction`` / ``restore_page`` / ``hide_page``.

Tool groups:

- **Content tools, auto-apply (no confirm):** ``propose_typo_fix``,
  ``transcribe_page``, ``propose_layouts``, ``hide_page``.
- **Presentation / read-only (no confirm):** ``read_draft``,
  ``set_metadata``, ``set_cover``, ``choose_layout``, ``render_book``.
- **Cost-gated (single pricing confirm, not content):**
  ``generate_cover_illustration``, ``generate_page_illustration``.
- **Review-turn only (user-initiated, no confirm):**
  ``apply_text_correction``, ``restore_page``. The agent must NOT
  initiate these on its own — they only fire in response to a user
  correction in the post-render review loop.

If a future tool ships that mutates ``page.text``, ``page.image``, or
removes a page without going through either a verbatim-only prompt or a
user-supplied string, that's a preserve-child-voice violation.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from src.agent import Tool
from src.builder import build_pdf
from src.draft import Draft, atomic_copy, next_version_number, slugify, to_book
from src.imposition import impose_a5_to_a4
from src.prune import prune
from src.providers.image import ImageGenerationError, ImageProvider
from src.schema import VALID_COVER_STYLES, VALID_LAYOUTS


def open_in_default_viewer(path: Path) -> None:
    """Hand ``path`` to the operating system's default handler.

    Windows uses the ``start`` verb via ``os.startfile``; macOS calls
    ``open``; everything else tries ``xdg-open``. All three are
    fire-and-forget — no exception means the OS has accepted the
    launch request, but there's no guarantee the viewer actually
    opened the file (the caller treats any raise as "couldn't open",
    silently).
    """
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    # start_new_session so the child survives our exit and doesn't
    # turn into a zombie waiting on the Python process to reap it.
    subprocess.Popen(
        [opener, str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


_METADATA_FIELDS = {"title", "author", "cover_subtitle", "back_cover_text"}
# set_metadata preserves whitespace on these fields — they carry the
# child's own words (cover subtitle, back-cover blurb) and should not
# be silently mutated. Title / author are conventional metadata and
# can be trimmed.
_CHILD_VOICE_FIELDS = {"cover_subtitle", "back_cover_text"}
# "Typo" caps — anything beyond a short phrase is a story edit in disguise.
_MAX_TYPO_CHARS = 30
_MAX_TYPO_WORDS = 3

# Message fragments surfaced back to the agent. Centralised so multiple
# tools speak with one voice (and Sonar doesn't flag duplicated literals).
_MSG_NO_DRAFT = "No draft loaded. Ask the user to provide a PDF first."
_BOOK_GEN_DIR = ".book-gen"
# Extensions pdf_ingest._extension_for may emit. Broader than just the
# common PNG/JPG pair so a PDF embedding WebP/GIF/TIFF/BMP/JPEG2000
# (rare but legal — PDF supports ``/JPXDecode`` for JPEG2000) still
# round-trips through restore_page; narrow enough that an accidental
# stray ``.txt`` / ``.json`` in ``.book-gen/images/`` is not attached
# as a page image and later crashed by the renderer.
_PIL_IMAGE_EXTS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".jpeg2000",
        ".webp",
        ".gif",
        ".tiff",
        ".tif",
        ".bmp",
    }
)
_MSG_UNSET = "(unset — ask the user)"

# Single source of truth for the "don't echo this / don't ask for
# approval" suffix every auto-applying tool appends to its success
# reply. Centralised so the four sentinel branches in
# ``apply_sentinel_result`` and the ``propose_typo_fix_tool``
# handler stay lockstep — no per-branch wording drift ("this text"
# vs "this status") for future reviews to catch.
_NO_DISPLAY_NO_APPROVAL_SUFFIX = (
    "Continue; do not display or ask for approval."
)


def _reject_typo_fix(
    draft: Draft, page_n: int, before: str, after: str
) -> str | None:
    """Return the rejection message if this typo-fix request is malformed,
    or ``None`` if it's shaped like a plausible mechanical edit."""
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
    return None


def _find_typo_match(text: str, before: str) -> re.Match[str] | None:
    """Word-boundary substring match so ``cat → dog`` never rewrites ``scatter``."""
    pattern = r"(?<!\w)" + re.escape(before) + r"(?!\w)"
    return re.search(pattern, text)


def read_draft_tool(get_draft: Callable[[], Draft | None]) -> Tool:
    """Tool: summarise the loaded PDF draft for the agent.

    Read-only. Returns the child's text verbatim so the agent can see
    exactly what was written, including typos and invented words — the
    agent decides what to flag for the user.

    Pages whose image carries the child's text visually but whose PDF
    text layer is empty (Samsung Notes exports, phone scans, etc.) are
    pre-flagged with ``[image-only]`` and a single summary NOTE at the
    end that tells the agent to ask the user to transcribe rather than
    invent — preserve-child-voice enforced at the surface.
    """

    def handler(_input: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        # Compact ``[image-only]`` tags go inline on each flagged
        # page; the full preserve-child-voice rationale (ask the
        # user to transcribe, don't invent) lives exactly once in
        # the summary NOTE built by ``_build_image_only_note``.
        lines = _read_draft_header_lines(draft)
        page_lines, image_only_pages = _read_draft_page_lines(draft)
        lines.extend(page_lines)
        if image_only_pages:
            lines.append(_build_image_only_note(image_only_pages))
        return "\n".join(lines)

    return Tool(
        name="read_draft",
        description=(
            "Read the currently-loaded PDF draft. Returns the title, author, "
            "cover status, page count, and for each page whether it has a "
            "drawing, its layout, and the child's exact text. Pages whose "
            "text layer is empty but whose image carries text visually "
            "(Samsung Notes / phone-scan exports) are flagged "
            "``[image-only]`` with a summary NOTE — when that fires, call "
            "the ``transcribe_page`` tool on each flagged page to OCR via "
            "the active LLM's vision capability (registered on every real "
            "provider now); if the active model doesn't support vision, "
            "``transcribe_page`` surfaces a clean failure and the user "
            "can transcribe manually. When ``transcribe_page`` reports a "
            "page looks blank (the ``<BLANK>`` sentinel branch), the page "
            "is auto-hidden (``hide_page``) so it doesn't render as an "
            "empty spread — the user catches a wrongly-hidden page in the "
            "post-render review turn via ``restore_page``. Never invent "
            "or paraphrase the child's words. Call this at the start of "
            "a session to see what you're working with."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=handler,
    )


def _read_draft_header_lines(draft: Draft) -> list[str]:
    """Compose the title / author / cover / page-count header block
    that every ``read_draft`` reply opens with."""
    title = draft.title.strip() or _MSG_UNSET
    author = draft.author.strip() or _MSG_UNSET
    cover = "yes" if draft.cover_image is not None else _MSG_UNSET
    return [
        f"Title: {title}",
        f"Author: {author}",
        f"Cover drawing set: {cover}",
        f"{len(draft.pages)} pages:",
    ]


def _read_draft_page_lines(draft: Draft) -> tuple[list[str], list[int]]:
    """Return ``(page_lines, image_only_pages)``: one line per page,
    plus the 1-indexed pages flagged ``[image-only]`` (drawing but
    empty text — Samsung Notes / phone-scan exports). The compact
    tag is in the line itself; the full preserve-child-voice
    explanation lives in the single summary NOTE built by
    ``_build_image_only_note``. Pure function — caller appends the
    returned lines to its running list."""
    page_lines: list[str] = []
    image_only_pages: list[int] = []
    for i, page in enumerate(draft.pages, start=1):
        marker = "drawing" if page.image is not None else "no drawing"
        text = page.text.strip().replace("\n", " ")
        image_only = page.image is not None and not text
        tag = " [image-only]" if image_only else ""
        hidden_tag = " [hidden]" if page.hidden else ""
        if image_only:
            image_only_pages.append(i)
        page_lines.append(
            f"  Page {i} ({marker}, layout={page.layout}){hidden_tag}:{tag} {text}"
        )
    return page_lines, image_only_pages


def _build_image_only_note(image_only_pages: list[int]) -> str:
    """Single summary NOTE telling the agent why some pages are still
    flagged image-only after deterministic ingestion ran — and what
    to do about them (nothing, during the metadata phase)."""
    which = ", ".join(str(n) for n in image_only_pages)
    return (
        f"NOTE: page(s) {which} are image-only — the PDF has no "
        "text layer there, likely a Samsung Notes / phone-scan "
        "export. Deterministic ingestion already ran OCR + sentinel "
        "classification on every image-only page BEFORE your first "
        "turn; if any remain flagged here it means the OCR call "
        "failed (offline session, vision error) and the page "
        "didn't get transcribed automatically. Do NOT call "
        "``transcribe_page`` during the metadata phase to retry — "
        "proceed with metadata + render, and the user can ask for "
        "a re-OCR on the specific page in the post-render review "
        "turn. Preserve-child-voice: do not invent, paraphrase, or "
        "'guess' the child's words."
    )


def propose_typo_fix_tool(
    get_draft: Callable[[], Draft | None],
) -> Tool:
    """Tool: apply a mechanical typo / OCR-misread fix on one page.

    Only a substring substitution is allowed — and the total edit is
    bounded to a short run of characters so the agent can't funnel a
    sentence-level rewrite through this tool. Auto-applied without a y/n
    gate; bad fixes are caught in the post-render review turn.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        page_n = int(input_["page"])
        before = str(input_["before"])
        after = str(input_["after"])
        reason = str(input_.get("reason", ""))

        rejection = _reject_typo_fix(draft, page_n, before, after)
        if rejection is not None:
            return rejection

        page = draft.pages[page_n - 1]
        match = _find_typo_match(page.text, before)
        if match is None:
            return (
                f"Rejected: the word '{before}' does not appear on page "
                f"{page_n} as a whole word. Don't invent substitutions — "
                "propose a fix only when you can see the typo verbatim in "
                "the child's text."
            )

        page.text = page.text[: match.start()] + after + page.text[match.end():]
        reason_tag = f" ({reason})" if reason else ""
        return (
            f"Applied typo fix on page {page_n}{reason_tag} "
            f"({len(before)} → {len(after)} chars). "
            + _NO_DISPLAY_NO_APPROVAL_SUFFIX
        )

    return Tool(
        name="propose_typo_fix",
        description=(
            "Apply a mechanical typo / OCR-misread fix on one page. Only "
            "substring substitutions (≤30 chars each side) are allowed. "
            "Do NOT use this to rewrite sentences or 'polish' the child's "
            "voice."
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
            return _MSG_NO_DRAFT
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


def apply_text_correction_tool(get_draft: Callable[[], Draft | None]) -> Tool:
    """Tool: overwrite a page's text verbatim with a user-provided string.

    Intended for the post-render review turn: when the user says
    'page 3 text: <verbatim>', the agent calls this tool with the
    exact string. No model, no prompt, no heuristics — the incoming
    ``text`` is written straight into ``page.text``. The agent MUST
    NOT initiate this tool on its own; it is a user-initiated
    correction path.

    Side effect: if the target page is currently ``hidden=True`` the
    tool also clears the flag. A user issuing a correction on a
    hidden page almost certainly means "bring this page back with
    this text"; silently writing to ``page.text`` while the page is
    filtered out of the render by ``to_book`` would be a misleading
    no-op. The auto-unhide is named in the reply so the action is
    visible.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        page_n = int(input_["page"])
        text = input_["text"]
        if page_n < 1 or page_n > len(draft.pages):
            return (
                f"Page {page_n} is out of range — the draft has "
                f"{len(draft.pages)} pages."
            )
        page = draft.pages[page_n - 1]
        page.text = text
        if page.hidden:
            page.hidden = False
            return (
                f"Page {page_n} text updated (verbatim, {len(text)} chars) "
                f"and unhidden — page is now visible in the rendered PDF."
            )
        return f"Page {page_n} text updated (verbatim, {len(text)} chars)."

    return Tool(
        name="apply_text_correction",
        description=(
            "Replace the text of page N with the user-provided string, "
            "verbatim. Use this ONLY during the post-render review turn "
            "when the user says 'page N text: ...'. Do not invent or "
            "paraphrase — the ``text`` field is written into page.text "
            "exactly as passed in. If page N was hidden, this tool also "
            "unhides it (a correction on a hidden page implies the user "
            "wants it visible); the reply names the auto-unhide "
            "explicitly. Never call on your own initiative."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1},
                "text": {"type": "string"},
            },
            "required": ["page", "text"],
        },
        handler=handler,
    )


def restore_page_tool(
    get_draft: Callable[[], Draft | None],
    get_session_root: Callable[[], Path],
) -> Tool:
    """Tool: undo edits on a page by re-attaching ``pdf_ingest``'s
    original output and clearing the ``hidden`` flag.

    Concrete realisation of the input-preserved guarantee:
    ``.book-gen/images/page-NN.*`` (the extension depends on what
    ``pdf_ingest._extension_for`` derived from the PDF's embedded
    image — commonly ``.png`` or ``.jpg``; in principle any format
    PIL reports) is never deleted, so the child's original drawing
    is always available to re-attach. Called when the user says
    'page N restore' during the review turn. For a text reset, call
    ``apply_text_correction`` with the original string.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        page_n = int(input_["page"])
        if page_n < 1 or page_n > len(draft.pages):
            return (
                f"Page {page_n} is out of range — the draft has "
                f"{len(draft.pages)} pages."
            )
        page = draft.pages[page_n - 1]
        page.hidden = False
        images_dir = Path(get_session_root()) / _BOOK_GEN_DIR / "images"
        stem = f"page-{page_n:02d}"
        # Accept any extension pdf_ingest may have written — PNG and
        # JPEG are the common shapes, but ``_extension_for`` returns
        # whatever PIL detected (WebP, GIF, TIFF, BMP, or JPEG2000
        # from ``/JPXDecode`` streams on exotic PDFs). The allow-list
        # here is the known PIL image formats: it's permissive enough
        # for every format pdf_ingest can produce, but still rejects
        # stray non-image files (e.g. an accidental ``page-01.txt``)
        # that would break the renderer downstream.
        candidates = sorted(
            p
            for p in images_dir.glob(f"{stem}.*")
            if p.is_file() and p.suffix.lower() in _PIL_IMAGE_EXTS
        )
        # Prefer PNG if the same page has multiple extensions on disk
        # (deterministic — png is lossless, so keep it when present).
        original = next(
            (p for p in candidates if p.suffix.lower() == ".png"),
            candidates[0] if candidates else None,
        )
        if original is not None:
            page.image = original
            return f"Page {page_n} restored (image re-attached, unhidden)."
        return (
            f"Page {page_n} unhidden (no original image found at "
            f"{images_dir / stem}.*)"
        )

    return Tool(
        name="restore_page",
        description=(
            "Undo edits on page N: clear the hidden flag and re-attach "
            "the child's original drawing from pdf_ingest's per-page "
            "output (``.book-gen/images/page-NN.*`` — extension depends "
            "on what the PDF embedded, usually ``.png`` or ``.jpg``). "
            "Use during the post-render review turn when the user says "
            "'page N restore'. For a text reset, call "
            "apply_text_correction with the original string instead."
        ),
        input_schema={
            "type": "object",
            "properties": {"page": {"type": "integer", "minimum": 1}},
            "required": ["page"],
        },
        handler=handler,
    )


def set_cover_tool(get_draft: Callable[[], Draft | None]) -> Tool:
    """Tool: pick a page's drawing as the cover image and, optionally,
    the cover style template.

    ``poster`` is the one style that doesn't need a page drawing — it
    renders type-only. For every other style a ``page`` with an image
    is required.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        style = input_.get("style")
        page_n_raw = input_.get("page")
        error = _validate_cover_inputs(draft, style, page_n_raw)
        if error is not None:
            return error
        if style == "poster":
            return _apply_poster_cover(draft, page_n_raw)
        return _apply_image_cover(draft, style, page_n_raw)

    return Tool(
        name="set_cover",
        description=(
            "Pick the book's cover. ``page`` names which page's drawing "
            "to use as the cover image (required unless style='poster'). "
            "``style`` optionally picks the cover template: 'full-bleed' "
            "(drawing covers the page, title on a translucent band), "
            "'framed' (title at the top, letterboxed drawing below), "
            "'portrait-frame' (drawing inside a decorative border, "
            "title above), 'title-band-top' (coloured band with title "
            "at the top, drawing below), or 'poster' (type-only cover, "
            "no drawing). Defaults to 'full-bleed' when omitted. "
            "If the user wants an AI-generated cover instead of reusing "
            "a page's drawing, the ``generate_cover_illustration`` tool "
            "is available on the OpenAI provider — tell users on other "
            "providers they can switch via /model to access it. "
            "PRESERVE-CHILD-VOICE applies to the AI cover prompt too: "
            "describe the cover scene in your own words from the story's "
            "themes; do not quote or paraphrase the child's page text "
            "into the prompt."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1},
                "style": {
                    "type": "string",
                    "enum": sorted(VALID_COVER_STYLES),
                },
            },
            "required": [],
        },
        handler=handler,
    )


def hide_page_tool(
    get_draft: Callable[[], Draft | None],
) -> Tool:
    """Tool: mark a page as hidden so it doesn't appear in the rendered book.

    Input is preserved in ``draft.pages`` — nothing is deleted. The
    ``restore_page`` tool reverses this symmetrically. Use when a page
    is confirmed empty (e.g. a trailing blank from a phone-scan export,
    flagged by ``transcribe_page`` with the ``<BLANK>`` sentinel) and
    shouldn't appear in the printed book.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        page_n, error = _parse_skip_page_input(input_, draft)
        if error is not None:
            return error
        draft.pages[page_n - 1].hidden = True
        return (
            f"Page {page_n} hidden. Draft still has {len(draft.pages)} "
            f"page(s); hidden pages are excluded from render. "
            f"Use restore_page to reverse."
        )

    return Tool(
        name="hide_page",
        description=(
            "Mark page N as hidden so it doesn't render. Input is "
            "preserved — ``restore_page`` reverses this. Use when a "
            "page is confirmed empty (e.g. a trailing blank from a "
            "phone-scan export, flagged by transcribe_page with the "
            "``<BLANK>`` sentinel) and shouldn't appear in the "
            "printed book."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1},
            },
            "required": ["page"],
        },
        handler=handler,
    )


def _parse_skip_page_input(input_: dict, draft: Draft) -> tuple[int | None, str | None]:
    """Pull the 1-indexed ``page`` out of ``input_`` and bounds-check
    it against ``draft.pages``. Returns ``(page_n, None)`` on a clean
    input or ``(None, error_msg)`` when the caller sent something
    unusable — the tool returns the error as a regular result so the
    agent can recover without a crashed turn."""
    raw = input_.get("page")
    if raw is None:
        return None, (
            "Rejected: 'page' is required — which page should be removed?"
        )
    try:
        page_n = int(raw)
    except (TypeError, ValueError):
        return None, (
            f"Rejected: 'page' must be an integer; got {raw!r}. "
            "Pass the 1-indexed page number."
        )
    if page_n < 1 or page_n > len(draft.pages):
        return None, (
            f"Page {page_n} is out of range — the draft has "
            f"{len(draft.pages)} pages."
        )
    return page_n, None


def transcribe_page_tool(
    get_draft: Callable[[], Draft | None],
    get_llm: Callable[[], object],
) -> Tool:
    """Tool: use the active LLM's vision capability to transcribe a
    page's image text verbatim into ``draft.pages[n-1].text``.

    Escape hatch for image-only PDFs (Samsung Notes exports, phone
    scans) where the embedded text is pixels rather than ``/Font``
    glyphs and ``pypdf.extract_text`` legitimately returns empty.

    Preserve-child-voice is enforced on two axes:

    1. **Vision capability required.** Registered on every real
       provider (Anthropic / OpenAI / Google / Ollama), but the
       active *model* still has to support vision — Claude 3+,
       GPT-4o, Gemini 1.5+, LLaVA on Ollama. A non-vision model
       surfaces as a failed ``llm.chat`` call with a truncated
       error message in the tool result; it cannot hallucinate a
       transcription because each provider's message translator
       now forwards the image content block in its native wire
       format (OpenAI multi-modal content array, Gemini
       ``Part(inline_data=Blob(...))``, Ollama ``images`` list).
    2. **Verbatim three-sentinel prompt.** The vision prompt tells
       the model to classify the page and output the text exactly
       as written — no typo fixes, no "polish," no paraphrase.
       ``<TEXT>`` = pure text page (image cleared, layout →
       text-only); ``<MIXED>`` = drawing + text (image kept);
       ``<BLANK>`` = no text (page hidden).
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        page_n, page, error = _parse_transcribe_input(input_, draft)
        if error is not None:
            return error
        method = str(input_.get("method", "vision"))
        cleaned, error = _run_ocr_engine(method, input_, page, page_n, get_llm)
        if error is not None:
            return error
        empty_msg = _check_empty_reply(cleaned, page_n, method)
        if empty_msg is not None:
            return empty_msg
        return apply_sentinel_result(page, cleaned, page_n, method)

    return Tool(
        name="transcribe_page",
        description=(
            "Transcribe a single page's text from its image. Use this "
            "when a page is flagged ``[image-only]`` by read_draft — "
            "the embedded text layer is empty but the image clearly "
            "shows words. Two OCR engines via ``method``: 'vision' "
            "(default) goes through the active LLM's vision "
            "capability using a three-sentinel classifier; "
            "'tesseract' goes through a local pytesseract install "
            "(zero API cost, works offline, strong on typeset "
            "printed text like Turkish matbaa yazısı, noticeably "
            "weaker on handwriting). Prefer 'tesseract' for clean "
            "typed pages and pass ``lang='tur'`` (or 'eng', "
            "'tur+eng', etc., three-letter ISO-639-2/B codes). "
            "Preserve-child-voice: the vision prompt tells the model "
            "to copy the text verbatim (no typo fixes, no paraphrase) "
            "and classify the page into one of three sentinels: "
            "``<TEXT>`` (pure text — image is cleared, layout → "
            "text-only to avoid the duplicate-print bug); "
            "``<MIXED>`` (text + distinct drawing — text written, "
            "image and layout kept so the child's drawing survives); "
            "``<BLANK>`` (no text — page hidden). "
            "Vision-method registered on every real provider "
            "(Anthropic / OpenAI / Google / Ollama); a non-vision "
            "model surfaces as a failed chat call. Tesseract method "
            "needs ``pip install 'littlepress-ai[tesseract]'`` plus "
            "a system tesseract binary + matching traineddata — when "
            "they're missing the tool surfaces a clean install hint "
            "rather than a crash."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1},
                "method": {
                    "type": "string",
                    "enum": ["vision", "tesseract"],
                    "description": (
                        "OCR engine. Default 'vision' — uses the "
                        "active LLM's vision capability with the "
                        "three-sentinel classifier. 'tesseract' "
                        "routes through a local pytesseract install "
                        "(zero API cost, offline, strong on typeset "
                        "printed text; handwriting is shakier). "
                        "Requires both the pytesseract package AND "
                        "the system tesseract binary with the "
                        "matching language trained-data installed."
                    ),
                },
                "lang": {
                    "type": "string",
                    "description": (
                        "Tesseract language code (only used when "
                        "method='tesseract'). Examples: 'eng' "
                        "(default), 'tur' for Turkish, 'tur+eng' "
                        "for mixed."
                    ),
                },
            },
            "required": ["page"],
        },
        handler=handler,
    )


def _parse_transcribe_input(
    input_: dict, draft: Draft
) -> tuple[int | None, object, str | None]:
    """Validate the 1-indexed page number. Returns ``(page_n, page,
    None)`` on success or ``(None, None, error)`` when the input is
    unusable."""
    raw = input_.get("page")
    if raw is None:
        return None, None, (
            "Rejected: 'page' is required — which page should be "
            "transcribed?"
        )
    try:
        page_n = int(raw)
    except (TypeError, ValueError):
        return None, None, (
            f"Rejected: 'page' must be an integer; got {raw!r}. "
            "Pass the 1-indexed page number."
        )
    if page_n < 1 or page_n > len(draft.pages):
        return None, None, (
            f"Page {page_n} is out of range — the draft has "
            f"{len(draft.pages)} pages."
        )
    page = draft.pages[page_n - 1]
    if page.image is None:
        return None, None, (
            f"Page {page_n} has no image to transcribe — nothing to "
            "OCR."
        )
    return page_n, page, None


def call_vision_for_transcription(
    llm: object, image_path: Path, page_n: int
) -> tuple[str, str | None]:
    """Send the page image to the active LLM and normalise errors
    into ``(cleaned_reply, None)`` or ``("", error_message)``.
    ``ImportError`` gets its own branch (SDK missing is distinct
    from "provider doesn't support vision"); everything else is
    truncated to 200 chars so an SDK that interpolates the base64
    payload into its error message can't echo the image back."""
    messages = [
        {
            "role": "user",
            "content": [
                _build_image_block(image_path),
                {"type": "text", "text": _TRANSCRIBE_PROMPT},
            ],
        }
    ]
    try:
        reply = llm.chat(messages)
    except ImportError as e:
        return "", (
            f"Transcription failed on page {page_n}: SDK not installed "
            f"({str(e)[:200]}). Ask the user to transcribe manually."
        )
    except Exception as e:  # noqa: BLE001 — every SDK raises a different hierarchy
        return "", (
            f"Transcription failed on page {page_n}: {str(e)[:200]}. "
            "This often means the active LLM doesn't support vision, "
            "or the network is down. Ask the user to transcribe "
            "manually, or switch to a multimodal provider via /model."
        )
    return str(reply).strip(), None


def _run_ocr_engine(
    method: str, input_: dict, page, page_n: int, get_llm
) -> tuple[str, str | None]:
    """Dispatch the OCR call to whichever engine ``method`` names.
    Validates ``method`` + ``lang`` at the boundary so the handler
    stays a short linear script. Returns ``(cleaned_reply, None)``
    on success or ``("", error_message)`` on any validation or
    engine failure — same shape the underlying ``_call_*``
    helpers use."""
    if method not in {"vision", "tesseract"}:
        return "", (
            f"Invalid method '{method}'. Valid values: "
            "'vision' (default; uses the active LLM) and "
            "'tesseract' (offline OCR, requires pytesseract + a "
            "system tesseract binary)."
        )
    if method == "tesseract":
        lang = str(input_.get("lang", "eng"))
        lang_error = _validate_tesseract_lang(lang)
        if lang_error is not None:
            return "", lang_error
        return _call_tesseract_for_transcription(
            Path(page.image), page_n, lang
        )
    return call_vision_for_transcription(
        get_llm(), Path(page.image), page_n
    )


import re as _re

# Tesseract's ``-l`` flag takes ISO-639-2/B codes ("eng", "tur") or a
# ``+``-joined list ("tur+eng"). Anything else — wrong separator,
# path traversal, CLI flag injection, stray casing — gets rejected at
# the tool boundary rather than reaching the CLI as a mysterious
# error. Three-letter lower-case codes only, optionally joined with
# a single ``+``.
_TESSERACT_LANG_RE = _re.compile(r"^[a-z]{3}(\+[a-z]{3})*$")


def _validate_tesseract_lang(lang: str) -> str | None:
    """Reject ``lang`` strings that don't look like one or more
    ISO-639-2/B codes. Returns a tool-result error message for the
    agent or ``None`` when the lang is shaped right."""
    if not _TESSERACT_LANG_RE.fullmatch(lang or ""):
        return (
            f"Invalid lang '{lang}'. Tesseract expects a three-letter "
            "ISO-639-2/B code, optionally ``+``-joined (e.g. 'eng', "
            "'tur', 'tur+eng'). Each code needs the matching "
            "traineddata pack installed on the system."
        )
    return None


def _call_tesseract_for_transcription(
    image_path: Path, page_n: int, lang: str
) -> tuple[str, str | None]:
    """Run offline OCR via pytesseract and normalise errors into
    ``(cleaned_reply, None)`` or ``("", error_message)``. Three
    distinct failure modes get their own clean-error message:
    ``pytesseract`` not installed (Python package), the system
    ``tesseract`` binary not on PATH, and any other exception from
    the OCR call.

    Tesseract is the fast + free path for Samsung-Notes-style
    typeset text (Turkish "matbaa yazısı") where LLM vision would
    cost a cloud round-trip per page. Handwriting still needs an
    LLM — classical OCR is shaky on it."""
    try:
        import pytesseract  # type: ignore[import-not-found]
    except ImportError:
        return "", (
            f"Transcription failed on page {page_n}: pytesseract is "
            "not installed. Install it with "
            "``pip install 'littlepress-ai[tesseract]'`` (and a "
            "system tesseract binary with your language trained-data, "
            "e.g. ``tesseract-ocr-tur`` on Ubuntu or via UB-Mannheim "
            "on Windows), or retry with method='vision'."
        )

    # Run the image through PIL first so a broken PNG surfaces as a
    # clean decode error rather than garbage OCR, and so the
    # pytesseract temp-file shim handles Windows long-path /
    # non-ASCII filenames the same way the vision path does.
    tess_not_found = getattr(pytesseract, "TesseractNotFoundError", None)
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            reply = pytesseract.image_to_string(img, lang=lang)
    except Exception as e:  # noqa: BLE001 — surface every tesseract error
        if tess_not_found is not None and isinstance(e, tess_not_found):
            return "", (
                f"Transcription failed on page {page_n}: tesseract "
                "binary not found on PATH. Install the system package "
                "(Windows: UB-Mannheim installer; macOS: "
                "``brew install tesseract tesseract-lang``; Linux: "
                "``apt install tesseract-ocr tesseract-ocr-tur``), or "
                f"retry with method='vision'. ({str(e)[:200]})"
            )
        return "", (
            f"Transcription failed on page {page_n}: tesseract error: "
            f"{str(e)[:200]}. Try method='vision' for a cloud fallback."
        )
    return str(reply).strip(), None


def _check_empty_reply(cleaned: str, page_n: int, method: str) -> str | None:
    """Early-return message when the OCR engine returns nothing at all
    (empty string after stripping). Returns ``None`` when the reply
    has content and should be forwarded to the sentinel parser.
    The empty-reply wording branches on ``method`` — Tesseract
    failures are not safety filters, and the retry advice differs."""
    if not cleaned:
        if method == "tesseract":
            return (
                f"Transcription failed on page {page_n}: tesseract "
                "returned no text. The image may have low contrast, "
                "too low a DPI, or the wrong ``lang`` trained-data "
                "for what's actually on the page. Try a different "
                "``lang``, a higher-resolution source, or switch to "
                "method='vision' for a cloud OCR pass."
            )
        return (
            f"Transcription failed on page {page_n}: provider "
            "returned empty text (often a safety filter or a "
            "vision-unsupported model). Draft left unchanged; "
            "ask the user to transcribe manually."
        )
    return None


def extract_sentinel(reply: str) -> tuple[str, str]:
    """Parse the model's reply into ``(sentinel, body)``.

    The first *non-empty* line is normalised (whitespace + backtick/quote
    stripped) and matched against the three known sentinels.  Leading blank
    lines are skipped so a reply like ``"\\n<TEXT>\\nhello"`` is handled
    identically to ``"<TEXT>\\nhello"``.  ``body`` is everything after the
    first non-empty line in the original reply, stripped of surrounding
    whitespace while preserving interior newlines (child's multi-line text).

    Returns ``("", "")`` for empty / all-whitespace input.
    Returns ``("", reply.strip())`` when no recognised sentinel is on the
    first non-empty line (model misbehaved — caller uses fallback)."""
    all_lines = reply.split("\n")
    non_empty = [line for line in all_lines if line.strip()]
    if not non_empty:
        return ("", "")
    raw_first = non_empty[0].strip().strip("`'\"").strip()
    first_idx = all_lines.index(non_empty[0])
    body = "\n".join(all_lines[first_idx + 1:]).strip()
    if raw_first in (_BLANK_SENTINEL, _TEXT_SENTINEL, _MIXED_SENTINEL):
        return raw_first, body
    return "", reply.strip()


def apply_sentinel_result(page, reply: str, page_n: int, method: str) -> str:
    """Parse the OCR reply and apply the appropriate action based on
    which sentinel the model used (or the fallback when it didn't).

    Vision replies use three-sentinel classification.
    Tesseract returns raw text — treated the same as ``<TEXT>``
    (clear image, set text-only) since Tesseract doesn't produce
    drawings alongside text."""
    # Tool-response messages are intentionally minimal — NO preview
    # of the transcribed text. If the response echoes the text back
    # the agent tends to re-display it to the user and default to
    # per-page approval prompts. The user audits page text in the
    # rendered PDF, not in chat.
    if method == "tesseract":
        # Tesseract raw text: apply as TEXT sentinel behaviour.
        page.text = reply
        page.image = None
        page.layout = "text-only"
        return (
            f"Page {page_n} transcribed ({len(reply)} chars, "
            f"pure text, layout text-only). "
            + _NO_DISPLAY_NO_APPROVAL_SUFFIX
        )

    sentinel, body = extract_sentinel(reply)

    if sentinel == _BLANK_SENTINEL:
        page.hidden = True
        return (
            f"Page {page_n} is blank, hidden. "
            + _NO_DISPLAY_NO_APPROVAL_SUFFIX
        )

    if sentinel == _TEXT_SENTINEL:
        page.text = body
        page.image = None
        page.layout = "text-only"
        return (
            f"Page {page_n} transcribed ({len(body)} chars, "
            f"pure text, layout text-only). "
            + _NO_DISPLAY_NO_APPROVAL_SUFFIX
        )

    if sentinel == _MIXED_SENTINEL:
        page.text = body
        return (
            f"Page {page_n} transcribed ({len(body)} chars, "
            f"drawing preserved, image and layout unchanged). "
            + _NO_DISPLAY_NO_APPROVAL_SUFFIX
        )

    # No recognised sentinel — model misbehaved. Write the raw reply
    # as page.text (best-effort) but DO NOT touch page.image or
    # page.layout — a non-destructive fallback preserves the child's
    # drawing until the user audits the render and corrects via
    # apply_text_correction / restore_page in the review turn.
    page.text = reply
    return (
        f"(warning: model did not use a sentinel) page {page_n} "
        f"text written ({len(reply)} chars, image and layout "
        f"unchanged). "
        + _NO_DISPLAY_NO_APPROVAL_SUFFIX
    )


# Anthropic recommends images no larger than 1568px on the long edge
# for vision — 5 MB per-image limit enforced server-side. Samsung Notes
# exports routinely ship ~3000x4000 pages, which would base64-encode
# beyond that limit and be rejected. Downscale to preserve readability
# while fitting the quota comfortably.
_TRANSCRIBE_MAX_IMAGE_EDGE = 1568

_TRANSCRIBE_PROMPT = (
    "Classify this image and transcribe any text it contains. "
    "A child wrote or typed this; preserve every spelling mistake, "
    "line break, punctuation choice, and capitalisation verbatim. "
    "Do NOT fix, polish, translate, reorder, or improve the wording "
    "in any way — preserve-child-voice. Do NOT describe or explain "
    "any drawing.\n\n"
    "You MUST reply with exactly ONE of these three sentinels on "
    "the first line, then (when applicable) the verbatim "
    "transcription on subsequent lines:\n\n"
    "<BLANK>\n"
    "  Use this sentinel alone when the page has no meaningful "
    "content (truly blank).\n\n"
    "<TEXT>\n"
    "  Use this sentinel when the image is pure text (e.g. a "
    "Samsung Notes screenshot or scanned typed page). Follow it "
    "with the verbatim transcription.\n\n"
    "<MIXED>\n"
    "  Use this sentinel when the image contains a distinct drawing "
    "alongside text. Follow it with the verbatim transcription of "
    "the TEXT ONLY — do not describe or mention the drawing.\n\n"
    "Reply format: sentinel on line 1, transcription on remaining "
    "lines (or nothing after <BLANK>). No preamble, no quotes, no "
    "commentary — only the sentinel line and the transcription."
)
# Sentinels the three-sentinel vision prompt asks for.
# Language-agnostic: the prompt applies equally to Turkish, English,
# or any other script, and all compliant replies collapse to one of
# these three tokens.
_BLANK_SENTINEL = "<BLANK>"
_TEXT_SENTINEL = "<TEXT>"
_MIXED_SENTINEL = "<MIXED>"


def _build_image_block(image_path: Path) -> dict:
    """Return an Anthropic-format image content block, downscaling
    when the source is larger than Anthropic's recommended edge so
    the request fits under the 5 MB per-image cap. PNG re-encode is
    lossless — no OCR-quality hit from the round-trip."""
    import base64
    import io
    import mimetypes

    media_type, _ = mimetypes.guess_type(image_path.name)
    if media_type is None:
        media_type = "image/png"

    from PIL import Image

    with Image.open(image_path) as img:
        w, h = img.size
        if max(w, h) > _TRANSCRIBE_MAX_IMAGE_EDGE:
            img.thumbnail(
                (_TRANSCRIBE_MAX_IMAGE_EDGE, _TRANSCRIBE_MAX_IMAGE_EDGE),
                Image.LANCZOS,
            )
            buf = io.BytesIO()
            # Re-encode as PNG regardless of source format. Keeps the
            # media_type honest and sidesteps JPEG lossy artefacts
            # when the original was PNG.
            img.save(buf, format="PNG")
            media_type = "image/png"
            raw = buf.getvalue()
        else:
            raw = image_path.read_bytes()

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(raw).decode("ascii"),
        },
    }



def _validate_cover_inputs(draft, style, page_n_raw) -> str | None:
    """Return a rejection string if ``style`` or ``page_n_raw`` don't
    match a valid cover, or ``None`` when the pair is shaped right.
    Style is checked first so a bad value doesn't half-commit state;
    page number is checked regardless of style so a typo doesn't get
    silently accepted by the poster branch."""
    if style is not None and style not in VALID_COVER_STYLES:
        return (
            f"Invalid style '{style}'. Valid styles: "
            f"{sorted(VALID_COVER_STYLES)}."
        )
    if page_n_raw is None:
        return None
    page_n = int(page_n_raw)
    if page_n < 1 or page_n > len(draft.pages):
        return (
            f"Page {page_n} is out of range — the draft has "
            f"{len(draft.pages)} pages."
        )
    return None


def _apply_poster_cover(draft, page_n_raw) -> str:
    """Poster is type-only: no drawing needed. Keep the existing
    ``cover_image`` alone so a previous full-bleed choice isn't
    silently discarded if the agent flips back later."""
    draft.cover_style = "poster"
    msg = "Cover set to 'poster' style (type-only — no drawing used)."
    if page_n_raw is not None:
        msg += " (The 'page' argument was ignored for this style.)"
    return msg


def _apply_image_cover(draft, style, page_n_raw) -> str:
    """Non-poster styles all need a page with an image; reject early
    if either's missing, then record the cover + optional style."""
    if page_n_raw is None:
        return (
            "page is required unless style='poster'. Name the page "
            "whose drawing should be the cover."
        )
    page_n = int(page_n_raw)
    page = draft.pages[page_n - 1]
    if page.image is None:
        return f"Page {page_n} has no drawing — can't use it as the cover."
    draft.cover_image = page.image
    if style is not None:
        draft.cover_style = style
    msg = f"Cover set to page {page_n}'s drawing ({page.image})"
    if style is not None:
        msg += f" with '{style}' layout"
    return msg + "."


# OpenAI ``gpt-image-1`` pricing (portrait 1024x1536, USD).
# APPROXIMATE — last spot-checked against openai.com/api/pricing/ in
# 2026-Q2. OpenAI quotes per-quality rates for square 1024x1024 and
# portraits scale ~1.5x. Treat these numbers as advisory; the actual
# bill lives on the user's OpenAI account. When a user reports a
# visible drift, re-check the pricing page and update here — both
# ``generate_cover_illustration`` and ``generate_page_illustration``
# read from this one constant so the refresh is a single edit.
_IMAGE_COST_USD = {"low": 0.02, "medium": 0.06, "high": 0.25}
# A5 covers are ≈ 2:3 portrait. 1024x1536 is the closest portrait size
# gpt-image-1 supports, and it's what the renderer letterboxes cleanly
# at A5 without wasted whitespace.
_IMAGE_SIZE_PORTRAIT = "1024x1536"


def generate_cover_illustration_tool(
    get_draft: Callable[[], Draft | None],
    get_session_root: Callable[[], Path],
    image_provider: ImageProvider,
    confirm: Callable[[str], bool],
) -> Tool:
    """Tool: generate a cover illustration from a text prompt and wire
    it up as the book's cover image.

    The user must approve both the prompt text and the estimated cost
    before any API call is made — the tool surfaces the price tier in
    the confirmation prompt so "high quality" isn't a silent 10x spend.

    On approval, the provider writes a PNG under ``<session_root>/
    .book-gen/images/cover-<hash>.png`` and the draft's ``cover_image``
    points at it. An optional ``style`` arg lets the agent pick the
    cover template in the same round (saves a separate ``set_cover``
    call).
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        prompt, quality, style, error = _parse_generate_cover_input(input_)
        if error is not None:
            return error
        confirm_msg = _build_generate_cover_confirm_prompt(prompt, quality)
        if not confirm(confirm_msg):
            return (
                "User declined the cover generation. Keep the existing "
                "cover (or ask the user to propose a different prompt)."
            )
        output_path = _cover_image_output_path(get_session_root(), prompt)
        try:
            image_provider.generate(
                prompt=prompt,
                output_path=output_path,
                size=_IMAGE_SIZE_PORTRAIT,
                quality=quality,
            )
        except ImageGenerationError as e:
            return f"Cover generation failed: {e}"
        return _apply_generated_cover(draft, output_path, style)

    return Tool(
        name="generate_cover_illustration",
        description=(
            "Generate a cover illustration from a text prompt using "
            "OpenAI's gpt-image-1 (requires an OpenAI API key). The user "
            "is shown the prompt and the estimated cost and must confirm "
            "before any API call happens. On approval the image is saved "
            "into the project and set as the book's cover. Use this only "
            "when the user explicitly wants an AI-generated cover — "
            "prefer reusing a page's existing drawing via set_cover so "
            "the child's artwork leads. PRESERVE-CHILD-VOICE: describe "
            "the cover scene in your own words from the story's themes; "
            "do NOT quote or paraphrase the child's page text into the "
            "prompt. The cover picture may be generated, but the "
            "wording that produces it must not launder the child's "
            "sentences through the image model. 'quality' trades off "
            "cost vs detail: low ≈ $0.02, medium ≈ $0.06, high ≈ $0.25. "
            "'style' is optional and picks the cover template; omit it "
            "to leave the current choice alone."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "quality": {
                    "type": "string",
                    "enum": sorted(_IMAGE_COST_USD),
                },
                "style": {
                    "type": "string",
                    "enum": sorted(VALID_COVER_STYLES),
                },
            },
            "required": ["prompt"],
        },
        handler=handler,
    )


def _parse_generate_cover_input(
    input_: dict,
) -> tuple[str, str, str | None, str | None]:
    """Pull ``prompt`` / ``quality`` / ``style`` out of the input
    dict and validate the three. Returns
    ``(prompt, quality, style, None)`` on success or
    ``("", "", None, error_message)`` on the first invalid field."""
    prompt = str(input_.get("prompt", "")).strip()
    if not prompt:
        return "", "", None, (
            "Rejected: prompt is required. Ask the user to describe "
            "the cover illustration they want."
        )
    quality = str(input_.get("quality", "medium"))
    if quality not in _IMAGE_COST_USD:
        return "", "", None, (
            f"Invalid quality '{quality}'. "
            f"Valid values: {sorted(_IMAGE_COST_USD)}."
        )
    style = input_.get("style")
    if style is not None and style not in VALID_COVER_STYLES:
        return "", "", None, (
            f"Invalid style '{style}'. Valid styles: "
            f"{sorted(VALID_COVER_STYLES)}."
        )
    return prompt, quality, style, None


def _build_generate_cover_confirm_prompt(prompt: str, quality: str) -> str:
    cost = _IMAGE_COST_USD[quality]
    return (
        "Generate a cover illustration with OpenAI gpt-image-1?\n"
        f"  Prompt : {prompt}\n"
        f"  Quality: {quality} (~${cost:.2f})\n"
        "This will call the OpenAI image API and bill your account."
    )


def _apply_generated_cover(
    draft: Draft, output_path: Path, style: str | None
) -> str:
    """Wire the newly-generated image into the draft and optionally
    set the cover style. Return the agent-facing success message."""
    draft.cover_image = output_path
    if style is not None:
        draft.cover_style = style
    suffix = f" Cover style set to '{style}'." if style is not None else ""
    return (
        f"Cover illustration generated at {output_path}. "
        f"Draft cover_image updated.{suffix}"
    )


def _cover_image_output_path(session_root: Path, prompt: str) -> Path:
    """Build a unique ``.book-gen/images/cover-<hash>.png`` for this
    generation. The hash includes the prompt plus a call counter so
    regenerating with the same prompt doesn't overwrite the prior
    attempt — the user may want to compare results."""
    return _hashed_image_output_path(session_root, prompt, "cover")


def _hashed_image_output_path(
    session_root: Path, prompt: str, prefix: str
) -> Path:
    """Shared helper for ``cover-<hash>.png`` / ``page-<hash>.png``
    output paths. The token includes the prompt + a nanosecond
    timestamp so regenerating with the same prompt yields a fresh
    filename and the old render stays on disk for comparison."""
    import hashlib
    import time

    token = f"{prompt}|{time.time_ns()}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]
    return session_root / _BOOK_GEN_DIR / "images" / f"{prefix}-{digest}.png"


def generate_page_illustration_tool(
    get_draft: Callable[[], Draft | None],
    get_session_root: Callable[[], Path],
    image_provider: ImageProvider,
    confirm: Callable[[str], bool],
) -> Tool:
    """Tool: generate an AI illustration for a specific page and wire
    it up as that page's drawing.

    Symmetric to ``generate_cover_illustration`` but writes to
    ``draft.pages[n-1].image`` instead of ``draft.cover_image``.
    Restores illustrations on pages that ``transcribe_page`` cleared
    (the Samsung-Notes duplicate-text fix) — or adds a fresh
    drawing to any ``text-only`` page when the child wants one.

    Same preserve-child-voice shape as the cover variant: user
    must approve the prompt + quality + price; the prompt must be
    the agent's own words, not a paraphrase of the child's page
    text; an optional ``layout`` switches the page off ``text-only``
    if the user wants image-top / image-bottom / image-full.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        page_n, page, error = _parse_page_illustration_input(input_, draft)
        if error is not None:
            return error
        prompt, quality, layout, error = _parse_page_illustration_fields(input_)
        if error is not None:
            return error

        confirm_msg = _build_page_illustration_confirm_prompt(
            page_n, prompt, quality, layout, existing_image=page.image
        )
        if not confirm(confirm_msg):
            return (
                f"User declined the page {page_n} illustration "
                "generation. Keep the existing image (if any) or ask "
                "the user to propose a different prompt."
            )
        output_path = _hashed_image_output_path(
            get_session_root(), prompt, f"page-{page_n}"
        )
        try:
            image_provider.generate(
                prompt=prompt,
                output_path=output_path,
                size=_IMAGE_SIZE_PORTRAIT,
                quality=quality,
            )
        except ImageGenerationError as e:
            return f"Page {page_n} illustration generation failed: {e}"

        page.image = output_path
        if layout is not None:
            page.layout = layout
        preview = (
            f" Layout set to '{layout}'." if layout is not None else ""
        )
        return (
            f"Page {page_n} illustration generated at {output_path}. "
            f"Draft page image updated.{preview}"
        )

    return Tool(
        name="generate_page_illustration",
        description=(
            "Generate an AI illustration for a specific page using "
            "OpenAI's gpt-image-1 (requires an OpenAI API key). The "
            "common case: after ``transcribe_page`` clears a "
            "Samsung-Notes-style source image, the page needs a "
            "fresh drawing; this tool produces one. PRESERVE-CHILD-"
            "VOICE: describe the scene in your OWN words from the "
            "story's themes — do NOT quote or paraphrase the "
            "child's page text into the image prompt. The user is "
            "shown the prompt and the estimated cost (low ≈ $0.02, "
            "medium ≈ $0.06, high ≈ $0.25 per 1024x1536 portrait) "
            "and must confirm before any API call happens. On "
            "approval the PNG is saved into the project and set as "
            "the page's ``image``. An optional ``layout`` switches "
            "the page off ``text-only`` (image-top / image-bottom / "
            "image-full). Registered only on the OpenAI provider — "
            "on other providers, tell the user to switch via "
            "/model first."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1},
                "prompt": {"type": "string"},
                "quality": {
                    "type": "string",
                    "enum": sorted(_IMAGE_COST_USD),
                },
                "layout": {
                    "type": "string",
                    "enum": ["image-bottom", "image-full", "image-top"],
                },
            },
            "required": ["page", "prompt"],
        },
        handler=handler,
    )


def _parse_page_illustration_input(
    input_: dict, draft: Draft
) -> tuple[int | None, object, str | None]:
    """Pull + validate the 1-indexed ``page``. Returns
    ``(page_n, page, None)`` on success or
    ``(None, None, error_msg)`` on the first invalid value."""
    raw = input_.get("page")
    if raw is None:
        return None, None, (
            "Rejected: 'page' is required — which page should get "
            "the new illustration?"
        )
    try:
        page_n = int(raw)
    except (TypeError, ValueError):
        return None, None, (
            f"Rejected: 'page' must be an integer; got {raw!r}. "
            "Pass the 1-indexed page number."
        )
    if page_n < 1 or page_n > len(draft.pages):
        return None, None, (
            f"Page {page_n} is out of range — the draft has "
            f"{len(draft.pages)} pages."
        )
    return page_n, draft.pages[page_n - 1], None


def _parse_page_illustration_fields(
    input_: dict,
) -> tuple[str, str, str | None, str | None]:
    """Validate ``prompt`` / ``quality`` / ``layout``. Returns
    ``(prompt, quality, layout, None)`` or
    ``("", "", None, error_msg)`` on the first invalid field."""
    prompt = str(input_.get("prompt", "")).strip()
    if not prompt:
        return "", "", None, (
            "Rejected: prompt is required. Ask the user to describe "
            "the illustration they want on this page."
        )
    quality = str(input_.get("quality", "medium"))
    if quality not in _IMAGE_COST_USD:
        return "", "", None, (
            f"Invalid quality '{quality}'. "
            f"Valid values: {sorted(_IMAGE_COST_USD)}."
        )
    layout = input_.get("layout")
    if layout is None:
        return prompt, quality, None, None
    if layout == "text-only":
        # Choosing ``text-only`` on a tool whose job is to write an
        # image onto the page is nonsensical — the user pays for a
        # PNG, the file gets written, ``page.image`` is set, and
        # then the layout hides it. Reject early before any API call.
        return "", "", None, (
            "Invalid layout 'text-only' for generate_page_illustration: "
            "this tool writes an image onto the page; a text-only "
            "layout would pay for the image and then hide it. Pick "
            "one of: image-top, image-bottom, image-full."
        )
    if layout not in VALID_LAYOUTS:
        return "", "", None, (
            f"Invalid layout '{layout}'. Valid layouts for pages "
            "that carry an image: image-top, image-bottom, image-full."
        )
    return prompt, quality, layout, None


def _build_page_illustration_confirm_prompt(
    page_n: int,
    prompt: str,
    quality: str,
    layout: str | None,
    *,
    existing_image,
) -> str:
    cost = _IMAGE_COST_USD[quality]
    layout_line = (
        f"  Layout : {layout}\n" if layout is not None else ""
    )
    # Overwrite warning: the existing image's draft-level reference
    # is replaced on approval. The user can reload the PDF to get
    # a scanned original back, but an earlier AI-generated image
    # lives only on disk — once ``page.image`` points away from it,
    # we won't pull it back automatically.
    if existing_image is not None:
        overwrite_line = (
            f"  NOTE: page {page_n} already has an image "
            f"({existing_image}) and will be REPLACED — the existing "
            "drawing cannot be recovered in-session.\n"
        )
    else:
        overwrite_line = ""
    return (
        f"Generate an illustration for page {page_n} with OpenAI "
        "gpt-image-1?\n"
        f"  Prompt : {prompt}\n"
        f"  Quality: {quality} (~${cost:.2f})\n"
        f"{layout_line}"
        f"{overwrite_line}"
        "This will call the OpenAI image API and bill your account."
    )


_RHYTHM_RULES_FOR_TOOL_DESC = (
    "Rhythm rules (from select-page-layout skill): avoid the same "
    "layout three pages in a row; cap image-full at ~30% of inner "
    "pages so it stays a visual statement; alternate image-top / "
    "image-bottom to keep cadence varied."
)


def _neighbour_summary(draft: Draft, page_n: int, radius: int = 2) -> str:
    """Adjacent pages' layouts around ``page_n`` — surfaced in
    ``choose_layout``'s reply so the agent can sanity-check the
    rhythm without another ``read_draft`` round-trip."""
    start = max(1, page_n - radius)
    end = min(len(draft.pages), page_n + radius)
    entries = []
    for i in range(start, end + 1):
        marker = " (this page)" if i == page_n else ""
        entries.append(f"p{i}={draft.pages[i - 1].layout}{marker}")
    return ", ".join(entries)


def choose_layout_tool(get_draft: Callable[[], Draft | None]) -> Tool:
    """Tool: set the per-page layout.

    Enforces the first rule of the select-page-layout skill: a page
    with no image must render as ``text-only``. Agent can pick among
    the four valid layouts for pages that do have an image. After
    applying, the reply includes the adjacent pages' layouts so the
    agent can keep an eye on the rhythm without re-calling
    ``read_draft``.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
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
        neighbours = _neighbour_summary(draft, page_n)
        return (
            f"Page {page_n} layout set to {layout}{suffix}. "
            f"Surrounding rhythm: {neighbours}."
        )

    return Tool(
        name="choose_layout",
        description=(
            "Set the per-page layout. Valid: image-top, image-bottom, "
            "image-full, text-only. Pages without a drawing must be "
            "text-only. Include a short reason so the user sees why. "
            + _RHYTHM_RULES_FOR_TOOL_DESC
            + " The reply includes the neighbouring pages' layouts so "
            "you can check the rhythm before picking the next page."
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


def _mirror_stable(versioned: Path, stable: Path) -> bool:
    """Atomically replace ``stable`` with a copy of ``versioned``.

    Returns ``True`` on success, ``False`` if the stable path is locked
    (typical on Windows when the user has the previous PDF open in a
    viewer). A locked stable file isn't a render failure — the versioned
    file is fresh — so the caller keeps going and tells the user.
    """
    try:
        atomic_copy(versioned, stable)
        return True
    except OSError:
        return False


def _render_message(
    versioned: Path,
    stable: Path,
    *,
    stable_updated: bool,
    opened: bool,
) -> str:
    """Assemble the A5 success line for the agent's reply.

    A single render drops four files (stable + versioned × A5 +
    booklet). The user reads four files as "why is this producing so
    much stuff?" unless each file's role is named. This message
    focuses on the A5 pair; the booklet pair is narrated by
    ``_impose_and_mirror`` in the same shape.
    """
    if not stable_updated:
        return (
            f"Wrote snapshot {versioned}. Couldn't update {stable.name} "
            "(is it open in a PDF viewer? close it and copy "
            f"{versioned.name} over {stable.name} to refresh)."
        )
    opened_tail = (
        " Opened it in your viewer."
        if opened
        else " Open it manually — couldn't launch a PDF viewer here."
    )
    return (
        f"A5 book written to {stable} — this is the file to open and "
        f"read.{opened_tail} "
        f"Also kept a snapshot at {versioned.name} (rollback only, "
        "safe to ignore unless you want to compare with a later render)."
    )


def _impose_and_mirror(
    versioned_a5: Path,
    stable_a5: Path,
    stable_updated: bool,
    message: str,
) -> str:
    """Produce the A4 booklet and mirror it alongside the A5 pair."""
    versioned_booklet = versioned_a5.with_name(
        f"{versioned_a5.stem}_A4_booklet.pdf"
    )
    stable_booklet = stable_a5.with_name(f"{stable_a5.stem}_A4_booklet.pdf")
    try:
        impose_a5_to_a4(versioned_a5, versioned_booklet)
    except Exception as e:
        return (
            f"{message} Booklet imposition failed: {e}. The A5 "
            "stayed on disk — the user can still print it."
        )
    booklet_stable_updated = stable_updated and _mirror_stable(
        versioned_booklet, stable_booklet
    )
    booklet_target = stable_booklet if booklet_stable_updated else versioned_booklet
    return (
        f"{message} "
        f"A4 booklet written to {booklet_target} — print this one "
        "double-sided (flipped on short edge), fold in half, staple the "
        "spine. "
        f"Also kept a snapshot at {versioned_booklet.name} (rollback "
        "only, safe to ignore unless you want to compare with a later "
        "render)."
    )


def propose_layouts_tool(
    get_draft: Callable[[], Draft | None],
) -> Tool:
    """Tool: propose layouts for *every* page at once and auto-apply.

    The earlier per-page ``choose_layout`` tool produces good results
    but is awkward for the "settle on a rhythm" phase of the
    conversation — the agent has to ask the user to approve N tiny
    decisions. This tool batches them: one call, immediate application.
    For surgical tweaks afterwards the per-page tool is still the right
    call.

    Layouts are auto-applied without a y/n gate; the user catches any
    bad layout in the post-render review turn instead.
    """

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        items = input_.get("layouts") or []
        if len(items) != len(draft.pages):
            return (
                "propose_layouts expects one entry per page "
                f"({len(draft.pages)} needed, got {len(items)}). This "
                "tool is for the full rhythm — use choose_layout for "
                "a partial change."
            )
        # Validate every proposed layout first. Partial application
        # would leave the user with a mix they didn't want.
        rejection = _reject_layout_batch(draft, items)
        if rejection is not None:
            return rejection

        for item in items:
            draft.pages[int(item["page"]) - 1].layout = str(item["layout"])
        return f"Applied layouts to all {len(items)} pages."

    return Tool(
        name="propose_layouts",
        description=(
            "Set the layout for EVERY page at once in a single call. "
            "Auto-applies — do NOT ask the user for a yes/no; the user "
            "audits the finished PDF in the post-render review turn. "
            "Use this right after metadata is settled. For surgical "
            "tweaks afterwards, use choose_layout. Valid layouts: "
            "image-top, image-bottom, image-full, text-only. Pages "
            "without a drawing must be text-only. "
            + _RHYTHM_RULES_FOR_TOOL_DESC
            + " Since you see every page at once here, use that view "
            "to make the cadence feel varied on paper."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "layouts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer", "minimum": 1},
                            "layout": {
                                "type": "string",
                                "enum": sorted(VALID_LAYOUTS),
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["page", "layout", "reason"],
                    },
                },
            },
            "required": ["layouts"],
        },
        handler=handler,
    )


def _reject_layout_batch(draft: Draft, items: list[dict]) -> str | None:
    """Return a rejection message if ``items`` can't be applied to
    ``draft`` as a whole, or ``None`` if the batch is clean."""
    seen_pages: set[int] = set()
    for item in items:
        page_n = int(item.get("page", 0))
        layout = str(item.get("layout", ""))
        if page_n < 1 or page_n > len(draft.pages):
            return (
                f"Page {page_n} is out of range — the draft has "
                f"{len(draft.pages)} pages."
            )
        if page_n in seen_pages:
            return f"Duplicate entry for page {page_n}."
        seen_pages.add(page_n)
        if layout not in VALID_LAYOUTS:
            return (
                f"Page {page_n}: invalid layout '{layout}'. "
                f"Valid layouts: {sorted(VALID_LAYOUTS)}."
            )
        page = draft.pages[page_n - 1]
        if page.image is None and layout != "text-only":
            return (
                f"Page {page_n} has no drawing — it must be text-only. "
                "Can't apply image-* layouts to an imageless page."
            )
    return None


def render_book_tool(
    get_draft: Callable[[], Draft | None],
    get_session_root: Callable[[], Path],
    open_file: Callable[[Path], None] | None = None,
) -> Tool:
    """Tool: build the finished A5 PDF (and optionally the A4 booklet).

    The agent calls this once all the necessary metadata is settled.
    Output goes under ``<session-root>/.book-gen/output/<slug>.pdf`` so
    the existing gitignore rule covers it. If ``impose=True`` the tool
    also writes ``<slug>_A4_booklet.pdf`` alongside; a booklet failure
    keeps the A5 intact and surfaces the error.

    After a successful A5 render the tool hands the file to
    ``open_file`` so the user's PDF viewer pops up automatically —
    without that step the user had to hunt through the filesystem to
    find the rendered book. The booklet is a print artefact and is
    NOT opened. Viewer failures are swallowed (the file is on disk;
    surfacing a "couldn't open viewer" in the agent reply would be
    noise). Defaults to :func:`open_in_default_viewer` when the caller
    doesn't inject its own opener (tests do).
    """
    opener = open_file if open_file is not None else open_in_default_viewer

    def handler(input_: dict) -> str:
        draft = get_draft()
        if draft is None:
            return _MSG_NO_DRAFT
        if not draft.title.strip():
            return (
                "Can't render yet: the draft has no title. Ask the user for "
                "one and use set_metadata before calling render_book."
            )

        impose = bool(input_.get("impose", False))
        source_dir = Path(get_session_root()) / _BOOK_GEN_DIR
        output_dir = source_dir / "output"
        slug = slugify(draft.title)
        # next_version_number needs the directory to exist so it can
        # scan for prior snapshots; create it up front.
        output_dir.mkdir(parents=True, exist_ok=True)
        version = next_version_number(output_dir, slug)
        versioned_a5 = (output_dir / f"{slug}.v{version}.pdf").resolve()
        stable_a5 = (output_dir / f"{slug}.pdf").resolve()

        try:
            book = to_book(draft, source_dir)
            # Render to the versioned filename — that's the canonical
            # artefact for this render. The stable name is a pointer.
            build_pdf(book, versioned_a5)
        except Exception as e:
            return f"Render failed: {e}"

        # Mirror to the stable name via atomic replace so an interrupted
        # copy leaves either the previous stable file or the new one —
        # never a half-written one. Windows holds an exclusive lock on
        # open PDFs; if the user has the previous stable copy open in
        # Acrobat we surface that separately without hiding the fact
        # that the render itself succeeded.
        stable_updated = _mirror_stable(versioned_a5, stable_a5)

        target = stable_a5 if stable_updated else versioned_a5
        try:
            opener(target)
            opened = True
        except Exception:
            # Viewer can't launch (headless env, OS permission) —
            # file is on disk and the path is in the reply.
            opened = False

        message = _render_message(
            versioned_a5, stable_a5, stable_updated=stable_updated, opened=opened
        )

        if impose:
            message = _impose_and_mirror(
                versioned_a5, stable_a5, stable_updated, message
            )

        # Housekeeping: drop orphan images from earlier AI retries and
        # snapshot PDFs beyond the most-recent few. Silent on failure —
        # locked files (PDF viewer on Windows) are caught inside prune.
        prune(Path(get_session_root()), draft)

        return message

    return Tool(
        name="render_book",
        description=(
            "Build the finished A5 picture-book PDF from the current draft. "
            "Set impose=true to also produce a 2-up A4 booklet ready to "
            "print double-sided, fold, and staple. Only call this once the "
            "title (and ideally author + cover) are set."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "impose": {
                    "type": "boolean",
                    "description": (
                        "Also produce the A4 booklet. Default false."
                    ),
                }
            },
            "required": [],
        },
        handler=handler,
    )
