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
        # Validate style first so a bad value doesn't half-commit the
        # cover state.
        if style is not None and style not in VALID_COVER_STYLES:
            return (
                f"Invalid style '{style}'. Valid styles: "
                f"{sorted(VALID_COVER_STYLES)}."
            )
        # If ``page`` was provided, validate it regardless of style —
        # an out-of-range number is a mistake whether we use it or
        # not. Silent acceptance would hide typos that matter the
        # moment the agent switches away from poster.
        page_n_raw = input_.get("page")
        if page_n_raw is not None:
            page_n = int(page_n_raw)
            if page_n < 1 or page_n > len(draft.pages):
                return (
                    f"Page {page_n} is out of range — the draft has "
                    f"{len(draft.pages)} pages."
                )

        if style == "poster":
            # Type-only template — no drawing needed. Keep the existing
            # cover_image alone so a previous full-bleed choice isn't
            # silently discarded if the agent flips back later.
            draft.cover_style = "poster"
            msg = "Cover set to 'poster' style (type-only — no drawing used)."
            if page_n_raw is not None:
                msg += f" (The 'page' argument was ignored for this style.)"
            return msg

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

    return Tool(
        name="set_cover",
        description=(
            "Pick the book's cover. ``page`` names which page's drawing "
            "to use as the cover image (required unless style='poster'). "
            "``style`` optionally picks the cover template: 'full-bleed' "
            "(drawing covers the page, title on a translucent band), "
            "'framed' (title at the top, letterboxed drawing below), "
            "or 'poster' (type-only cover, no drawing — for books whose "
            "child-author didn't make a cover illustration). Defaults "
            "to 'full-bleed' when omitted."
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
            f"(is it open in a PDF viewer? close it and copy "
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
                f"propose_layouts expects one entry per page "
                f"({len(draft.pages)} needed, got {len(items)}). This "
                "tool is for the full rhythm — use choose_layout for "
                "a partial change."
            )
        # Validate every proposed layout first. Partial application
        # would leave the user with a mix they didn't approve.
        rejection = _reject_layout_batch(draft, items)
        if rejection is not None:
            return rejection

        prompt = _build_layout_prompt(draft, items)
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


def _build_layout_prompt(draft: Draft, items: list[dict]) -> str:
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
