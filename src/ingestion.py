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

    # Import here rather than at module top to avoid a circular
    # import if src/agent_tools.py ever grows an import back to
    # src/ingestion.py. These helpers were promoted to public in
    # the previous commit of this branch.
    from src.agent_tools import call_vision_for_transcription, apply_sentinel_result

    total = len(draft.pages)
    for idx, page in enumerate(draft.pages, start=1):
        # Skip pages that are already processed / out of scope.
        if page.hidden:
            continue
        if page.image is None:
            continue
        if page.text.strip():
            continue

        try:
            reply, error = call_vision_for_transcription(llm_provider, page.image, idx)
            if error:
                report.errors.append((idx, error[:200]))
                console.print(f"[yellow]OCR page {idx}/{total}: failed — {error}[/yellow]")
                continue
        except Exception as e:  # noqa: BLE001 — any vision failure is non-fatal
            report.errors.append((idx, str(e)[:200]))
            console.print(f"[yellow]OCR page {idx}/{total}: failed — {e}[/yellow]")
            continue

        summary = apply_sentinel_result(page, reply, idx, method="vision")
        # Classify by post-mutation page state, not by the summary
        # string — the sentinel branch is what the report cares about.
        if page.hidden:
            report.blank_pages.append(idx)
        elif page.image is None:
            report.text_pages.append(idx)
        else:
            report.mixed_pages.append(idx)
        console.print(f"[dim]OCR page {idx}/{total}: {summary}[/dim]")

    return report
