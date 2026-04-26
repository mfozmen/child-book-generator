"""End-to-end test against the user's actual Samsung Notes draft.

The user reported the same render pathologies across multiple PR
rounds — duplicate text on MIXED pages, missing illustrations,
cover overrides, colophon leaking into story pages. Each previous
PR fixed one symptom while the broader flow kept regressing because
no test exercised the full pipeline against the real input.

This test does. Loads the actual ``yavru_dinozor`` PDF, runs OCR /
colophon detection / metadata prompts / rendering with stubbed LLM
responses calibrated to the real page content, then asserts every
invariant the user has hit:

  * MIXED pages get an extracted clean drawing (no baked-in text)
    and an image-top layout — illustrations actually render.
  * The colophon page (page 5: ``YAZAR:POYRAZ RESİMLEYEN:POYRAZ``)
    is auto-hidden — doesn't leak into the story interior.
  * Blank pages (6, 7, 8) are auto-hidden.
  * Cover honours the user's deterministic choice (poster).
  * The rendered PDF text contains each story sentence at most once
    — the duplicate-text bug from the v3 round is gone.

Skipped when the fixture isn't available (the PDF is the user's
child's content; not committed to the public repo by default).
The test itself is the regression net for any future change that
might re-introduce one of these failure modes.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader
from rich.console import Console

from src.agent import AgentResponse


_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "yavru_dinozor" / "draft.pdf"


pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason=(
        f"Real fixture missing: {_FIXTURE}. The Samsung Notes PDF "
        "is the user's child's personal content and isn't committed "
        "to the public repo; this end-to-end test runs locally on "
        "the maintainer's machine where the fixture exists."
    ),
)


# OCR replies calibrated to the actual page content of the
# yavru_dinozor draft. These mimic what a real vision provider
# would return.
_OCR_REPLIES = [
    # Page 1 — title + opening, with illustration.
    "<MIXED>\nYAVRU DİNOZOR 1\n"
    "Bir gün bir yumurta çatlamış ve içinden\n"
    "yavru bir dinozor çıkmış. O dinozor yumurta dan\n"
    "çıktığında yanında bir sürü yumurta görmüş.",
    # Page 2 — eggs hatched, dinos went to forest.
    "<MIXED>\nSonra yumurtalar çatlamış ve dinozorlar ormana gitmiş.",
    # Page 3 — grew big.
    "<MIXED>\nAma o kadar büyümüş ki neredeyse bir insanın 100 katıymış.",
    # Page 4 — not aggressive like t.rex; has friend.
    "<MIXED>\nAma t.rex kadar saldırgan değilmiş.\n"
    "yanında bir tane dinozor varmış.",
    # Page 5 — colophon (treated as TEXT by vision, then auto-hidden
    # by colophon detector).
    "<TEXT>\nYAZAR:POYRAZ RESİMLEYEN:POYRAZ",
    # Pages 6-8 — trailing blanks.
    "<BLANK>",
    "<BLANK>",
    "<BLANK>",
]


_COLOPHON_REPLY = "<COLOPHON>\n5\n</COLOPHON>"


class _ScriptedLLM:
    """Stub provider that serves pre-canned chat replies in order
    and returns a single end-of-turn agent response. Mimics the
    Anthropic provider shape: ``chat()`` for OCR / colophon /
    AI-blurb work, ``turn()`` for the agent's tool-use loop."""

    def __init__(self) -> None:
        self._chat_replies = list(_OCR_REPLIES) + [
            _COLOPHON_REPLY,
            # Back-cover AI-draft reply.
            "Bir yumurtadan çatlayıp çıkan yavru dinozor, ormanda "
            "büyüyüp devasa bir etçile dönüşür — ama yalnız değildir, "
            "yanında onu destekleyen bir dostu vardır.",
        ]
        self._turn_responses = self._build_turn_responses()
        self.chat_calls: list[dict] = []
        self.turn_calls: list[dict] = []

    @staticmethod
    def _build_turn_responses() -> list[AgentResponse]:
        """The agent's job in this scenario is narrow: confirm the
        AI back-cover blurb (``set_metadata``) and call
        ``render_book``. No layout meddling — that's what the v3
        regression was about. The propose_layouts / choose_layout
        protections enforce this server-side too, but pinning the
        agent to the minimal flow makes the test deterministic."""
        return [
            # Set the back-cover blurb verbatim from the AI draft.
            AgentResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "set_metadata",
                        "input": {
                            "field": "back_cover_text",
                            "value": (
                                "Bir yumurtadan çatlayıp çıkan yavru "
                                "dinozor, ormanda büyüyüp devasa bir "
                                "etçile dönüşür — ama yalnız değildir, "
                                "yanında onu destekleyen bir dostu "
                                "vardır."
                            ),
                        },
                    }
                ],
                stop_reason="tool_use",
            ),
            # Render the book.
            AgentResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "render_book",
                        "input": {"impose": True},
                    }
                ],
                stop_reason="tool_use",
            ),
            # Final review prompt to user.
            AgentResponse(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "PDF hazır. Sayfalarda sorun varsa "
                            "numarasını yazın, yoksa ok yazın."
                        ),
                    }
                ],
                stop_reason="end_turn",
            ),
            # User says "ok" — final close.
            AgentResponse(
                content=[
                    {"type": "text", "text": "Tamam, kitap hazır!"}
                ],
                stop_reason="end_turn",
            ),
        ]

    def chat(self, messages, **kwargs):
        self.chat_calls.append({"messages": list(messages), "kwargs": dict(kwargs)})
        if not self._chat_replies:
            return ""
        return self._chat_replies.pop(0)

    def turn(self, messages, tools):
        self.turn_calls.append(
            {"messages": list(messages), "tools": [t.name for t in tools]}
        )
        if not self._turn_responses:
            return AgentResponse(
                content=[{"type": "text", "text": "(no more scripted)"}],
                stop_reason="end_turn",
            )
        return self._turn_responses.pop(0)


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _extract_text_from_pdf(pdf: Path) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)


def test_yavru_dinozor_renders_illustrations_and_no_duplicate_text(
    tmp_path, monkeypatch
):
    """The full live-render scenario the user has been hitting.
    See module docstring for what it pins."""
    monkeypatch.setenv("LITTLEPRESS_LANG", "tr")
    from src.providers.llm import find
    from src.repl import Repl

    llm = _ScriptedLLM()
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=False, width=100, no_color=True
    )

    # The metadata prompts run after ingestion (5 prompts in tr
    # mode): title, author, series y/n + volume, cover (a/b/c),
    # back-cover (a/b/c). After the agent turn, the review prompt
    # asks for issues — we reply "ok" to exit.
    repl = Repl(
        read_line=_scripted([
            f"/load {_FIXTURE}",
            "Yavru Dinozor",
            "Poyraz Özmen",
            "e",            # series? yes
            "1",            # volume
            "c",            # cover: poster
            "c",            # back-cover: AI draft
            "ok",           # review-turn exit
            "/exit",
        ]),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.run()

    assert repl.draft is not None
    pages = repl.draft.pages
    assert len(pages) == 8

    # ---- MIXED pages 1-4: extracted drawing + image-top layout ----
    for idx in range(4):
        page = pages[idx]
        assert not page.hidden, f"page {idx+1} unexpectedly hidden"
        assert page.image is not None, f"page {idx+1} lost its image"
        assert page.image.exists(), (
            f"page {idx+1} image path missing on disk: {page.image}"
        )
        # Extraction succeeded — the file is the cleaned drawing,
        # not the original full-page raster. Naming convention is
        # ``page-NN.drawing.png`` from ``_try_extract_drawing``.
        assert page.image.name.endswith(".drawing.png"), (
            f"page {idx+1} should have extracted drawing, got "
            f"{page.image.name}"
        )
        assert page.layout == "image-top", (
            f"page {idx+1} should be image-top after MIXED extraction; "
            f"got {page.layout}"
        )
        # Sanity: text was transcribed.
        assert page.text.strip(), f"page {idx+1} text empty"

    # ---- Colophon page hidden ----
    assert pages[4].hidden, (
        "page 5 (colophon credits page) should be auto-hidden"
    )

    # ---- Blank pages hidden ----
    for idx in (5, 6, 7):
        assert pages[idx].hidden, f"page {idx+1} (blank) should be hidden"

    # ---- Cover: poster (typography-only) ----
    assert repl.draft.cover_image is None, (
        "poster cover must NOT have an image attached; got "
        f"{repl.draft.cover_image}"
    )
    assert repl.draft.cover_style == "poster", (
        f"cover_style should stay poster; got {repl.draft.cover_style}"
    )

    # ---- Back-cover blurb populated ----
    assert "yavru dinozor" in repl.draft.back_cover_text.lower()

    # ---- Rendered PDF exists ----
    output_dir = tmp_path / ".book-gen" / "output"
    a5_renders = list(output_dir.glob("*.pdf"))
    assert a5_renders, f"no rendered PDF in {output_dir}"
    a5 = next(p for p in a5_renders if "_A4_booklet" not in p.name)

    # ---- Each story sentence appears at most once in the rendered
    # PDF — the duplicate-text bug from the v3 round is the whole
    # reason this test exists. ----
    rendered_text = _extract_text_from_pdf(a5)
    for phrase in (
        "Bir gün bir yumurta",
        "Sonra yumurtalar çatlamış",
        "büyümüş ki neredeyse",
        "saldırgan değilmiş",
    ):
        count = rendered_text.lower().count(phrase.lower())
        assert count <= 1, (
            f"story phrase {phrase!r} appears {count} times in the "
            f"rendered PDF — duplicate-text bug regressed. Excerpt:\n"
            f"{rendered_text[:500]!r}"
        )

    # ---- Extracted drawing is meaningfully smaller than the
    # original raster — the extraction actually cropped, not just
    # re-saved the full page. ----
    original_p1 = (tmp_path / ".book-gen" / "images" / "page-01.png")
    extracted_p1 = pages[0].image
    if original_p1.exists() and extracted_p1.exists():
        with Image.open(original_p1) as orig, Image.open(extracted_p1) as crop:
            assert crop.size[1] < orig.size[1], (
                f"extracted drawing height {crop.size[1]} not smaller "
                f"than original page height {orig.size[1]} — "
                "extraction didn't crop"
            )
