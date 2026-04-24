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

from rich.console import Console

from src.draft import Draft


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


def test_collect_series_accepts_natural_language_affirmative(tmp_path):
    """The series prompt should accept common yes/no shapes, not
    just 'y' / 'n'. Users type full words, and Turkish speakers type
    'evet' / 'hayır'."""
    from src.metadata_prompts import collect_series

    # "yes"
    draft1 = _empty_draft(tmp_path)
    draft1.title = "A"
    collect_series(draft1, _scripted(["yes", "2"]), _console())
    assert draft1.title == "A - 2"

    # "evet" (Turkish yes)
    draft2 = _empty_draft(tmp_path)
    draft2.title = "B"
    collect_series(draft2, _scripted(["evet", "3"]), _console())
    assert draft2.title == "B - 3"

    # "hayır" (Turkish no)
    draft3 = _empty_draft(tmp_path)
    draft3.title = "C"
    collect_series(draft3, _scripted(["hayır"]), _console())
    assert draft3.title == "C"


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
