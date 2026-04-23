# Deterministic Ingestion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move OCR + sentinel classification out of the agent tool-use loop into a pure Python ingestion step that runs between `from_pdf` and the first agent turn.

**Architecture:** New `src/ingestion.py` with `IngestReport` + `ingest_image_only_pages()`. Promote three helpers in `src/agent_tools.py` (`_call_vision_for_transcription`, `_extract_sentinel`, `_apply_sentinel_result`) to public so both the tool and the ingestion module share them. REPL calls ingestion in the load flow. Greeting loses "PROCESS THE DRAFT AUTOMATICALLY" + "BATCH THE INGESTION" blocks.

**Tech Stack:** Python 3.10+, `pytest`, `dataclasses`, existing `src.providers.llm`, existing `src.draft`.

**Spec:** `docs/superpowers/specs/2026-04-23-deterministic-ingestion-design.md`

**Branch:** `feat/deterministic-ingestion` (already checked out).

---

## File Structure

| File | Role | Create / Modify |
|---|---|---|
| `src/agent_tools.py` | Promote 3 helpers from `_private` to public (`call_vision_for_transcription`, `extract_sentinel`, `apply_sentinel_result`) so both the tool and the new module use them. | Modify |
| `src/ingestion.py` | Pure function `ingest_image_only_pages(draft, llm, console) -> IngestReport`. Orchestrates the per-page vision call + sentinel application. | Create |
| `src/repl.py` | Call `ingest_image_only_pages` after `_load_pdf` / CLI preload and before the first agent turn. Rewrite `_AGENT_GREETING_HINT` to drop the "PROCESS THE DRAFT AUTOMATICALLY" + "BATCH THE INGESTION" blocks. | Modify |
| `tests/test_ingestion.py` | Six unit tests covering the happy path, each sentinel branch, idempotency, and the NullProvider no-op. | Create |
| `tests/test_repl_load.py` | One integration test verifying auto-ingestion fires on load. | Modify |
| `tests/test_agent_greeting.py` | Forbidden-pattern regression so the deleted greeting blocks don't creep back. | Modify |
| `docs/PLAN.md` | Move the "Move ingestion out of the LLM loop entirely" entry from "Next up" → "Shipped" with this PR's number. | Modify (last task) |

---

## Chunk 1: Visibility relaxation

### Task 1: Promote 3 helpers in `src/agent_tools.py` to public

**Files:**
- Modify: `src/agent_tools.py`
- Test: `tests/test_agent_tools.py` (only if any test imports the private names)

Today these three helpers exist (find the exact lines by grep):
- `_call_vision_for_transcription` — wraps the LLM `chat()` call with vision messages.
- `_extract_sentinel` — parses `<BLANK>` / `<TEXT>` / `<MIXED>` from the reply.
- `_apply_sentinel_result` — mutates the draft page based on the sentinel.

Rename (drop the leading underscore) so `src/ingestion.py` can import them. The rename is purely a visibility change — the behaviour is identical.

- [ ] **Step 1: Grep for callers to see the impact**

```bash
grep -n "_call_vision_for_transcription\|_extract_sentinel\|_apply_sentinel_result" src/ tests/
```

Expected: all hits inside `src/agent_tools.py` and `tests/test_agent_tools.py`. If any other file already references them by the private name, update those too.

- [ ] **Step 2: Rename the three functions + all call sites**

Search-and-replace within `src/agent_tools.py` and any test files that hit them directly:
- `_call_vision_for_transcription` → `call_vision_for_transcription`
- `_extract_sentinel` → `extract_sentinel`
- `_apply_sentinel_result` → `apply_sentinel_result`

- [ ] **Step 3: Run the suite**

```
pytest
```

Expected: all 636 passing (unchanged count). Pure rename, behaviour unchanged.

- [ ] **Step 4: Commit**

```
git add src/agent_tools.py tests/
git commit -m "refactor(agent): promote vision/sentinel helpers to module-public"
```

Use the `generating-conventional-commits` skill to draft the exact message.

---

## Chunk 2: `src/ingestion.py` module

### Task 2: Scaffold the module + IngestReport

**Files:**
- Create: `src/ingestion.py`
- Test: `tests/test_ingestion.py`

- [ ] **Step 1: Write the first failing test (empty draft → empty report)**

Create `tests/test_ingestion.py`:

```python
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
```

- [ ] **Step 2: Run to confirm RED**

```
pytest tests/test_ingestion.py::test_ingest_empty_draft_returns_empty_report -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingestion'`.

- [ ] **Step 3: Create `src/ingestion.py`**

```python
"""Deterministic ingestion — runs OCR + sentinel classification on
every image-only page *before* the agent gets a turn. Pure Python;
the LLM is called directly, not through the agent's tool-use loop.
This removes the surface where earlier versions of the tool printed
a per-page y/n confirm UI that Claude / GPT kept reconstructing from
training memory regardless of greeting prompts.

Contract: idempotent. Called on every ``littlepress`` launch (fresh
load or memory-restored). Pages whose text is already populated, or
whose ``hidden`` flag is set, are skipped — a re-ingest is free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.draft import Draft


@dataclass
class IngestReport:
    """What ``ingest_image_only_pages`` did (or would have done on
    a dry run)."""

    text_pages: list[int] = field(default_factory=list)
    mixed_pages: list[int] = field(default_factory=list)
    blank_pages: list[int] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return len(self.text_pages) + len(self.mixed_pages) + len(self.blank_pages)


def ingest_image_only_pages(
    draft: Draft,
    llm_provider: Any,
    console: Any,
) -> IngestReport:
    """OCR every image-only, non-hidden page in ``draft``; apply the
    sentinel outcome; return a summary. Mutates ``draft`` in place.

    No-op for empty drafts, for drafts with no image-only pages, or
    when ``llm_provider`` is ``None`` / a ``NullProvider``.
    """
    return IngestReport()
```

- [ ] **Step 4: Run the test green**

```
pytest tests/test_ingestion.py::test_ingest_empty_draft_returns_empty_report -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/ingestion.py tests/test_ingestion.py
# generating-conventional-commits → feat(ingestion): scaffold module with IngestReport + no-op entry point
git commit
```

### Task 3: Transcribe every image-only page

**Files:**
- Modify: `src/ingestion.py`
- Test: `tests/test_ingestion.py`

- [ ] **Step 1: Write the failing test (3 pages, 2 image-only, TEXT reply)**

Append to `tests/test_ingestion.py`:

```python
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
```

- [ ] **Step 2: RED check**

```
pytest tests/test_ingestion.py::test_ingest_transcribes_every_image_only_page -v
```

Expected: FAIL — stub returns empty report without doing any work.

- [ ] **Step 3: Implement the loop**

Replace `ingest_image_only_pages` body:

```python
def ingest_image_only_pages(
    draft: Draft,
    llm_provider: Any,
    console: Any,
) -> IngestReport:
    report = IngestReport()
    if llm_provider is None or getattr(llm_provider, "name", "") == "none":
        return report

    from src.agent_tools import (
        call_vision_for_transcription,
        apply_sentinel_result,
    )

    for idx, page in enumerate(draft.pages, start=1):
        if page.hidden:
            continue
        if page.image is None:
            continue
        if page.text.strip():
            continue

        try:
            reply = call_vision_for_transcription(page, idx, llm_provider)
        except Exception as e:  # noqa: BLE001 — any vision failure is non-fatal here
            report.errors.append((idx, str(e)[:200]))
            console.print(f"[yellow]OCR page {idx}: failed — {e}[/yellow]")
            continue

        summary = apply_sentinel_result(page, reply, idx, method="vision")
        # Classify by page state, not by the human-readable summary string.
        if page.hidden:
            report.blank_pages.append(idx)
        elif page.image is None:
            report.text_pages.append(idx)
        else:
            report.mixed_pages.append(idx)
        console.print(f"[dim]OCR page {idx}/{len(draft.pages)}: {summary}[/dim]")

    return report
```

(`call_vision_for_transcription` + `apply_sentinel_result` come from Task 1's rename.)

- [ ] **Step 4: Run green**

```
pytest tests/test_ingestion.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```
git add src/ingestion.py tests/test_ingestion.py
# generating-conventional-commits → feat(ingestion): transcribe image-only pages via direct LLM call
git commit
```

### Task 4: TEXT / MIXED / BLANK sentinel branches

**Files:**
- Modify: `tests/test_ingestion.py`

The loop body already calls `apply_sentinel_result` which handles all three branches. Just need regression tests pinning each outcome.

- [ ] **Step 1: Add three tests, one per sentinel**

```python
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


def test_ingest_applies_mixed_sentinel_preserves_image_and_layout(tmp_path):
    from src.ingestion import ingest_image_only_pages

    img = _tiny_png(tmp_path / ".book-gen" / "images" / "page-01.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    llm = _ScriptedLLM(["<MIXED>\nHello plus a drawing"])

    report = ingest_image_only_pages(draft, llm, _console())

    assert draft.pages[0].text == "Hello plus a drawing"
    assert draft.pages[0].image == img
    assert draft.pages[0].layout == "image-top"
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
```

- [ ] **Step 2: Run green**

```
pytest tests/test_ingestion.py -v
```

All pass (no implementation change needed — `apply_sentinel_result` from the agent tool already handles the three branches correctly).

- [ ] **Step 3: Commit**

```
git add tests/test_ingestion.py
# generating-conventional-commits → test(ingestion): pin TEXT / MIXED / BLANK sentinel outcomes
git commit
```

### Task 5: Idempotency + NullProvider

**Files:**
- Modify: `tests/test_ingestion.py`

- [ ] **Step 1: Add two tests**

```python
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
```

- [ ] **Step 2: Run green**

```
pytest tests/test_ingestion.py -v
```

All pass — the loop body already checks `page.text.strip()` / `page.hidden` / `page.image is None` before dispatching, and the provider-name guard handles NullProvider.

- [ ] **Step 3: Commit**

```
git add tests/test_ingestion.py
# generating-conventional-commits → test(ingestion): idempotent re-run + NullProvider no-op
git commit
```

---

## Chunk 3: REPL integration

### Task 6: Wire ingestion into the REPL load flow

**Files:**
- Modify: `src/repl.py`
- Test: `tests/test_repl_load.py`

The REPL has a `_load_pdf` helper (or equivalent under a different name — grep). After `draft = draft_mod.from_pdf(...)` and before persisting / handing the draft to the agent, call `ingest_image_only_pages`.

- [ ] **Step 1: Find the load path**

```bash
grep -n "from_pdf\|_load_pdf\|set_draft" src/repl.py src/cli.py | head -20
```

- [ ] **Step 2: Write the integration test**

Append to `tests/test_repl_load.py` (file already exists; reuse `_make` / `_scripted` if present, otherwise mirror the pattern from `tests/test_review_loop.py`):

```python
def test_load_pdf_auto_ingests_image_only_pages(tmp_path):
    """End-to-end: loading an image-only PDF triggers deterministic
    ingestion before any agent turn — the agent sees a draft that's
    already been OCR'd."""
    from PIL import Image
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from rich.console import Console
    import io

    # Build a 2-page PDF where each page is just an embedded image
    # (no text layer — mirrors Samsung Notes exports).
    pdf = tmp_path / "draft.pdf"
    c = rl_canvas.Canvas(str(pdf), pagesize=A5)
    for i in range(2):
        img_path = tmp_path / f"_src_{i}.png"
        Image.new("RGB", (120, 160), (200, 200, 200)).save(img_path)
        c.drawImage(ImageReader(str(img_path)), 50, 200, width=300, height=400)
        c.showPage()
    c.save()

    # ScriptedLLM: return <TEXT> for both pages.
    class _LLM:
        name = "anthropic"
        def __init__(self):
            self.calls = 0
        def chat(self, *_a, **_kw):
            self.calls += 1
            return f"<TEXT>\nPage {self.calls} transcribed"
        def turn(self, *_a, **_kw):
            raise AssertionError("agent should not have started yet")

    from src.providers.llm import find
    from src.repl import Repl

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    llm = _LLM()
    repl = Repl(
        read_line=lambda: (_ for _ in ()).throw(EOFError),  # no interactive input
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )

    # Slash command path — simulates the user typing /load <pdf>.
    # If the REPL exposes a public load helper, call it instead; if it
    # only exposes the slash command, drive via the scripted read-loop.
    from src import draft as draft_mod
    loaded = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")
    repl.set_draft(loaded)  # triggers the same hook the CLI preload uses

    # Both image-only pages got transcribed before any agent turn.
    assert llm.calls == 2
    assert loaded.pages[0].text == "Page 1 transcribed"
    assert loaded.pages[1].text == "Page 2 transcribed"
```

Adjust the test to whatever the actual REPL public API looks like (`repl.set_draft`, `repl.load_pdf`, or whatever).

- [ ] **Step 3: Run RED**

Expected: FAIL — REPL doesn't call ingestion yet.

- [ ] **Step 4: Wire ingestion into the REPL**

In `src/repl.py`, find the spot where the draft is finalised post-load (most likely `set_draft`, `_load_pdf`, or the handler for `/load`). Add:

```python
from src.ingestion import ingest_image_only_pages

# ... inside the load handler, after:
#   self._draft = draft
# but before:
#   memory_mod.save_draft(...)
if self._llm is not None and getattr(self._llm, "name", "") != "none":
    ingest_image_only_pages(draft, self._llm, self._console)
# Persist the POST-ingestion state so re-launches don't re-OCR.
memory_mod.save_draft(self._session_root, draft)
```

Use the actual attribute names the REPL uses. If the REPL's load path already calls `save_draft`, the ingestion call goes *before* it.

- [ ] **Step 5: Run green**

```
pytest tests/test_repl_load.py -v
```

- [ ] **Step 6: Commit**

```
git add src/repl.py tests/test_repl_load.py
# generating-conventional-commits → feat(repl): auto-ingest image-only pages on load
git commit
```

---

## Chunk 4: Greeting cleanup

### Task 7: Strip the now-redundant greeting blocks

**Files:**
- Modify: `src/repl.py` (the `_AGENT_GREETING_HINT` constant)
- Test: `tests/test_agent_greeting.py`

The greeting currently instructs the agent to run the ingestion pipeline itself (old flow, with auto-apply). After Task 6, the pipeline runs *before* the agent. The greeting should reflect that: draft is pre-processed when the agent starts.

- [ ] **Step 1: Write the forbidden-pattern regression**

Append to `tests/test_agent_greeting.py`:

```python
def test_greeting_no_longer_tells_agent_to_process_the_draft_itself():
    """After the deterministic-ingestion PR, ``littlepress`` does the
    OCR + sentinel work before the agent's first turn. The greeting
    must NOT still tell the agent to run transcribe_page in a batch
    — that was the old flow and those phrases invited the LLM to
    reconstruct the pre-refactor UI from training memory."""
    from src.repl import _AGENT_GREETING_HINT

    forbidden = [
        "PROCESS THE DRAFT AUTOMATICALLY",
        "BATCH THE INGESTION",
        "For every image-only page, call transcribe_page",
        "Run the ingestion pipeline",
    ]
    for phrase in forbidden:
        assert phrase not in _AGENT_GREETING_HINT, (
            f"stale ingestion directive leaked into greeting: {phrase!r}"
        )


def test_greeting_tells_agent_the_draft_is_already_processed():
    """Conversely, the new hint should tell the agent the draft
    arrives already transcribed so it doesn't try to redo the work."""
    from src.repl import _AGENT_GREETING_HINT

    g = _AGENT_GREETING_HINT.lower()
    # A phrase that says "ingestion is done / pre-processed / already
    # transcribed" — any of these is fine.
    assert (
        "already transcribed" in g
        or "already processed" in g
        or "pre-processed" in g
        or "already been" in g
    )
```

- [ ] **Step 2: Run RED**

Expected: the "forbidden" test FAILS because the greeting currently has those blocks.

- [ ] **Step 3: Rewrite the greeting**

Open `src/repl.py`. The `_AGENT_GREETING_HINT` constant has two blocks that go:
- The `PROCESS THE DRAFT AUTOMATICALLY. Do NOT ask the user per-page confirmations ...` block.
- The `BATCH THE INGESTION. Call transcribe_page for every image-only page ...` block.

Delete both. In their place, insert a short opener:

```
"The draft arrives already transcribed — ``littlepress`` ran OCR "
"and sentinel classification (``<BLANK>`` / ``<TEXT>`` / ``<MIXED>``) "
"against every image-only page before your first turn. Blank "
"pages are already hidden. Do NOT call ``transcribe_page`` during "
"the metadata phase; the tool stays registered only so the user "
"can request a re-OCR on a specific page during the post-render "
"review turn (``page N re-OCR``).\n\n"
```

Keep `ASK ONLY FOR THINGS YOU CANNOT INFER`, `RENDER IMMEDIATELY`, `POST-RENDER REVIEW TURN`, and `PRESERVE-CHILD-VOICE` sections unchanged.

- [ ] **Step 4: Run green**

```
pytest tests/test_agent_greeting.py -v
```

- [ ] **Step 5: Commit**

```
git add src/repl.py tests/test_agent_greeting.py
# generating-conventional-commits → refactor(repl): greeting assumes pre-ingested draft
git commit
```

---

## Chunk 5: Suite + docs + PR

### Task 8: Full suite + docs sweep + PR

**Files:**
- Modify: `README.md` (one-line update: "ingestion runs automatically on load")
- Modify: `docs/PLAN.md` — move the ingestion-out-of-loop entry from "Next up" to "Shipped"

- [ ] **Step 1: Full suite**

```
pytest
```

Expected: all passing (~645, was 636 + 9 new ingestion tests + 2 greeting regression tests, minus any renames that consolidated).

- [ ] **Step 2: README update**

In the "Status" / "How it works" section, add a sentence: "When you load a PDF, Littlepress OCR's image-only pages automatically and classifies each (text / drawing + text / blank) before the agent conversation starts — no per-page approval prompts during ingestion."

- [ ] **Step 3: PLAN update**

In `docs/PLAN.md`:
- Move the "Move ingestion out of the LLM loop entirely." bullet from "Next up" → "Shipped" table as a new row (PR number filled in after `gh pr create`).
- Leave the broader "AI-only-for-judgment" principle as a follow-up (metadata collection, cover menu, back-cover default) in "Next up" or a new section — it's the next sub-project.

- [ ] **Step 4: Commit docs + push + PR**

```
git add README.md docs/PLAN.md
# generating-conventional-commits → docs: README + PLAN for deterministic ingestion
git commit
git push -u origin feat/deterministic-ingestion
gh pr create --title "feat(ingestion): run OCR + sentinel classification before the agent starts" --body "<use the spec's Problem / Contract / Scope sections>"
```

After the PR URL lands, update `docs/PLAN.md`'s Shipped row with the real PR number and push a follow-up commit.

---

## Out of scope (do not expand this plan)

- Deterministic metadata collection (title / author / series / cover menu / back-cover default) — next sub-PR.
- Batch typo-fix in Python — stays on the agent side, bounded.
- Batch layout in Python — stays on the agent side.
- Tesseract-only mode — `transcribe_page` tool still supports it for review-turn retries.
- Parallel / async per-page OCR — serial for now; revisit if a real user complains about 8-page load latency.
