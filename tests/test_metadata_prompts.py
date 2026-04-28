"""Deterministic metadata prompts (Sub-project 2). The LLM-driven
upfront question block in the agent greeting is being replaced by
plain Python prompts that run between PDF ingestion and the agent's
first turn. These tests pin the pure-function prompt helpers; the
REPL integration tests live in ``tests/test_repl_metadata.py``.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from rich.console import Console

from src.draft import Draft


# Pin English for the existing test suite — these tests were written
# before the i18n module landed and assert against English phrasing /
# English-only y/n token acceptance. The locale-detection path runs
# in production; tests need a fixed default so they don't depend on
# the dev machine's locale (the maintainer's Windows is Turkish, so
# without the fixture each test would silently pick ``tr`` and a
# subset would fail). Tests that exercise Turkish behaviour override
# via their own ``monkeypatch.setenv("LITTLEPRESS_LANG", "tr")``.
@pytest.fixture(autouse=True)
def _force_english(monkeypatch):
    monkeypatch.setenv("LITTLEPRESS_LANG", "en")


def _console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, width=100, no_color=True)


def _scripted(lines: list[str]):
    it: Iterator[str] = iter(lines)

    def read() -> str:
        try:
            return next(it)
        except StopIteration as e:  # pragma: no cover — exhaustion means
            # a test forgot to script enough inputs; surface as EOF
            raise EOFError from e

    return read


def _empty_draft(tmp_path: Path) -> Draft:
    return Draft(source_pdf=tmp_path / "x.pdf", pages=[])


# ---------------------------------------------------------------------------
# collect_title
# ---------------------------------------------------------------------------


def test_collect_title_writes_user_string_verbatim(tmp_path):
    from src.metadata_prompts import collect_title

    draft = _empty_draft(tmp_path)
    collect_title(draft, _scripted(["The Brave Owl"]), _console())

    # Verbatim — user's string is the source of truth. No .title() call,
    # no "smart casing", no stripping of internal spaces. preserve-child-
    # voice applies (user is typing on the child's behalf).
    assert draft.title == "The Brave Owl"


def test_collect_title_preserves_non_ascii_verbatim(tmp_path):
    """The user is the source of truth on title spelling. A Turkish
    or accented title must round-trip byte-for-byte."""
    from src.metadata_prompts import collect_title

    draft = _empty_draft(tmp_path)
    collect_title(draft, _scripted(["Yavru Dinozor - 1"]), _console())

    assert draft.title == "Yavru Dinozor - 1"


def test_collect_title_strips_surrounding_whitespace(tmp_path):
    """Terminals often append a stray space after paste. Strip the
    OUTER whitespace only — internal whitespace is preserved."""
    from src.metadata_prompts import collect_title

    draft = _empty_draft(tmp_path)
    collect_title(draft, _scripted(["  The Brave Owl  "]), _console())

    assert draft.title == "The Brave Owl"


def test_collect_title_reprompts_on_empty_input(tmp_path):
    """Title is mandatory. An empty reply must re-prompt rather than
    accept an empty string — the cover renderer needs a non-empty
    title to lay out the cover correctly."""
    from src.metadata_prompts import collect_title

    draft = _empty_draft(tmp_path)
    collect_title(
        draft,
        _scripted(["", "  ", "The Brave Owl"]),
        _console(),
    )

    assert draft.title == "The Brave Owl"


# ---------------------------------------------------------------------------
# collect_author
# ---------------------------------------------------------------------------


def test_collect_author_writes_user_string_verbatim(tmp_path):
    from src.metadata_prompts import collect_author

    draft = _empty_draft(tmp_path)
    collect_author(draft, _scripted(["Ece"]), _console())

    assert draft.author == "Ece"


def test_collect_author_reprompts_on_empty_input(tmp_path):
    from src.metadata_prompts import collect_author

    draft = _empty_draft(tmp_path)
    collect_author(draft, _scripted(["", "Ece"]), _console())

    assert draft.author == "Ece"


# ---------------------------------------------------------------------------
# collect_series
# ---------------------------------------------------------------------------


def test_collect_series_no_leaves_title_alone(tmp_path):
    """Series membership is recorded INSIDE the title (e.g. 'My Book
    - 1'), not as a separate data field. A 'no' answer is a no-op on
    the draft — ``title`` stays whatever ``collect_title`` put there."""
    from src.metadata_prompts import collect_series

    draft = _empty_draft(tmp_path)
    draft.title = "The Brave Owl"
    collect_series(draft, _scripted(["n"]), _console())

    assert draft.title == "The Brave Owl"


def test_collect_series_yes_appends_volume_to_title(tmp_path):
    """On 'yes', the follow-up volume number is appended to the
    title in the ``<title> - <n>`` shape so the cover renderer
    picks it up naturally — no new data field."""
    from src.metadata_prompts import collect_series

    draft = _empty_draft(tmp_path)
    draft.title = "Yavru Dinozor"
    collect_series(draft, _scripted(["y", "1"]), _console())

    assert draft.title == "Yavru Dinozor - 1"


def test_collect_series_accepts_full_words_as_well_as_short_letters(tmp_path):
    """The series prompt should accept both the single-letter shape
    (``y`` / ``n``) and the full word (``yes`` / ``no``)."""
    from src.metadata_prompts import collect_series

    # "yes"
    draft1 = _empty_draft(tmp_path)
    draft1.title = "A"
    collect_series(draft1, _scripted(["yes", "2"]), _console())
    assert draft1.title == "A - 2"

    # "no"
    draft2 = _empty_draft(tmp_path)
    draft2.title = "B"
    collect_series(draft2, _scripted(["no"]), _console())
    assert draft2.title == "B"


def test_collect_series_rejects_non_english_tokens_and_reprompts(tmp_path):
    """CLAUDE.md forbids non-English tokens in production code (PR
    #69 review #1). The Turkish ``evet`` / ``hayır`` shortcuts were
    removed from the frozensets, so a Turkish-speaking user now has
    to type ``yes`` or ``y``. Prove the token tables don't silently
    accept the old Turkish shortcuts — a fresh re-prompt happens,
    and the flow only advances when the user supplies an English
    affirmative/negative."""
    from src.metadata_prompts import collect_series

    draft = _empty_draft(tmp_path)
    draft.title = "A"
    # ``evet`` and ``hayır`` must re-prompt (as any gibberish would);
    # the flow only settles on the final ``no``.
    collect_series(
        draft,
        _scripted(["evet", "hayır", "no"]),
        _console(),
    )
    assert draft.title == "A"


def test_collect_series_reprompts_on_unclear_answer(tmp_path):
    """Gibberish replies re-prompt rather than default silently.
    Avoids accidentally marking a book as 'not in a series' when
    the user typoed."""
    from src.metadata_prompts import collect_series

    draft = _empty_draft(tmp_path)
    draft.title = "A"
    collect_series(draft, _scripted(["maybe", "no"]), _console())

    assert draft.title == "A"


def test_collect_series_volume_reprompts_on_non_integer(tmp_path):
    """Volume must be a positive integer — anything else re-prompts."""
    from src.metadata_prompts import collect_series

    draft = _empty_draft(tmp_path)
    draft.title = "A"
    collect_series(draft, _scripted(["y", "three", "", "3"]), _console())

    assert draft.title == "A - 3"


# ---------------------------------------------------------------------------
# collect_cover_choice
# ---------------------------------------------------------------------------
# The cover prompt is a 3-way menu: (a) use an existing page drawing,
# (b) generate with AI (hands off to the agent's first turn — needs
# LLM judgment to draft the prompt from the story), (c) poster style
# (no image, typography only).
#
# Deterministic branches mutate the draft directly. The AI branch is
# the single judgment-requiring path and returns the ``"ai"`` tag so
# the caller knows to leave the cover fields unset for the agent to
# fill in.


def _draft_with_pages(tmp_path: Path, pages: list[tuple[str | None, bool]]) -> Draft:
    """Build a Draft whose pages carry (image_path_or_None, hidden)."""
    from src.draft import DraftPage

    draft_pages = [
        DraftPage(
            text="",
            image=(tmp_path / img) if img else None,
            hidden=hidden,
        )
        for img, hidden in pages
    ]
    return Draft(source_pdf=tmp_path / "x.pdf", pages=draft_pages)


def test_collect_cover_choice_poster_sets_cover_style_and_clears_image(tmp_path):
    from src.metadata_prompts import collect_cover_choice

    draft = _draft_with_pages(tmp_path, [("page-01.png", False)])
    draft.cover_image = tmp_path / "stale.png"  # stale default to prove override
    draft.cover_style = "full-bleed"

    result = collect_cover_choice(draft, _scripted(["c"]), _console())

    assert result == "poster"
    assert draft.cover_image is None
    assert draft.cover_style == "poster"


def test_collect_cover_choice_page_drawing_picks_first_available_drawing(tmp_path):
    """Option (a) is the default fast path: use the first page drawing
    still attached to the draft. Ingestion may have cleared text-only
    pages' images (no drawing left to use) and hidden blank pages, so
    we must scan past those."""
    from src.metadata_prompts import collect_cover_choice

    draft = _draft_with_pages(
        tmp_path,
        [
            (None, False),              # text-only page (image cleared)
            (None, True),                # blank hidden page
            ("page-03.png", False),     # first real drawing — pick this
            ("page-04.png", False),
        ],
    )

    result = collect_cover_choice(draft, _scripted(["a"]), _console())

    assert result == "page-drawing"
    assert draft.cover_image == tmp_path / "page-03.png"
    assert draft.cover_style == "full-bleed"


def test_collect_cover_choice_page_drawing_falls_back_to_poster_when_no_drawing(tmp_path):
    """Samsung Notes exports can be 100% text pages. Option (a) has
    nothing to reuse in that case — fall back to poster rather than
    silently picking a hidden or text-only page.

    PR #69 review finding #3: the fallback used to be silent, so the
    user who picked (a) would only discover they got poster when
    the rendered PDF opened. Assert the fallback prints a warning
    so the surprise is eliminated."""
    from io import StringIO

    from rich.console import Console as _Console

    from src.metadata_prompts import collect_cover_choice

    draft = _draft_with_pages(
        tmp_path,
        [(None, False), (None, True), (None, False)],
    )
    buf = StringIO()
    loud_console = _Console(
        file=buf, force_terminal=False, width=100, no_color=True
    )

    result = collect_cover_choice(draft, _scripted(["a"]), loud_console)

    assert result == "poster"
    assert draft.cover_image is None
    assert draft.cover_style == "poster"
    # The user must see a message explaining why they got poster
    # after picking (a). The wording can evolve; the test pins the
    # core information content.
    out = buf.getvalue().lower()
    assert "no page drawing" in out or "no drawing" in out
    assert "poster" in out


def test_collect_cover_choice_ai_leaves_draft_untouched_for_agent(tmp_path):
    """Option (b) is the only judgment-requiring branch: the agent
    needs to draft a cover prompt from the story content, confirm
    with the user, and call generate_cover_illustration. The
    deterministic helper just records the intent by returning
    ``"ai"`` — it MUST NOT touch ``draft.cover_image`` or
    ``draft.cover_style``."""
    from src.metadata_prompts import collect_cover_choice

    draft = _draft_with_pages(tmp_path, [("page-01.png", False)])
    # Caller sets defaults before calling; collect_cover_choice must
    # leave them alone on the AI branch.
    draft.cover_image = None
    draft.cover_style = "full-bleed"

    result = collect_cover_choice(draft, _scripted(["b"]), _console())

    assert result == "ai"
    assert draft.cover_image is None
    assert draft.cover_style == "full-bleed"


def test_collect_cover_choice_reprompts_on_unclear_answer(tmp_path):
    from src.metadata_prompts import collect_cover_choice

    draft = _draft_with_pages(tmp_path, [("page-01.png", False)])

    result = collect_cover_choice(draft, _scripted(["d", "huh", "c"]), _console())

    assert result == "poster"


# ---------------------------------------------------------------------------
# collect_back_cover
# ---------------------------------------------------------------------------


def test_collect_back_cover_none_leaves_text_empty(tmp_path):
    from src.metadata_prompts import collect_back_cover

    draft = _empty_draft(tmp_path)
    draft.back_cover_text = "stale"  # stale default; option (a) must clear

    result = collect_back_cover(draft, _scripted(["a"]), _console())

    assert result == "none"
    assert draft.back_cover_text == ""


def test_collect_back_cover_self_written_writes_user_string_verbatim(tmp_path):
    """The user's blurb is written verbatim (preserve-child-voice —
    they're typing on the child's behalf). Outer whitespace stripped;
    internal preserved."""
    from src.metadata_prompts import collect_back_cover

    draft = _empty_draft(tmp_path)
    result = collect_back_cover(
        draft,
        _scripted(["b", "  Yavru dinozor büyümeyi öğreniyor.  "]),
        _console(),
    )

    assert result == "self-written"
    assert draft.back_cover_text == "Yavru dinozor büyümeyi öğreniyor."


def test_collect_back_cover_ai_leaves_draft_untouched_for_agent(tmp_path):
    """Option (c) is the judgment path — agent drafts a one-line
    blurb grounded on the story's actual page text, confirms, writes
    it via set_metadata. Deterministic helper records intent only."""
    from src.metadata_prompts import collect_back_cover

    draft = _empty_draft(tmp_path)
    result = collect_back_cover(draft, _scripted(["c"]), _console())

    assert result == "ai-draft"
    assert draft.back_cover_text == ""


def test_collect_back_cover_self_written_reprompts_on_empty_blurb(tmp_path):
    """If the user picks (b) but submits empty text, they probably
    meant (a). Re-prompt the blurb until they type something or fall
    out via re-pick."""
    from src.metadata_prompts import collect_back_cover

    draft = _empty_draft(tmp_path)
    result = collect_back_cover(
        draft,
        _scripted(["b", "", "  ", "A one-line blurb."]),
        _console(),
    )

    assert result == "self-written"
    assert draft.back_cover_text == "A one-line blurb."


def test_collect_back_cover_reprompts_on_unclear_answer(tmp_path):
    from src.metadata_prompts import collect_back_cover

    draft = _empty_draft(tmp_path)
    result = collect_back_cover(draft, _scripted(["x", "a"]), _console())

    assert result == "none"


# ---------------------------------------------------------------------------
# Turkish locale — paired tests covering the same contracts in tr.
# ---------------------------------------------------------------------------
# These tests prove the warmth fix actually localises: prompt strings
# come out in Turkish, the y/n tokens accept ``evet`` / ``hayır`` /
# ``e`` / ``h`` natively, and the cover / back-cover menus produce
# Turkish menu text. The English-only y/n rejection test above stays
# in place as the en-mode regression; this is its tr counterpart.


def test_collect_title_prompts_in_turkish_when_lang_is_tr(tmp_path):
    """The Turkish prompt for the title comes out as
    ``Kitabın adı ne?`` — a full sentence, not a single English
    label. The user's typed string is still written verbatim."""
    from src.metadata_prompts import collect_title

    draft = _empty_draft(tmp_path)
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=False, width=100, no_color=True
    )
    collect_title(
        draft, _scripted(["Yavru Dinozor"]), console, lang="tr"
    )

    assert draft.title == "Yavru Dinozor"
    out = buf.getvalue()
    # Substring rather than full match — Rich may add formatting
    # markers around the bolded text.
    assert "Kitabın" in out and "adı" in out


def test_resolve_lang_normalises_unsupported_to_detected_default(monkeypatch):
    """PR #76 round-2 review #1: ``_resolve_lang`` was made
    symmetric with ``detect_lang()`` — an unsupported ``lang``
    argument (e.g. ``"fr"``) falls through to the detected default
    rather than being returned as-is. Without the fall-through, a
    caller passing an unsupported code would force every ``t()``
    lookup down the English fallback path while a quietly
    inconsistent locale tag stays visible elsewhere.

    Patches ``detect_lang`` to return ``"en"`` deterministically so
    the test isn't sensitive to the dev machine's system locale
    (the maintainer's Windows is Turkish; without the patch the
    fall-through would land on ``"tr"`` here)."""
    from src import metadata_prompts

    monkeypatch.setattr(metadata_prompts, "detect_lang", lambda: "en")

    # Unsupported codes fall through to the detected default.
    assert metadata_prompts._resolve_lang("fr") == "en"
    assert metadata_prompts._resolve_lang("klingon") == "en"
    assert metadata_prompts._resolve_lang("") == "en"
    # Supported codes pass through untouched.
    assert metadata_prompts._resolve_lang("en") == "en"
    assert metadata_prompts._resolve_lang("tr") == "tr"
    # ``None`` resolves via ``detect_lang`` directly (not fall-through).
    assert metadata_prompts._resolve_lang(None) == "en"


def test_collect_series_turkish_prompt_advertises_e_h_not_y_n(tmp_path):
    """PR #76 review #2: the Turkish series prompt used to print
    ``(y/n)`` while accepting ``evet`` / ``e`` / ``hayır`` / ``h``
    natively — a Turkish-typing user got accepted on ``evet`` even
    though the hint never told them that was a valid answer. Fix:
    Turkish prompt now reads ``(e/h)`` to match the localised token
    set."""
    from src.metadata_prompts import collect_series

    draft = _empty_draft(tmp_path)
    draft.title = "A"
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=False, width=100, no_color=True
    )
    # ``e`` = evet (yes); follow-up volume number then ends the
    # prompt cycle. The point of the test is the displayed hint,
    # not the path through the volume sub-prompt.
    collect_series(draft, _scripted(["e", "1"]), console, lang="tr")

    out = buf.getvalue()
    # Hint matches what the tr token set advertises.
    assert "(e/h)" in out
    # Sanity: the en hint shape isn't bleeding through.
    assert "(y/n)" not in out


def test_collect_series_accepts_evet_in_turkish_mode(tmp_path):
    """In Turkish mode the y/n tokens widen to include ``evet`` /
    ``e`` (yes) and ``hayır`` / ``h`` (no), matching what a
    Turkish-typing user would naturally answer. CLAUDE.md
    compliance is preserved because these tokens live behind the
    ``lang == "tr"`` gate in a structured i18n module — not as
    scattered Turkish leaks in English flows."""
    from src.metadata_prompts import collect_series

    draft = _empty_draft(tmp_path)
    draft.title = "A"
    collect_series(
        draft, _scripted(["evet", "1"]), _console(), lang="tr"
    )
    assert draft.title == "A - 1"

    # And the negative side.
    draft2 = _empty_draft(tmp_path)
    draft2.title = "B"
    collect_series(draft2, _scripted(["hayır"]), _console(), lang="tr")
    assert draft2.title == "B"


def test_collect_cover_choice_menu_renders_in_turkish(tmp_path):
    """The cover menu renders Turkish option text — full sentences,
    not bare ``(a)/(b)/(c)`` letters."""
    from src.metadata_prompts import collect_cover_choice

    draft = _draft_with_pages(tmp_path, [("page-01.png", False)])
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=False, width=100, no_color=True
    )
    collect_cover_choice(draft, _scripted(["c"]), console, lang="tr")

    out = buf.getvalue()
    assert "Kapak" in out
    # A descriptive Turkish snippet from the menu must be present.
    assert "afiş" in out or "yapay zeka" in out


def test_collect_back_cover_self_written_prompts_turkish(tmp_path):
    """Back-cover self-written branch in Turkish — both the menu and
    the inner ``write the blurb`` prompt must localise."""
    from src.metadata_prompts import collect_back_cover

    draft = _empty_draft(tmp_path)
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=False, width=100, no_color=True
    )
    result = collect_back_cover(
        draft,
        _scripted(["b", "Bir dinozorun cesaret hikayesi."]),
        console,
        lang="tr",
    )

    assert result == "self-written"
    assert draft.back_cover_text == "Bir dinozorun cesaret hikayesi."
    out = buf.getvalue()
    assert "Arka kapak" in out


def test_collect_metadata_orchestrator_uses_one_language_throughout(tmp_path):
    """The orchestrator resolves the language ONCE and passes it
    down to every helper — the user must never see English and
    Turkish prompts mixed in a single session."""
    from src.metadata_prompts import collect_metadata

    draft = _draft_with_pages(tmp_path, [("page-01.png", False)])
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=False, width=100, no_color=True
    )

    collect_metadata(
        draft,
        _scripted(["Yavru Dinozor", "Ece", "n", "c", "a"]),
        console,
        lang="tr",
    )

    out = buf.getvalue()
    # Every Turkish prompt label appears.
    assert "Kitabın" in out
    assert "Yazar" in out
    assert "seri" in out.lower()  # "serinin" / "serisi"
    assert "Kapak" in out
    assert "kapak yazısı" in out.lower() or "Arka kapak" in out
    # And no English label leaked through (sanity — uses unique
    # English tokens that don't accidentally match Turkish).
    assert "What's the title" not in out
    assert "Who's the author" not in out


# ---------------------------------------------------------------------------
# collect_metadata — orchestrator
# ---------------------------------------------------------------------------
# The orchestrator runs the five prompts in their canonical order and
# returns the two AI-branch tags the REPL needs to decide whether to
# hand off to the agent's first turn for AI cover / AI back-cover
# work. Title / author / series / poster / page-drawing cover / none
# / self-written blurb are all applied deterministically by the
# individual helpers; only AI branches defer.


def test_collect_metadata_runs_all_five_prompts_in_order(tmp_path):
    from src.metadata_prompts import MetadataChoices, collect_metadata

    draft = _draft_with_pages(tmp_path, [("page-01.png", False)])

    choices = collect_metadata(
        draft,
        _scripted([
            "The Brave Owl",  # title
            "Ece",             # author
            "n",               # not a series
            "a",               # cover: page-drawing
            "a",               # back-cover: none
        ]),
        _console(),
    )

    assert isinstance(choices, MetadataChoices)
    assert choices.cover == "page-drawing"
    assert choices.back_cover == "none"
    # Deterministic branches mutated the draft.
    assert draft.title == "The Brave Owl"
    assert draft.author == "Ece"
    assert draft.cover_image == tmp_path / "page-01.png"
    assert draft.cover_style == "full-bleed"
    assert draft.back_cover_text == ""


def test_collect_metadata_returns_ai_flags_when_ai_branches_chosen(tmp_path):
    """When the user picks AI for cover and back-cover, the
    orchestrator returns the branch tags but does NOT mutate the
    cover or back-cover fields — the agent's first turn handles
    those (drafting a prompt from story content is the judgment
    part that warrants the LLM)."""
    from src.metadata_prompts import collect_metadata

    draft = _draft_with_pages(tmp_path, [("page-01.png", False)])

    choices = collect_metadata(
        draft,
        _scripted([
            "Yavru Dinozor",   # title
            "Ece",              # author
            "y", "1",           # series + volume → title becomes "Yavru Dinozor - 1"
            "b",                # cover: ai
            "c",                # back-cover: ai-draft
        ]),
        _console(),
    )

    assert choices.cover == "ai"
    assert choices.back_cover == "ai-draft"
    # Series+volume was applied.
    assert draft.title == "Yavru Dinozor - 1"
    # AI branches left cover and back-cover untouched.
    assert draft.cover_image is None
    assert draft.back_cover_text == ""


def test_collect_metadata_strips_duplicate_title_header_from_first_page(tmp_path):
    """Reported 2026-04-28: the cover renders the user-typed title;
    the first interior story page also begins with a near-identical
    header from OCR (the child wrote the title at the top of the
    physical page). Result: title appears twice. After
    ``collect_metadata`` finishes — title is now known and the
    series-volume suffix has been applied — a title-header strip
    pass should drop the duplicate from the first non-hidden page.
    Casefold + diacritic-fold + sequence similarity covers the
    typed-vs-OCR'd spelling drift (typed ``Dinazor`` vs OCR'd
    ``DİNOZOR``)."""
    from src.draft import DraftPage
    from src.metadata_prompts import collect_metadata

    # First-page text mimics the OCR result for the yavru_dinozor
    # input: a header line that the child wrote at the top of the
    # page, captured by the vision pass.
    first = DraftPage(
        text="YAVRU DİNOZOR 1\nBir gün bir yumurta çatlamış...",
        image=None,
        layout="text-only",
    )
    second = DraftPage(text="Story continues.", image=None, layout="text-only")
    draft = Draft(source_pdf=tmp_path / "x.pdf", pages=[first, second])

    collect_metadata(
        draft,
        _scripted([
            "Yavru Dinazor",   # title
            "Ece",              # author
            "y", "1",           # series + volume → title becomes "Yavru Dinazor - 1"
            "c",                # cover: poster (no follow-up prompts)
            "a",                # back-cover: none
        ]),
        _console(),
    )

    # Sanity: title got the volume suffix.
    assert draft.title == "Yavru Dinazor - 1"
    # Strip ran: first-page header is gone, body text remains.
    assert draft.pages[0].text == "Bir gün bir yumurta çatlamış..."
    # Second page is untouched.
    assert draft.pages[1].text == "Story continues."
