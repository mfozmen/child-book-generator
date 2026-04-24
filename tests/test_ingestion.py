"""Deterministic ingestion — OCR + sentinel classification runs
between ``from_pdf`` and the first agent turn. The LLM does the
vision work but from a pure Python caller; no agent tool-use loop,
no chance for the model to reconstruct the old confirm UI from
training memory.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from rich.console import Console

from src.draft import Draft, DraftPage


def _console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, width=100, no_color=True)


def _tiny_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 40), (10, 20, 30)).save(path)
    return path


class _ScriptedLLM:
    """Pops the next canned reply on each ``chat`` call. Mirrors the
    shape used by ``tests/test_agent_tools.py`` and
    ``tests/test_review_loop.py``."""

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), "kwargs": dict(kwargs)})
        return self._replies.pop(0)


def test_ingest_empty_draft_returns_empty_report(tmp_path):
    from src.ingestion import ingest_image_only_pages, IngestReport

    draft = Draft(source_pdf=tmp_path / "x.pdf", pages=[])
    llm = _ScriptedLLM([])

    report = ingest_image_only_pages(draft, llm, _console())

    assert isinstance(report, IngestReport)
    assert report.text_pages == []
    assert report.mixed_pages == []
    assert report.blank_pages == []
    assert report.errors == []
    assert llm.calls == []


def test_ingest_transcribes_every_image_only_page(tmp_path):
    """3 pages: #1 has text already (skipped), #2+#3 are image-only
    (transcribed). Scripted LLM replies ``<TEXT>\\n...`` for both."""
    from src.ingestion import ingest_image_only_pages

    img2 = _tiny_png(tmp_path / ".book-gen" / "images" / "page-02.png")
    img3 = _tiny_png(tmp_path / ".book-gen" / "images" / "page-03.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[
            DraftPage(text="already has text", image=None),
            DraftPage(text="", image=img2),
            DraftPage(text="", image=img3),
        ],
    )
    llm = _ScriptedLLM(["<TEXT>\nPage two text", "<TEXT>\nPage three text"])

    report = ingest_image_only_pages(draft, llm, _console())

    # Only the two image-only pages triggered llm.chat.
    assert len(llm.calls) == 2
    assert draft.pages[0].text == "already has text"  # untouched
    assert draft.pages[1].text == "Page two text"
    assert draft.pages[2].text == "Page three text"
    assert report.text_pages == [2, 3]
    assert report.total_processed == 2


def test_ingest_applies_text_sentinel_clears_image_and_sets_text_only(tmp_path):
    from src.ingestion import ingest_image_only_pages

    img = _tiny_png(tmp_path / ".book-gen" / "images" / "page-01.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    llm = _ScriptedLLM(["<TEXT>\nHello"])

    report = ingest_image_only_pages(draft, llm, _console())

    assert draft.pages[0].text == "Hello"
    assert draft.pages[0].image is None
    assert draft.pages[0].layout == "text-only"
    assert report.text_pages == [1]


def test_ingest_applies_mixed_sentinel_defaults_to_text_only_preserves_image(tmp_path):
    """Regression for the duplicate-text bug surfaced in Yavru Dinozor v3:
    when vision classifies a page as <MIXED> (text + separate drawing),
    the draft keeps page.image (so the user can opt back into the
    drawing via choose_layout in the review turn) BUT sets layout to
    ``text-only`` so the renderer doesn't print both the image (with
    handwritten text baked in) and the transcription below. Vision
    misclassifies a lot of Samsung-Notes handwriting + margin doodles
    as MIXED, so the safe default is text-only and the user explicitly
    opts in when they want the drawing drawn."""
    from src.ingestion import ingest_image_only_pages

    img = _tiny_png(tmp_path / ".book-gen" / "images" / "page-01.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    llm = _ScriptedLLM(["<MIXED>\nHello plus a drawing"])

    report = ingest_image_only_pages(draft, llm, _console())

    assert draft.pages[0].text == "Hello plus a drawing"
    # Image preserved so ``choose_layout(page=1, layout="image-top")``
    # in the review turn can opt the drawing back in without needing
    # a re-OCR.
    assert draft.pages[0].image == img
    # But layout is forced to text-only as the safe default; the
    # render pipeline respects layout=text-only even when image is
    # attached (``src/pages.py::draw_page``).
    assert draft.pages[0].layout == "text-only"
    assert report.mixed_pages == [1]


def test_ingest_applies_blank_sentinel_hides_page(tmp_path):
    from src.ingestion import ingest_image_only_pages

    img = _tiny_png(tmp_path / ".book-gen" / "images" / "page-01.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img)],
    )
    llm = _ScriptedLLM(["<BLANK>"])

    report = ingest_image_only_pages(draft, llm, _console())

    assert draft.pages[0].hidden is True
    assert draft.pages[0].text == ""
    assert report.blank_pages == [1]


def test_ingest_is_idempotent_on_already_processed_pages(tmp_path):
    """Re-running ingestion on an already-transcribed draft must not
    re-call the LLM (already-text pages are skipped; this matters
    when the user reloads a memory-restored draft)."""
    from src.ingestion import ingest_image_only_pages

    img = _tiny_png(tmp_path / ".book-gen" / "images" / "page-01.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img)],
    )
    llm = _ScriptedLLM(["<TEXT>\nHello", "<TEXT>\nShould-not-fire"])

    ingest_image_only_pages(draft, llm, _console())
    assert len(llm.calls) == 1

    # Second run: page.text is already populated → skipped; image is
    # already cleared → page is no longer image-only anyway.
    report2 = ingest_image_only_pages(draft, llm, _console())
    assert len(llm.calls) == 1  # no new call
    assert report2.total_processed == 0


def test_ingest_no_op_on_null_provider(tmp_path):
    """Offline / NullProvider session: ingestion silently does nothing,
    leaving the draft as-is. The manual transcribe_page slash-command
    path still exists for these users."""
    from src.ingestion import ingest_image_only_pages
    from src.providers.llm import NullProvider

    img = _tiny_png(tmp_path / ".book-gen" / "images" / "page-01.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )

    report = ingest_image_only_pages(draft, NullProvider(), _console())

    assert report.total_processed == 0
    assert draft.pages[0].text == ""
    assert draft.pages[0].image == img  # untouched
    assert draft.pages[0].layout == "image-top"
    # PR #65 #2 regression: ``report.errors`` must also be empty.
    # The original guard used ``getattr(llm_provider, "name", "")
    # == "none"`` which silently returned False for NullProvider
    # (it has no ``.name`` attribute), so execution fell through
    # into the loop, called ``chat()`` → raised NotImplementedError,
    # got caught in the except block, and populated ``errors``.
    # The fixed guard (``isinstance(..., NullProvider)``) short-
    # circuits before the loop, so ``errors`` stays empty.
    assert report.errors == [], (
        f"NullProvider path must short-circuit before the vision "
        f"call; errors leaking in means the guard regressed: "
        f"{report.errors!r}"
    )
