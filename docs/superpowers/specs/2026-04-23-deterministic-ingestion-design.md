# Deterministic ingestion — design

**Status:** approved 2026-04-23, moving to implementation plan.
**Branch:** `feat/deterministic-ingestion`.
**Follows from:** `docs/PLAN.md`'s "Move ingestion out of the LLM loop entirely" entry. First of multiple sub-project PRs.

## Problem

Two successive Yavru Dinozor test sessions (v1 2026-04-22 pre-review-based-gate, v2 2026-04-23 post-v1.11.3) each showed the agent re-constructing the pre-refactor OCR confirm UI during ingestion — verbatim `Apply this OCR transcription to page 1? ... Approve? (y/n) ... keep_image=True branch` — even though none of that text exists in any `.py` file on `main`. The diagnostic one-liner confirmed the user's editable install loads current code (`transcribe_page_tool` has no `confirm`, no `keep_image`; greeting contains no `keep_image` literal); the behaviour is Claude / GPT reconstructing the old UI from training data. Prompt-level fixes (PR #60 greeting rewrite, PR #61 forbidden-pattern list, PR #62 tool-response pruning, PR #63 wording unification, PR #64 series-question restore) all hit the same ceiling: the LLM keeps picking up the old pattern mid-conversation.

The only fix that removes the ability is removing the LLM from the loop.

## New contract

> **Deterministic Python runs ingestion. The LLM does not speak until ingestion is complete.**

When `littlepress` loads a PDF:
1. `pdf_ingest` extracts text + per-page images (unchanged).
2. The REPL iterates pages flagged image-only (image present, no extractable text, not hidden) and calls the vision OCR path *directly in Python* — no agent turn, no tool-use loop.
3. Each page's reply is classified via the existing three-sentinel parser (`<BLANK>` / `<TEXT>` / `<MIXED>`) and the sentinel outcome is applied to the draft (auto-hide / clear image + set text-only / keep image).
4. A single-line console summary reports what happened.
5. Then — and only then — the agent is handed the draft and starts its greeting.

The LLM's training-memory reconstruction of the old OCR confirm UI becomes irrelevant because the LLM never gets a turn during ingestion.

This is the first concrete application of the broader "AI only for judgment / creativity" principle recorded in `docs/PLAN.md`. Subsequent PRs will extend the same principle to metadata collection (title / author / series / cover / back-cover default → deterministic prompts) and, optionally, review-turn mechanics.

## Scope

**In scope for this PR:**
- New `src/ingestion.py` module with a pure function `ingest_image_only_pages(draft, llm_provider, console) -> IngestReport`.
- REPL hook: after `draft = from_pdf(pdf)`, before the first agent turn, call `ingest_image_only_pages`.
- Make the vision-OCR + sentinel-apply helpers currently inside `transcribe_page_tool`'s closure (`_call_vision_for_transcription`, `_apply_sentinel_result`, `_extract_sentinel`) reachable from outside the tool factory without breaking the tool.
- Agent greeting: remove the "PROCESS THE DRAFT AUTOMATICALLY" + "BATCH THE INGESTION" blocks (work is already done when the agent starts); keep metadata, render, and review-turn sections.
- `transcribe_page` agent tool **stays registered** because the post-render review turn can ask for a re-OCR on a specific page (e.g. "page 3 re-OCR with Tesseract").

**Out of scope (future PRs):**
- Deterministic metadata collection (title/author/series/cover menu/back-cover default).
- Typo-fix pass in the deterministic layer (the bounded `propose_typo_fix` stays on the agent side).
- Layout-batch in the deterministic layer (the bounded `propose_layouts` stays on the agent side).
- Review-turn restructuring.

## Module surface

### `src/ingestion.py` — new file

```python
from dataclasses import dataclass, field
from pathlib import Path
from src.draft import Draft

@dataclass
class IngestReport:
    text_pages: list[int] = field(default_factory=list)    # <TEXT> outcomes
    mixed_pages: list[int] = field(default_factory=list)   # <MIXED> outcomes
    blank_pages: list[int] = field(default_factory=list)   # <BLANK> → hidden
    errors: list[tuple[int, str]] = field(default_factory=list)  # page, reason


def ingest_image_only_pages(
    draft: Draft,
    llm_provider,           # src.providers.llm.LLMProvider | None
    console,                # rich.console.Console
) -> IngestReport:
    """OCR every image-only, non-hidden page in ``draft`` through the
    vision path and apply the sentinel outcome. Pure — mutates draft
    in place, returns an IngestReport for the caller to summarise.

    No-op if ``llm_provider`` is None or ``NullProvider`` (offline
    session: the slash-command path still handles transcription
    manually). No-op if the draft has no image-only pages.
    """
```

- Idempotent: a page whose `text` is non-empty or whose `hidden` is True is skipped, so re-loading an already-ingested draft is free.
- Failure isolation: a vision-API error on page N is recorded in `IngestReport.errors`, other pages continue. The console summary surfaces the failure count; the agent sees partial ingestion and can decide what to do (most likely: warn the user, suggest `transcribe_page` retry in the review turn).

### `src/agent_tools.py` — visibility relaxation

Three helpers currently live inside `transcribe_page_tool`'s closure or as module-private functions:
- `_call_vision_for_transcription(page, page_n, llm, method="vision")` — builds vision messages, calls `llm.chat`, returns raw reply.
- `_extract_sentinel(reply) -> (sentinel, body)` — normalises sentinel detection.
- `_apply_sentinel_result(page, reply, page_n, method) -> str` — parses reply, mutates page, returns human-readable summary.

They're already pure / side-effect-local. Promote them from `_private` to module-public (drop the leading underscore on the two that `ingestion.py` needs to call) or, if we prefer to keep the underscores, expose them via a small module-level namespace object. Prefer the rename — there's no real "private" guarantee in Python and the ingestion module is a legitimate second consumer.

No behaviour change; no test changes on the tool side; only the import path shifts.

### `src/repl.py` — two spots

1. **Load hook.** After `repl._draft = draft` is set (both CLI preload and `/load` slash command), call `ingest_image_only_pages(draft, repl._llm, repl._console)` and `memory_mod.save_draft(root, draft)` so the post-ingestion state persists across re-launches.

2. **Greeting hint rewrite.** Strip the `PROCESS THE DRAFT AUTOMATICALLY` + `BATCH THE INGESTION` blocks (draft is already processed when the agent starts). Open with a one-liner confirming the fact: *"The PDF has already been transcribed and classified; blank pages are hidden. You start with a draft ready for metadata + render."* Keep the `ASK ONLY FOR THINGS YOU CANNOT INFER` section untouched (that's still in scope for the agent). Keep the `POST-RENDER REVIEW TURN` section untouched.

## Data flow

```
littlepress draft.pdf
   │
   ▼
draft_mod.from_pdf(pdf)
   ├─► page.text from pdf_ingest.extract_pages
   └─► page.image from pdf_ingest.extract_images
   │
   ▼
ingest_image_only_pages(draft, llm, console)  ◄── NEW deterministic step
   │
   │   For each image-only page:
   │     reply = llm.chat(vision_messages)
   │     sentinel, body = _extract_sentinel(reply)
   │     _apply_sentinel_result(page, reply, page_n, "vision")
   │
   ▼
memory.save_draft(root, draft)   ◄── persist post-ingestion state
   │
   ▼
agent greet + ask for metadata (title/author/series/cover/back-cover)
   │
   ▼
render_book
   │
   ▼
post-render review turn
```

## Testing

**New `tests/test_ingestion.py`:** six tests, all against a fixture `Draft` plus a scripted LLM (same `_ScriptedLLM` harness used in `tests/test_review_loop.py`):

1. `test_ingest_transcribes_every_image_only_page` — 3 pages (2 image-only + 1 plain-text), `<TEXT>` replies, assert `llm.chat` called twice, both image-only pages get text.
2. `test_ingest_applies_text_sentinel_clears_image_and_sets_text_only` — verify the TEXT branch mutates `page.image = None` + `page.layout = "text-only"`.
3. `test_ingest_applies_mixed_sentinel_keeps_image` — verify the MIXED branch writes `page.text` but leaves `image` + `layout` intact.
4. `test_ingest_applies_blank_sentinel_hides_page` — verify BLANK sets `page.hidden = True` and leaves `page.text` empty.
5. `test_ingest_skips_pages_already_processed` — two runs on the same draft: second call is a no-op, `llm.chat` NOT called again (idempotent).
6. `test_ingest_no_op_on_null_provider` — passing `NullProvider()` (or `None`) returns an empty report and leaves the draft unchanged.

**`tests/test_repl_load.py` (existing file):** one new scripted integration test that loads a multi-page image-only PDF fixture and asserts the draft's text is populated *before* any agent call happens.

**`tests/test_agent_greeting.py`:** a forbidden-pattern test that pins the absence of "PROCESS THE DRAFT AUTOMATICALLY" and "BATCH THE INGESTION" blocks in the greeting — these were the instructions that told the agent to re-do ingestion through tool calls.

## Risks and mitigations

- **Vision latency on load.** Eight page OCRs at ~3s each = 24s at load time. Before the refactor the same work happened during agent conversation, so it was spread out. Now it's upfront. Mitigation: console progress line per page (`OCR page 3/8 ...`) so the user sees activity; on failures continue and surface in the summary. Acceptable trade for the UX gain.
- **Partial failures.** One vision call out of eight 500s. The draft is left half-ingested. `IngestReport.errors` records page 5 failure; the agent's greeting gets a note ("page 5 couldn't be OCR'd automatically; ask the user after metadata is set"). The slash-command fallback (`/load`) + direct agent `transcribe_page` tool call remain available.
- **Memory contract.** Schema v2 already persists `hidden` and the post-ingest state is saved to `draft.json`, so re-launches don't re-run the OCR. No schema change.
- **Offline / NullProvider users.** They relied on the agent's slash-command escape hatch to transcribe manually. That path stays. Ingestion no-ops; the agent greeting still mentions the manual path.
- **Vision model picks wrong sentinel on a real page.** E.g. the Samsung Notes scan should have been `<MIXED>` but vision replies `<TEXT>`, and the image gets cleared. Recovery path: the review turn's `restore_page(N)` re-attaches the original drawing. The review-turn instruction already covers this; no new surface needed.

## Out of scope (do not expand this spec)

- Deterministic metadata collection → next PR.
- Batch typo-fix in Python → `propose_typo_fix` stays on the agent side; bounded, silent.
- Batch layout in Python → `propose_layouts` stays on the agent side.
- Tesseract-only ingestion mode → `transcribe_page` agent tool still supports `method="tesseract"`; the deterministic ingestor uses `method="vision"` only.
- Parallelising the per-page OCR calls → serial for now (reasoning: clearer console progress, simpler error isolation; Python `asyncio` can come back if a real user complains about latency).
