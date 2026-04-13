# p2-01 — Tool suite + agent loop

## Goal

The REPL becomes an **agent**: user types intent in natural language, the LLM reasons, calls narrow tools, and the tools do the real work. This is where `preserve-child-voice` is enforced structurally — the LLM has no tool that freely rewrites page text.

## Scope

### Agent loop

- New module: `src/agent.py`.
- On each user turn:
  1. Append user message to conversation.
  2. Send to LLM with full tool schema + system prompt.
  3. LLM responds with either text or a tool call.
  4. If tool call → execute locally → feed result back → loop until LLM replies with text.
  5. Render the final text to the terminal.
- System prompt includes the `preserve-child-voice` contract (story never changes; mechanical fixes only via dedicated tools; always ask before generating images).

### Tool catalogue (phase 2 initial set)

Each tool is a Python function registered with a JSON schema. Wrap existing code; don't duplicate logic.

| Tool | Calls | Purpose |
|---|---|---|
| `load_pdf(path)` | `pdf_ingest.extract_pages` + `extract_images` | Import a PDF, populate the draft book. |
| `get_book_summary()` | — | Return title/author/page count/which pages miss text or image. |
| `get_page(n)` | — | Return a single page's current state. |
| `propose_text_fix(n, before, after, rule)` | — | Surface a typo/OCR fix candidate to the user; user approves before write. |
| `set_metadata(field, value)` | schema | title / author / cover subtitle / back cover. No page text here. |
| `set_page_layout(n, layout)` | schema | One of the four valid layouts. |
| `render_book(impose=False)` | `builder.build_pdf` + `imposition` | Produce the final PDF. |

### Guarded design

- No tool named `set_page_text` or `edit_page`. Page text only changes via `propose_text_fix` → user "yes" → audit log entry → write.
- `propose_text_fix` validates `after` against a character-level diff: if more than N characters change, or if meaning-altering words are added/removed, reject and ask human.
- All tools log to session `edit_log` before mutating state.

## Acceptance

- User can say: "load draft.pdf and tell me what's missing" → agent calls `load_pdf` + `get_book_summary`, replies in prose.
- User can say: "fix the typo on page 2" → agent calls `propose_text_fix` → REPL shows diff → user confirms → applied.
- User can say: "render the book" → `render_book` → PDF appears.
- Attempting to trick the LLM into rewriting a page (e.g. "make page 2 more poetic") results in a refusal — because no tool exists for it.
- Tests: mock LLM that emits a scripted tool-call sequence; assert state transitions.

## Out of scope

- Illustration generation tool (p3-01).
- OCR tool (p4-01).
- Layout suggestion tool (p5-01).
