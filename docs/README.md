# docs/

Internal planning notes. Each task is a single Markdown file. **When a task ships, delete the file.** The set of files in this directory is the set of open work.

Naming: `p<phase>-<nn>-<slug>.md`.

## Project shape (post-pivot, 2026-04-13)

The project is an **AI-first interactive CLI** — a Claude-Code-style REPL for turning a child's PDF draft into a printed picture book.

```
$ pipx run child-book-generator
> Hi! Which model shall we use?
  1) Claude  2) GPT  3) Gemini  4) Ollama (local)
> 1
> API key: ****
> Drop a PDF or type /help
> draft.pdf
[reads 8 pages ...]
> Page 2 has a typo: "dragn" → "dragon"? (y/n/show)
> y
> Page 3 has no drawing. Generate illustration? (y/n/skip)
...
> output/my-book.pdf ready ✓
```

## Phases

- **Phase 0** — Packaging & one-command launch (`pipx run` UX).
- **Phase 1** — REPL shell + provider selection + session state.
- **Phase 2** — Tool suite: wrap existing code (PDF ingest, schema, render, imposition) as agent-callable tools; wire agent loop.
- **Phase 3** — Illustration generation (per-page & cover, opt-in per item).
- **Phase 4** — OCR tool (Tesseract + vision LLM fallback).
- **Phase 5** — Layout assistance tool (agent calls `select-page-layout` skill logic).

Phases are roughly sequential but some work within a phase can parallelize. Don't start a phase before the previous one renders an end-to-end slice.

## Guardrails (apply at every phase)

- **`preserve-child-voice`** is enforced by tool design, not by prompt trust. The LLM never gets a tool that rewrites page text freely — only narrow typo/OCR-fix proposal tools with user confirmation.
- **Provider-agnostic.** Every LLM / image / OCR provider lives behind an adapter. Adding a provider = one file.
- **Nothing secret at rest.** API keys live in session state only, never committed. `.book-gen/` is gitignored.

User-facing docs live in root `README.md`.
