# Agent-first pivot — plan (2026-04-14)

The slash-command era got too feature-heavy. Pivot to an **agent-driven** CLI: the user points at a PDF, a model walks the conversation, the book comes out the other side. The goal is "drag-and-drop book" — fast, simple, smart, language-agnostic.

## UX target

```
$ child-book-generator draft.pdf
[agent reads draft]
Hi! I see 8 pages, 6 have drawings. What's the book's title?
> The Brave Owl
Author?
> Yusuf (age 7)
Page 3's "dragn" — I'd correct this to "dragon". OK?
> yes
Cover: use page 1's drawing?
> yes
[renders]
Done: output/the-brave-owl.pdf (+ A4 booklet for printing)
```

The agent **replies in whatever language the user types in**. No language toggle.

Any provider with tool-use support can drive the conversation. Claude is the default because it's already wired, but the `LLMProvider` protocol and factory keep OpenAI / Gemini / Ollama one adapter away.

## PR plan

### PR #13 — `feat/agent-core`
- Agent loop using tool-use on the active LLM.
- Accept a PDF path as CLI argument: `child-book-generator draft.pdf` drops straight into the agent.
- One tool: `read_draft()` — returns text + image summary per page.
- First-launch provider picker (current behaviour) still applies if the user hasn't chosen a model.
- Slash commands (`/load /title /render /pages /author /model /help /exit`) stay but are demoted — `/help` still lists them, they're the manual escape hatch.

### PR #14 — `feat/agent-edit-tools`
Narrow tools the agent calls, each with user approval surfaced in the REPL:
- `propose_typo_fix(page, before, after, reason)` — y/n per item
- `set_metadata(field, value)` — title / author / cover.subtitle / back_cover.text
- `set_cover(page_number)` — which page's drawing becomes the cover
- `choose_layout(page, layout, reason)` — agent picks, explains; user can override

**`preserve-child-voice` is enforced at the tool surface**: no tool exists that rewrites page text freely. The LLM can only propose typo/OCR fixes, and those require user confirmation. The `preserve-child-voice` skill is part of the agent's system prompt, but the real guarantee is the absence of a raw `set_page_text` tool.

### PR #15 — `feat/agent-render`
- `render_book(impose=bool)` tool — agent calls when ready.
- A5 + optional A4 booklet; outputs under `.book-gen/output/`.
- Final confirmation message with print instructions for the booklet.

### PR #16 — `feat/project-memory`
- `.book-gen/memory.json` stores the project's settled choices (cover page, typo-fix patterns the user approves, layout preferences, user language).
- On relaunch the agent reads it and defaults to the same answers, only asking when something new comes up.
- Optional global `~/.book-gen/global.json` for cross-book defaults (editing style, preferred layout rhythm). Stays off by default.

### PR #17 — `chore/cleanup`
Pure removal PR — no behaviour change, just simplification now that the agent is the primary interface.

Candidates to review and cut:
- `_CHECKERS` placeholder for OpenAI / Google in `src/providers/validator.py` — intentionally kept as an extension point (new provider = one row in `_CHECKERS`, no dispatch code to touch).
- Slash commands — intentionally kept as escape hatches (offline mode, agent outage, explicit "skip the agent" use).
- `Draft` vs `Book` — intentionally kept: `Draft` is lenient/editable, `Book` is the strict renderer-facing shape. `to_book` is the validation boundary.
- `examples/book.json` + placeholder PNGs — intentionally kept: used by `tests/test_build.py` to smoke the standalone renderer.
- Any tests that pin slash-command edge cases the agent makes irrelevant — none found; all still cover live code paths.

Rule: cut only what is clearly dead; keep anything the escape-hatch flow still uses.

## Explicitly deferred (don't build unless asked)

- **Keyring / persisted API key.** Re-prompting each launch is fine.
- **Illustration generation.** Separate project.
- **OCR for handwritten scans.** Current PDFs have extractable text; add when a real draft needs it.
- **Full parametric layout engine.** `choose_layout` tool applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.
- **Real chat memory as its own feature.** Folded into the agent.

## Done when

- `child-book-generator some-draft.pdf` produces a printable A5 (and optional A4 booklet) in 5-10 minutes of conversation.
- The child's story text is never silently rewritten (no tool allows it).
- Re-running on the same draft uses remembered choices and asks only about what changed.
- Codebase stays small enough for one person to hold in their head.
