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
# How many characters of surrounding page text to show in the y/n prompt
# so the user sees what they're actually approving (not just a→b).
_TYPO_CONTEXT_CHARS = 25

# Message fragments surfaced back to the agent. Centralised so multiple
# tools speak with one voice (and Sonar doesn't flag duplicated literals).
_MSG_NO_DRAFT = "No draft loaded. Ask the user to provide a PDF first."
_MSG_UNSET = "(unset — ask the user)"


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


def _build_typo_prompt(
    text: str, match: re.Match[str], page_n: int, before: str, after: str, reason: str
) -> str:
    """Render the y/n prompt with ±_TYPO_CONTEXT_CHARS of surrounding
    page text so the user sees what they're actually approving."""
    start = max(0, match.start() - _TYPO_CONTEXT_CHARS)
    end = min(len(text), match.end() + _TYPO_CONTEXT_CHARS)
    context = text[start:end].replace("\n", " ")
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    reason_tag = f" ({reason})" if reason else ""
    return (
        f"Page {page_n}: fix '{before}' → '{after}'{reason_tag} "
        f"in: {prefix}{context}{suffix}"
    )


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
        lines: list[str] = []
        title = draft.title.strip() or _MSG_UNSET
        author = draft.author.strip() or _MSG_UNSET
        cover = "yes" if draft.cover_image is not None else _MSG_UNSET
        lines.append(f"Title: {title}")
        lines.append(f"Author: {author}")
        lines.append(f"Cover drawing set: {cover}")
        lines.append(f"{len(draft.pages)} pages:")
        image_only_pages: list[int] = []
        for i, page in enumerate(draft.pages, start=1):
            marker = "drawing" if page.image is not None else "no drawing"
            text = page.text.strip().replace("\n", " ")
            # Samsung-Notes exports (and other image-text PDFs) have
            # pages with a drawing but no ``/Font`` resource — the
            # child's text lives visually inside the image and pypdf
            # returns empty. Flag these with a compact ``[image-only]``
            # tag; the English-sentence explanation (preserve-child-
            # voice, transcribe, don't invent) lives in the single
            # summary NOTE below so the signal isn't diluted by N
            # copies of the same line. Pages without an image are
            # already covered by "no drawing".
            image_only = page.image is not None and not text
            tag = " [image-only]" if image_only else ""
            if image_only:
                image_only_pages.append(i)
            lines.append(
                f"  Page {i} ({marker}, layout={page.layout}):{tag} {text}"
            )
        if image_only_pages:
            which = ", ".join(str(n) for n in image_only_pages)
            lines.append(
                f"NOTE: page(s) {which} are image-only — the PDF has no "
                "text layer there, likely a Samsung Notes / phone-scan "
                "export where the text is rendered inside the image. "
                "Use the ``transcribe_page`` tool to OCR each flagged "
                "page via the active LLM's vision capability (Claude 3+, "
                "GPT-4o, Gemini 1.5+), or ask the user to transcribe "
                "manually. Always confirm the transcription with the "
                "user before moving on. Do not invent, paraphrase, or "
                "'guess' the child's words — preserve-child-voice."
            )
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
            "the active LLM's vision (Anthropic only for now); if that "
            "tool isn't registered, ask the user to transcribe manually. "
            "Never invent or paraphrase the child's words. Call this at "
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

        prompt = _build_typo_prompt(page.text, match, page_n, before, after, reason)
        if not confirm(prompt):
            return f"User declined. Keep page {page_n} exactly as the child wrote it."

        page.text = page.text[: match.start()] + after + page.text[match.end():]
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


def transcribe_page_tool(
    get_draft: Callable[[], Draft | None],
    get_llm: Callable[[], object],
    confirm: Callable[[str], bool],
) -> Tool:
    """Tool: use the active LLM's vision capability to transcribe a
    page's image text verbatim into ``draft.pages[n-1].text``.

    Escape hatch for image-only PDFs (Samsung Notes exports, phone
    scans) where the embedded text is pixels rather than ``/Font``
    glyphs and ``pypdf.extract_text`` legitimately returns empty.

    Preserve-child-voice is enforced on three axes:

    1. **Provider gate (at REPL).** Only registered when the active
       provider is Anthropic, because only ``AnthropicProvider.chat``
       currently forwards image content blocks intact. Other
       providers' ``_messages_to_*`` translators silently drop image
       blocks, leading to hallucinated transcriptions.
    2. **User confirmation.** The OCR reply is shown to the user
       *before* landing in ``page.text`` — same y/n pattern as
       ``propose_typo_fix``. An existing transcription is surfaced
       in the prompt so the user sees what's being overwritten.
    3. **Verbatim prompt.** The vision prompt tells the model to
       output the text exactly as written — no typo fixes, no
       "polish," no paraphrase.
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
        if page.image is None:
            return (
                f"Page {page_n} has no image to transcribe — nothing to "
                "OCR."
            )

        image_block = _build_image_block(Path(page.image))
        messages = [
            {
                "role": "user",
                "content": [
                    image_block,
                    {"type": "text", "text": _TRANSCRIBE_PROMPT},
                ],
            }
        ]

        llm = get_llm()
        try:
            reply = llm.chat(messages)
        except ImportError as e:
            # SDK missing — a different failure class than "provider
            # doesn't support vision", hence a separate branch.
            return (
                f"Transcription failed on page {page_n}: SDK not "
                f"installed ({str(e)[:200]}). Ask the user to "
                "transcribe manually."
            )
        except Exception as e:  # noqa: BLE001 — every SDK raises a different hierarchy
            return (
                f"Transcription failed on page {page_n}: "
                f"{str(e)[:200]}. This often means the active LLM "
                "doesn't support vision, or the network is down. "
                "Ask the user to transcribe manually, or switch to "
                "a multimodal provider via /model."
            )

        cleaned = str(reply).strip()
        if not cleaned:
            # Google safety filter and OpenAI content_filter both
            # surface as an empty reply rather than an exception. We
            # mustn't write the empty string — it would blank a page
            # the user may have typed manually (and the "success"
            # message would mask the failure).
            return (
                f"Transcription failed on page {page_n}: provider "
                "returned empty text (often a safety filter or a "
                "vision-unsupported model). Draft left unchanged; "
                "ask the user to transcribe manually."
            )
        if _is_blank_sentinel_reply(cleaned):
            # Samsung Notes exports routinely trail blank pages, and
            # the prompt asks the vision model to answer those with
            # the ``<BLANK>`` sentinel rather than fabricating text.
            # When the model complies, leave ``page.text`` alone and
            # tell the agent the page is probably blank — same shape
            # as the empty-reply branch but a distinct message so the
            # agent knows the model *saw* the page and confirmed it
            # was empty, rather than refusing to answer.
            return (
                f"Page {page_n} looks blank to the vision model "
                "(no transcribable text on the image). Draft left "
                "unchanged — ask the user whether this page was meant "
                "to be empty (e.g. a trailing blank from the export) "
                "or whether they want to skip it / mark it as the "
                "back cover."
            )

        prompt_msg = _build_transcribe_confirm_prompt(page_n, page.text, cleaned)
        if not confirm(prompt_msg):
            return (
                f"User declined the OCR transcription for page {page_n}. "
                "Draft unchanged. Ask them to transcribe manually, or "
                "call transcribe_page again after adjusting."
            )

        page.text = cleaned
        preview = cleaned[:80].replace("\n", " ")
        return (
            f"Page {page_n} transcribed and applied ({len(cleaned)} "
            f"chars). Preview: {preview!r}."
        )

    return Tool(
        name="transcribe_page",
        description=(
            "Transcribe a single page's text from its image using the "
            "active LLM's vision capability. Use this when a page is "
            "flagged ``[image-only]`` by read_draft — the embedded "
            "text layer is empty but the image clearly shows words. "
            "Preserve-child-voice: the vision prompt tells the model "
            "to copy the text verbatim (no typo fixes, no paraphrase) "
            "AND the user must approve the OCR reply via a y/n prompt "
            "before it lands in the draft — same gate pattern as "
            "propose_typo_fix. Registered only on Anthropic today "
            "(the other providers don't forward image content blocks "
            "yet); on non-Anthropic sessions the tool isn't available "
            "and the user should transcribe manually."
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


# Anthropic recommends images no larger than 1568px on the long edge
# for vision — 5 MB per-image limit enforced server-side. Samsung Notes
# exports routinely ship ~3000x4000 pages, which would base64-encode
# beyond that limit and be rejected. Downscale to preserve readability
# while fitting the quota comfortably.
_TRANSCRIBE_MAX_IMAGE_EDGE = 1568

_TRANSCRIBE_PROMPT = (
    "Transcribe the text visible in this image EXACTLY as written. A "
    "child wrote or typed this; preserve every spelling mistake, line "
    "break, punctuation choice, and capitalisation verbatim. Do NOT "
    "fix, polish, or improve the wording in any way — "
    "preserve-child-voice.\n\n"
    "If the image has NO visible text (a truly blank page), reply "
    "with exactly <BLANK> on its own — no quotes, no explanation, "
    "nothing else. Otherwise output ONLY the transcribed text, "
    "with no preamble, quotes, or commentary."
)
# The sentinel the prompt asks for when the page carries no text.
# Language-agnostic: the prompt applies equally to Turkish, English,
# or any other script, and all compliant replies collapse to this
# one token. A hedged real transcription ("I cannot make out the
# last line, but the rest reads: '…'") never collides with this
# check, so it reaches the confirm gate intact.
_BLANK_SENTINEL = "<BLANK>"


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


def _is_blank_sentinel_reply(reply: str) -> bool:
    """Return True when the LLM's reply is the ``<BLANK>`` sentinel
    (possibly wrapped in whitespace, quotes, or backticks) that the
    prompt asks for on empty pages.

    Exact comparison after stripping wrapping, so a story that
    happens to contain ``<BLANK>`` as a substring inside a longer
    sentence still transcribes through to the confirm gate. The
    confirm gate remains the last line of defence for prose-style
    meta-responses the model emits when it ignores the sentinel
    instruction."""
    core = reply.strip().strip("`'\"").strip()
    return core == _BLANK_SENTINEL


def _build_transcribe_confirm_prompt(
    page_n: int, existing_text: str, new_text: str
) -> str:
    """Compose the y/n prompt shown to the user. When the page is
    empty we render a simple "apply this transcription?" message;
    when it already carries text (user typed it manually earlier)
    the prompt shows both so the user can see what's being
    overwritten."""
    if existing_text.strip():
        return (
            f"Replace the existing text on page {page_n}?\n"
            f"  Existing (user-typed):\n    {existing_text!r}\n"
            f"  New (OCR):\n    {new_text!r}\n"
            "Approve the overwrite?"
        )
    return (
        f"Apply this OCR transcription to page {page_n}?\n"
        f"  {new_text!r}\n"
        "Approve?"
    )


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


# OpenAI ``gpt-image-1`` pricing (portrait 1024x1536, USD, approximate).
# Drives the confirmation prompt shown to the user; actual billing
# happens on the user's OpenAI account. Check the current rates at
# https://openai.com/api/pricing/ when a visible drift is reported.
_IMAGE_COST_USD = {"low": 0.02, "medium": 0.07, "high": 0.19}
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

        prompt = str(input_.get("prompt", "")).strip()
        if not prompt:
            return (
                "Rejected: prompt is required. Ask the user to describe "
                "the cover illustration they want."
            )

        quality = str(input_.get("quality", "medium"))
        if quality not in _IMAGE_COST_USD:
            return (
                f"Invalid quality '{quality}'. "
                f"Valid values: {sorted(_IMAGE_COST_USD)}."
            )

        style = input_.get("style")
        if style is not None and style not in VALID_COVER_STYLES:
            return (
                f"Invalid style '{style}'. Valid styles: "
                f"{sorted(VALID_COVER_STYLES)}."
            )

        cost = _IMAGE_COST_USD[quality]
        confirm_msg = (
            "Generate a cover illustration with OpenAI gpt-image-1?\n"
            f"  Prompt : {prompt}\n"
            f"  Quality: {quality} (~${cost:.2f})\n"
            "This will call the OpenAI image API and bill your account."
        )
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

        draft.cover_image = output_path
        if style is not None:
            draft.cover_style = style
        suffix = f" Cover style set to '{style}'." if style is not None else ""
        return (
            f"Cover illustration generated at {output_path}. "
            f"Draft cover_image updated.{suffix}"
        )

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
            "cost vs detail: low ≈ $0.02, medium ≈ $0.07, high ≈ $0.19. "
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


def _cover_image_output_path(session_root: Path, prompt: str) -> Path:
    """Build a unique ``.book-gen/images/cover-<hash>.png`` for this
    generation. The hash includes the prompt plus a call counter so
    regenerating with the same prompt doesn't overwrite the prior
    attempt — the user may want to compare results."""
    import hashlib
    import time

    token = f"{prompt}|{time.time_ns()}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]
    return session_root / ".book-gen" / "images" / f"cover-{digest}.png"


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
    """Assemble the A5 success line for the agent's reply."""
    if not stable_updated:
        return (
            f"Wrote snapshot {versioned}. Couldn't update {stable.name} "
            "(is it open in a PDF viewer? close it and copy "
            f"{versioned.name} over {stable.name} to refresh)."
        )
    tail = (
        " and opened it in your viewer."
        if opened
        else ". Open it manually — couldn't launch a PDF viewer here."
    )
    return f"Wrote A5 book to {stable} (also kept snapshot {versioned.name}){tail}"


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
        f"{message} Also wrote A4 booklet to {booklet_target} (snapshot "
        f"{versioned_booklet.name}). Tell the user to print "
        "double-sided (flipped on short edge), fold, and staple."
    )


def propose_layouts_tool(
    get_draft: Callable[[], Draft | None],
    confirm: Callable[[str], bool],
) -> Tool:
    """Tool: propose layouts for *every* page at once, show a table,
    apply all if the user approves.

    The earlier per-page ``choose_layout`` tool produces good results
    but is awkward for the "settle on a rhythm" phase of the
    conversation — the agent has to ask the user to approve N tiny
    decisions. This tool batches them: one prompt, one yes/no, one
    application. For surgical tweaks afterwards the per-page tool is
    still the right call.
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
        # would leave the user with a mix they didn't approve.
        rejection = _reject_layout_batch(draft, items)
        if rejection is not None:
            return rejection

        prompt = _build_layout_prompt(items)
        if not confirm(prompt):
            return (
                "User declined the proposed rhythm. Ask what they'd "
                "like to change, then propose again or adjust specific "
                "pages with choose_layout."
            )
        for item in items:
            draft.pages[int(item["page"]) - 1].layout = str(item["layout"])
        return f"Applied layouts to all {len(items)} pages."

    return Tool(
        name="propose_layouts",
        description=(
            "Propose the layout for EVERY page at once so the user can "
            "approve the whole rhythm with a single yes/no instead of "
            "answering per-page. Use this right after metadata is "
            "settled. For surgical tweaks afterwards, use choose_layout. "
            "Valid layouts: image-top, image-bottom, image-full, "
            "text-only. Pages without a drawing must be text-only. "
            + _RHYTHM_RULES_FOR_TOOL_DESC
            + " Since you see every page at once here, use that view "
            "to make the cadence feel varied on paper — not just in the "
            "summary table."
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


def _build_layout_prompt(items: list[dict]) -> str:
    """Render a table-ish summary of the proposed rhythm for the y/n
    prompt — the user sees every page and the reason for the choice."""
    rows = ["Proposed layouts:"]
    for item in sorted(items, key=lambda d: int(d["page"])):
        page_n = int(item["page"])
        layout = str(item["layout"])
        reason = str(item.get("reason", ""))
        rows.append(f"  Page {page_n}: {layout} — {reason}")
    rows.append("Approve this rhythm?")
    return "\n".join(rows)


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
        source_dir = Path(get_session_root()) / ".book-gen"
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
