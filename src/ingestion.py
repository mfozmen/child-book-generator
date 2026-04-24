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
from src.providers.llm import NullProvider


@dataclass
class IngestReport:
    """What ``ingest_image_only_pages`` did."""

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

    No-op when ``llm_provider`` is ``None`` or a ``NullProvider``
    instance; the slash-command transcribe path still handles
    offline sessions.
    """
    report = IngestReport()
    if llm_provider is None or isinstance(llm_provider, NullProvider):
        return report

    total = len(draft.pages)
    for idx, page in enumerate(draft.pages, start=1):
        if _should_skip_page(page):
            continue
        _ocr_one_page(page, idx, total, llm_provider, console, report)
    return report


def _should_skip_page(page: Any) -> bool:
    """Already-processed / out-of-scope pages: hidden, no image
    attached, or text already populated (idempotent re-ingest)."""
    return page.hidden or page.image is None or bool(page.text.strip())


def _ocr_one_page(
    page: Any,
    idx: int,
    total: int,
    llm_provider: Any,
    console: Any,
    report: IngestReport,
) -> None:
    """Run the vision call on one page, apply the sentinel outcome,
    classify the result into the report. Any vision failure is
    recorded as a non-fatal error and the page is left untouched."""
    # Late import so ``src/agent_tools.py`` can freely import back
    # from ``src/ingestion.py`` in the future without a cycle.
    # ``_vision_reply_or_record_error`` does its own late import of
    # ``call_vision_for_transcription``; this one only needs
    # ``apply_sentinel_result``.
    from src.agent_tools import apply_sentinel_result

    reply = _vision_reply_or_record_error(
        llm_provider, page.image, idx, total, console, report
    )
    if reply is None:
        return

    summary = apply_sentinel_result(page, reply, idx, method="vision")
    _classify_outcome(page, idx, report)
    console.print(f"[dim]OCR page {idx}/{total}: {summary}[/dim]")


def _vision_reply_or_record_error(
    llm_provider: Any,
    image_path: Any,
    idx: int,
    total: int,
    console: Any,
    report: IngestReport,
) -> str | None:
    """Call vision; return the reply on success, ``None`` on failure
    (both the ``(reply, error)`` tuple and raised exceptions are
    treated as failure and appended to ``report.errors``)."""
    from src.agent_tools import call_vision_for_transcription

    try:
        reply, error = call_vision_for_transcription(llm_provider, image_path, idx)
    except Exception as e:  # noqa: BLE001 — any vision failure is non-fatal
        _record_failure(str(e), idx, total, console, report)
        return None
    if error:
        _record_failure(error, idx, total, console, report)
        return None
    return reply


def _record_failure(
    error: str, idx: int, total: int, console: Any, report: IngestReport
) -> None:
    report.errors.append((idx, error[:200]))
    console.print(f"[yellow]OCR page {idx}/{total}: failed — {error}[/yellow]")


def _classify_outcome(page: Any, idx: int, report: IngestReport) -> None:
    """Classify by post-mutation page state, not by the summary
    string — the sentinel branch is what the report cares about."""
    if page.hidden:
        report.blank_pages.append(idx)
    elif page.image is None:
        report.text_pages.append(idx)
    else:
        report.mixed_pages.append(idx)
