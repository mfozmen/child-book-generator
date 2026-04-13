# p1-01 — REPL shell + provider selection

## Goal

Launch an interactive terminal session that feels like Claude Code: a persistent prompt, slash commands, readable output, and a clean way to pick / switch the LLM provider.

## Scope

- New module: `src/cli.py` (entry point) + `src/repl.py` (loop).
- UI library: `rich` for rendering + `prompt_toolkit` for input (history, arrow keys, multiline).
- First-run flow:
  1. Greet user.
  2. If no saved provider in session state, ask: "Which model? 1) Claude 2) GPT 3) Gemini 4) Ollama (local) 5) No model (offline mode)".
  3. If cloud provider selected, ask for API key (masked input). Store in session state (not committed, not in env unless user opts in).
  4. Validate by sending a tiny ping to the provider.
  5. Drop into main prompt.
- Slash commands (initial set):
  - `/help` — list commands
  - `/model` — switch provider mid-session
  - `/models` — list available models for current provider; pick one
  - `/session` — show current state (provider, loaded PDF, pages, unsaved changes)
  - `/save` — persist session
  - `/exit` — leave
- Non-slash input = chat turn; goes through the agent loop (wired in p2-01).
- Graceful handling: Ctrl-C cancels current turn without exiting; Ctrl-D exits with save prompt.

## Provider adapters

- New package: `src/providers/llm/`.
- Adapter protocol: `class LLMProvider(Protocol): def chat(messages, tools) -> Response`.
- Implementations (each a separate file):
  - `anthropic.py` — uses `anthropic` SDK, default model `claude-opus-4-6`.
  - `openai.py` — uses `openai` SDK.
  - `google.py` — uses `google-generativeai`.
  - `ollama.py` — uses `ollama` SDK, points at `http://localhost:11434`.
  - `none.py` — raises on any call; lets the rest of the app work offline.
- SDK deps are **optional extras** in `pyproject.toml`:
  - `pip install child-book-generator[anthropic]` etc., or `[all]` for everything.
  - Missing SDK at runtime → clear error pointing to the extras install.

## Acceptance

- `pipx run --spec . child-book-generator` launches the REPL and completes first-run provider setup.
- Switching provider with `/model` works without restarting.
- Session survives provider-auth errors (re-prompts, doesn't crash).
- Tests cover: first-run flow (faked stdin), `/model` switch, bad API key rejection.

## Out of scope

- Agent loop itself (p2-01).
- Tool dispatch (p2-01).
- Multi-session management.
