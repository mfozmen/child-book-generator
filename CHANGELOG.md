# CHANGELOG


## v1.14.0 (2026-04-24)

### Documentation

- **plan**: Two real-session bugs from Yavru Dinozor v3 + note on shadow-install cause
  ([`e6638e3`](https://github.com/mfozmen/littlepress-ai/commit/e6638e374ae66fdbfd3c47ebaba0de677b91d569))

First successful end-to-end run after clearing a stale ``child-book-generator`` editable install
  (pre-PR-#19 clone) that was shadowing every push — that was the actual cause of the ingestion
  failures the v1 and v2 sessions saw, not LLM training memory. Diagnostic: ``pip show`` listed two
  editable installs registering the ``littlepress`` entry point; the alphabetically-first one
  (``child-book-generator-0.6.0``) won, so all our refactor commits never reached the running
  binary. ``pip uninstall child-book-generator -y`` fixed it.

Two real bugs surfaced on the clean run:

- Back-cover blurb prompt rejects "sen yaz" because the greeting forbids agent-invented text.
  Maintainer's mental model is editor-driven, not child-only — agent should offer an opt-in AI draft
  path (draft from story content, user approves / edits / overwrites verbatim). Small PR.

- ``<MIXED>`` pages render text twice: the image contains the handwritten text baked in, AND
  ``page.text`` adds the transcription as normal body copy. Vision classifies too many Samsung-Notes
  pages as ``<MIXED>`` because of margin doodles. Either tighten the vision prompt or flip the
  default to text-only with an explicit review-turn opt-in. Needs design.

### Features

- **repl**: Offer AI-draft option for the back-cover blurb
  ([#66](https://github.com/mfozmen/littlepress-ai/pull/66),
  [`e05fff1`](https://github.com/mfozmen/littlepress-ai/commit/e05fff1f476024e44bb896f8cdf166a9b5fc63b4))

* feat(repl): offer AI-draft option for the back-cover blurb

Yavru Dinozor v3 session (2026-04-24): the user replied "sen yaz" (you write it) to the back-cover
  prompt; the agent refused, citing preserve-child-voice. Maintainer's mental model is
  editor-driven, not child-only: the agent SHOULD offer an AI-draft path here, parallel to the cover
  step's (a)/(b)/(c) three-option format.

Greeting change: the back-cover bullet now names three options the agent must surface explicitly —
  (a) user writes it verbatim, (b) AI drafts a one-line blurb from the story's own page text (draft
  in chat, wait for approval / edit / overwrite before calling set_metadata), (c) skip.
  Preserve-child-voice scope clarified: it applies to the book's INTERIOR (page text — the

child's words, untouched); the back-cover blurb is editor-facing metadata and the AI-draft branch is
  a legitimate opt-in. The draft is grounded in page content, not theme clichés.

Replaced the narrow ``test_greeting_echoes_preserve_child_voice_guard_for_back_cover`` regression
  with two tighter ones: - ``test_greeting_offers_three_back_cover_options`` pins the (a)/(b)/(c)
  structure + the AI / story-grounding tokens. -
  ``test_greeting_clarifies_preserve_child_voice_scope_for_back_cover`` pins the scope split
  (interior vs metadata) and the "verbatim" anchor on the accept path.

Full suite: 648 passing (was 647; net +1 from the split).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

* fix(repl): align CLAUDE.md + skill with back-cover carve-out; scope the regression test

Two findings on PR #66 review:

1. Contract drift: the PR narrowed preserve-child-voice to exclude AI-drafted back-cover blurbs, but
  CLAUDE.md and .claude/skills/preserve-child-voice/SKILL.md both still listed back-cover text
  flatly as in-scope. Canonical docs and production prompt now say opposite things.

Reframed both around authoring source, not field name: - Always child-authored — OCR output, page
  text, invented names / spellings / onomatopoeia. - Child-authored by proxy — cover subtitle or
  back-cover text the user types on the child's behalf. Skill applies. - Editor-facing metadata — a
  back-cover blurb the user opts into having AI draft. Skill does not block; the draft must stay
  grounded in the story's actual page content, and the user signs off.

2. Vacuous regression: the (a)/(b)/(c) + AI + story-grounding tokens all appear in the cover bullet
  already, so removing the entire back-cover addition left the test green. Scoped the assertions to
  a substring slice of the greeting starting at "back-cover blurb" and ending at the next section
  boundary ("ask each of these") — the test now actually regresses when the back-cover feature
  regresses.

Full suite: 648 passing (unchanged; this is a doc-alignment + test-tightening commit, no code
  behaviour drift).

* fix: PR #66 round-2 — align skill YAML description, harden test slice delimiter

Two residual findings:

- SKILL.md YAML front-matter ``description:`` field still listed cover/back-cover text flatly,
  contradicting the body's new carve-out for AI-drafted back-cover blurbs. Skill pickers and any
  description-indexed consumer read the front-matter. Updated to match the body: child-authored
  in-scope + explicit out-of- scope note for the AI-drafted opt-in blurb.

- The back-cover test slice used ``"ask each of these"`` as a free-text end delimiter with no guard.
  A future greeting rewrite rephrasing that sentence would silently grow the slice and re-admit the
  vacuous-pass failure mode. Added an explicit ``assert "ask each of these" in lowered`` guard
  before the slice with a loud error message naming the fix (update the delimiter to match). Now the
  test fails noisily if the anchor drifts, instead of silently passing from the cover bullet.

Full suite: 648 passing (unchanged; doc + test hardening).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>


## v1.13.0 (2026-04-23)

### Chores

- **release**: 1.13.0 [skip ci]
  ([`9010d1e`](https://github.com/mfozmen/littlepress-ai/commit/9010d1edbc5f6d8cf32de1a2fe7fdfe8be4f0cd5))

### Features

- **ingestion**: Run OCR + sentinel classification before the agent starts
  ([#65](https://github.com/mfozmen/littlepress-ai/pull/65),
  [`a781178`](https://github.com/mfozmen/littlepress-ai/commit/a781178349c8528755f5f0c8e5b6ab3a5a78ee81))

* docs(spec): deterministic ingestion — first sub-project of AI-only-for-judgment refactor

Moves OCR + sentinel classification out of the agent tool-use loop and into a pure Python ingestion
  step that runs between ``from_pdf`` and the first agent turn. The LLM still does the vision work,
  but from a deterministic caller -- no tool-use ceremony, no chance for the model to reconstruct
  the old confirm UI from training memory.

Scope is deliberately narrow: only transcribe_page + blank-hide move to Python. propose_typo_fix and
  propose_layouts stay on the agent side (they're bounded and silent; not the source of the theatre
  this PR fixes). Deterministic metadata collection is the next sub-project.

Out of scope explicitly listed: metadata, typo batch, layout batch, Tesseract-only mode, parallel
  OCR. Each can come back as its own sub-PR if a real user need surfaces.

* docs(plan): implementation plan for deterministic ingestion (PR-A)

Eight tasks across five chunks: - Chunk 1: rename 3 agent_tools helpers to module-public so
  ingestion can import them (pure visibility change) - Chunk 2: src/ingestion.py with IngestReport +
  6 TDD tests covering TEXT / MIXED / BLANK sentinels, idempotency, NullProvider - Chunk 3: REPL
  load-hook + integration test that asserts OCR happens before any agent turn - Chunk 4: greeting
  loses PROCESS THE DRAFT AUTOMATICALLY + BATCH THE INGESTION blocks; regression pins the absence -
  Chunk 5: full suite + README/PLAN sweep + PR

Spec at docs/superpowers/specs/2026-04-23-deterministic-ingestion-design.md.

* refactor(agent): promote vision/sentinel helpers to module-public

Drop leading underscores from _call_vision_for_transcription, _extract_sentinel, and
  _apply_sentinel_result to expose them for reuse by the upcoming ingestion module. Pure visibility
  change — no behavior change, all tests remain passing.

* feat(ingestion): scaffold module with no-op entry point

Adds src/ingestion.py with IngestReport dataclass and ingest_image_only_pages() stub. Task 3
  implements the OCR loop body. Includes corresponding test that verifies empty draft returns empty
  report with no LLM calls.

* feat(ingestion): implement deterministic image-only page OCR loop

Iterate image-only pages in draft; call call_vision_for_transcription for each;
  apply_sentinel_result to classify (blank/text-only/mixed); track per-category in the report.
  Errors are captured and logged but non-fatal. Matches preserve-child-voice contract: every page
  mutation goes through the sentinel-enforced vision path.

Implements Task 3 of the deterministic-ingestion plan.

* test(ingestion): add regression tests for sentinel classification

Three tests pin the behavior of each sentinel type (<TEXT>, <MIXED>, <BLANK>) at the ingestion
  layer. This ensures future refactors of ingest_image_only_pages or apply_sentinel_result cannot
  silently break a sentinel branch.

- test_ingest_applies_text_sentinel_clears_image_and_sets_text_only -
  test_ingest_applies_mixed_sentinel_preserves_image_and_layout -
  test_ingest_applies_blank_sentinel_hides_page

* test(ingestion): add regression tests for idempotence and null provider

Task 5 — sentinel regression tests: 1. test_ingest_is_idempotent_on_already_processed_pages:
  Re-running ingestion on an already-transcribed draft must not call the LLM, as already-text pages
  are skipped (matters when reloading memory). 2. test_ingest_no_op_on_null_provider:
  Offline/NullProvider session ingestion silently does nothing, leaving the draft untouched.

Both behaviors are already implemented in the loop body (Task 3). Tests confirm the contract is met.

* feat(repl): auto-ingest image-only pages on PDF load

Wire ``ingest_image_only_pages`` into both load paths — CLI preload (``_greet_if_draft_loaded``) and
  the ``/load`` slash command (``_cmd_load``) — via a shared ``_run_ingestion`` helper. Ingestion
  now runs deterministically before the agent's first turn so the agent always sees a
  fully-transcribed draft. The call is idempotent: already-text pages are skipped, so
  memory-restored sessions are unaffected.

* refactor(repl): remove stale ingestion directives from agent greeting

The deterministic-ingestion work (Task 6) moved OCR and sentinel classification to run before the
  agent's first turn. The greeting still contained two large blocks telling the agent to run these
  steps itself, which reintroduced the theatre this refactor aimed to eliminate. Replace those
  blocks with a single short section stating the draft arrives already transcribed.

Add regression tests to prevent these stale directives from leaking back in during future greeting
  rewrites.

* docs: document deterministic ingestion in README and PLAN

README: add status bullet noting OCR + sentinel classification now runs

before the agent conversation starts (no per-page prompts during load).

PLAN: add feat/deterministic-ingestion to the Shipped table; replace the

"Move ingestion out of the LLM loop entirely" wall-of-text with a trimmed "Continue the
  AI-only-for-judgment refactor" entry naming the two remaining sub-projects.

* docs(plan): record PR #65 for feat/deterministic-ingestion

* fix(ingestion): address PR #65 review — real NullProvider guard, greeting/NOTE alignment, tighter
  regression tests

Three findings, all below threshold but all legitimate:

- #2 (real bug): the ``NullProvider`` early-return in ``src/ingestion.py`` used
  ``getattr(llm_provider, "name", "") == "none"`` which silently returned False for ``NullProvider``
  (it has no ``.name`` attribute). Execution fell through into the loop, called ``chat()`` → raised
  NotImplementedError, got caught in the except block, and populated ``report.errors``. Fixed by
  switching to ``isinstance(llm_provider, NullProvider)`` — guard now short-circuits before any
  vision call. Regression tightened in ``test_ingest_no_op_on_null_provider`` to assert
  ``report.errors == []`` (the old assertions passed whether the guard fired or not because the end
  state of a failed vision call looks identical to a short-circuit).

- #1: ``_build_image_only_note`` in ``src/agent_tools.py`` (surfaced via ``read_draft``) still told
  the agent "Use the ``transcribe_page`` tool to OCR each flagged page" — directly contradicting the
  new greeting's "Do NOT call transcribe_page during the metadata phase" directive. Rewrote the note
  to acknowledge ingestion already ran and point the agent at the post-render review-turn re-OCR
  path instead. New regression ``test_image_only_note_does_not_tell_agent_to_call_transcribe_page``
  pins the alignment.

- #3: ``assert "transcribe_page" in g`` in ``test_greeting_drives_auto_ingest_then_review_turn`` was
  vacuous — the new greeting contains the token in a "do NOT call" directive, so the assertion
  passed whether the greeting drove auto-apply or told the agent to avoid the tool entirely. Removed
  the vacuous line with a comment pointing at the companion test that pins the real intent.

Full suite: 647 passing (was 646; +1 regression from #1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>


## v1.12.0 (2026-04-23)

### Chores

- **release**: 1.12.0 [skip ci]
  ([`0bcfe81`](https://github.com/mfozmen/littlepress-ai/commit/0bcfe810f6255dbfbdbe203b70477b23231fb85e))

### Documentation

- **plan**: Capture Yavru Dinozor v2 failure modes + prescribe ingestion-out-of-LLM refactor
  ([`183d2c3`](https://github.com/mfozmen/littlepress-ai/commit/183d2c3f442742cda4febba3f5a212ba4c9ffb6e))

Session transcript from 2026-04-23 (OpenAI provider this time) kept producing pre-refactor behaviour
  despite PR #60/#62/#63 landing: per-page confirm prompts, keep_image=true parameter references,
  skip_page renumber message, series question in greeting, metadata review checkpoint, missing cover
  step, language mismatch. Likely a combination of stale local install + LLM training-memory
  overpowering prompt-level fixes.

Prompt engineering has hit its ceiling. The real fix -- taking ingestion off the agent loop entirely
  so the LLM doesn't get to speak during transcribe_page calls -- is now the top next-up item.
  Captured the scope and entry criteria in PLAN so the refactor PR has a clear brief to pick up.

- **plan**: Sharpen "AI only for judgment" scope — back-cover blurb opt-in path
  ([`f54be23`](https://github.com/mfozmen/littlepress-ai/commit/f54be238fc1b9026a4d8b2afc62b5a0455992a03))

Maintainer's architectural call: deterministic Python collects data (title/author/series/cover
  menu/metadata review); LLM is for judgment and creativity only. Concrete example added to the
  ingestion-out-of-LLM plan entry: the back-cover blurb is a plain prompt by default ("type it, or
  'skip', or 'AI'"); only the 'AI' branch routes to the LLM to draft a blurb the user then approves
  or edits. Writing verbatim needs no LLM; generating creatively does.

Also enumerates the full split upfront so the refactor's brainstorm has a clear map of what moves to
  deterministic Python (title / author / series / back-cover default / cover menu / metadata review
  / OCR ingestion) vs. what stays LLM-driven (vision OCR + classification, AI cover prompt, AI blurb
  opt-in, review-turn NL parsing).

### Features

- **repl**: Restore series question to greeting
  ([#64](https://github.com/mfozmen/littlepress-ai/pull/64),
  [`3a64133`](https://github.com/mfozmen/littlepress-ai/commit/3a6413314fd4546adee5ee6ebc93d73e04973221))

* feat(repl): restore the "is this a series?" greeting question

The series-question feature (shipped previously under the feat/always-ask-series-question banner per
  docs/PLAN.md) got silently dropped when the T11 greeting rewrite collapsed the upfront-question
  block under the "ask only what cannot be inferred" heading. The series question qualifies under
  that rule -- the user is the source of truth; the agent cannot infer "part of a series" from title
  pattern alone.

Restored the greeting clause: agent ALWAYS asks whether this book is part of a series (every book,
  regardless of title pattern), follows up with the volume number on yes, and has the user record
  the answer inside the title (e.g. ``Yavru Dinozor - 1``) so the cover renderer picks it up
  naturally. No new data field.

Regression: test_greeting_always_asks_series_question locks in

the "series" + "volume" + "always/every book" tokens so a future rewrite can't silently drop the
  flow again.

Full suite: 636 passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

* fix(repl): address PR #64 review — English example, tighter test guard, PLAN row

Three review findings:

- #1 (CRITICAL, CLAUDE.md violation): the new series-question bullet used ``Yavru Dinozor - 1`` as
  the title example baked into the production system prompt. CLAUDE.md's English-only rule applies
  to greetings (same pattern PR #60, #61, #63 had to clean up). Replaced with ``My Series - 1`` —
  language-neutral and still conveys the series-plus-volume shape. Also fixed the same leak in the
  regression test's docstring. - #2 (below threshold, scope): PLAN's row for the series feature
  still read ``TBD``. Updated to ``#64`` / ``feat/restore-series-question`` so the Shipped table has
  the right PR number. Other TBD rows flagged by the reviewer are pre-existing drift outside this
  PR's scope — tracked for a separate docs sweep. - #3 (below threshold): regression test used
  ``assert "always" in g or "every book" in g``. The ``or`` meant a future rewrite could drop either
  phrase and the test still passes. Tightened to ``assert "always" in g`` + ``assert "every book" in
  g`` so both the anti-inference framing tokens are pinned independently.

Full suite: 636 passing (unchanged; fix tightens, does not add).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>


## v1.11.4 (2026-04-23)

### Bug Fixes

- **agent**: Address PR #62 post-merge review — uniform wording, stop typo_fix text echo, regression
  guards ([#63](https://github.com/mfozmen/littlepress-ai/pull/63),
  [`fab05c6`](https://github.com/mfozmen/littlepress-ai/commit/fab05c68ca964803ee97292775dc0a1db58938da))

* fix(agent): address PR #62 review — uniform branch wording, stop echoing page text in
  propose_typo_fix, add regression guards

Three review findings, all below threshold but all legitimate:

1. BLANK-branch directive in _apply_sentinel_result read "do not display or ask for approval" while
  the three sibling branches (TEXT / MIXED / fallback) said "do not display this text or ask for
  approval". Aligned to "do not display this status or ask for approval" so the LLM sees consistent
  language across all four.

2. PR #62 was a bug fix but had no regression test pinning the absence of the Preview snippet. Added
  test_transcribe_page_responses_never_include_transcribed_text_preview — a single test that drives
  all four branches (<BLANK>, <TEXT>, <MIXED>, no-sentinel fallback) with a canary string in the
  transcription and asserts the canary and "Preview" literal are absent from every reply.

3. propose_typo_fix_tool's handler return still included ``New text: {page.text!r}`` — echoing the
  entire page content back to the LLM, exactly the trigger PR #62 was meant to kill on
  transcribe_page. Rewrote the return to metadata-only ("Applied typo fix on page N (reason) (X → Y
  chars). Continue; do not display this status or ask for approval.") and added
  test_propose_typo_fix_response_does_not_echo_full_page_text as the regression guard.

Full suite: 635 passing (was 633; +2 regression tests).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

* fix(agent): unify tool-response suffix into a constant, drop Turkish from test docstring

PR #63 round-2 review. Three findings addressed (round-2 #4 is legitimate but unfixable in-place — a
  future-drift guard, not a RED-first regression, since PR #62 already merged):

- #1 (CRITICAL — CLAUDE.md violation): test docstring contained a Turkish phrase (``Preview: 'YAVRU
  DİNOZOR 1 Bir gün ...'``). CLAUDE.md's English-only rule exempts test FIXTURES (input data) but
  not docstrings / comments. Replaced with ``Preview: '<first 80 chars of transcribed text>'``. -
  #2/#3 (uniform wording): the PR claimed to unify branch wording but swapped one divergence for
  another — <BLANK> said ``"this status"`` while the other three said ``"this text"``, and
  propose_typo_fix said ``"this status"`` while the four sentinel branches said ``"this text"``.
  Extracted the common suffix into ``_NO_DISPLAY_NO_APPROVAL_SUFFIX = "Continue; do not display or
  ask for approval."`` at module level and threaded it through all five call sites. Single source of
  truth; no demonstrative ("this X") to drift on.

Full suite: 635 passing (unchanged — this is a wording refactor plus a docstring cleanup).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 1.11.4 [skip ci]
  ([`7b4a245`](https://github.com/mfozmen/littlepress-ai/commit/7b4a245f076fd4cff93dd8febf42626f83e76055))


## v1.11.3 (2026-04-23)

### Bug Fixes

- **agent**: Drop Preview from transcribe_page tool response + add explicit "do not display"
  directive ([#62](https://github.com/mfozmen/littlepress-ai/pull/62),
  [`8050fdd`](https://github.com/mfozmen/littlepress-ai/commit/8050fdd4a52a7b5678e9d8188032bd97c67e20bb))

Real-session test showed the agent STILL emitting per-page "Apply this OCR transcription to page N?
  ... Approve? (y/n)" pseudo-confirms even after the greeting's forbidden-pattern block was removed.
  Root cause: the tool return message included a ``Preview: 'YAVRU DİNOZOR 1 Bir gün ...'`` snippet
  of the transcribed text. The LLM, upon seeing the text in the tool response, defaulted to "show it
  to the user + ask for approval" -- the exact old-UI behaviour.

Fix: remove the preview from every branch of

``_apply_sentinel_result`` (BLANK / TEXT / MIXED / fallback) and add an explicit instruction in the
  response itself: "Continue with the next page; do not display this text or ask for approval." The
  LLM now has neither the text to re-display nor a template to wrap it in.

Full suite: 633 passing (one assertion on "warning" in the fallback message kept intact by restoring
  that token).

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 1.11.3 [skip ci]
  ([`df0e792`](https://github.com/mfozmen/littlepress-ai/commit/df0e792b2aabd5ca2315751d7c75e8968652218f))


## v1.11.2 (2026-04-23)

### Bug Fixes

- **agent**: Drop Preview from transcribe_page tool response + add explicit "do not display"
  directive
  ([`4aa6260`](https://github.com/mfozmen/littlepress-ai/commit/4aa6260d0721ba59c500829e51b0e752e5cd1ad4))

Real-session test showed the agent STILL emitting per-page "Apply this OCR transcription to page N?
  ... Approve? (y/n)" pseudo-confirms even after the greeting's forbidden-pattern block was removed.
  Root cause: the tool return message included a ``Preview: 'YAVRU DİNOZOR 1 Bir gün ...'`` snippet
  of the transcribed text. The LLM, upon seeing the text in the tool response, defaulted to "show it
  to the user + ask for approval" -- the exact old-UI behaviour.

Fix: remove the preview from every branch of

``_apply_sentinel_result`` (BLANK / TEXT / MIXED / fallback) and add an explicit instruction in the
  response itself: "Continue with the next page; do not display this text or ask for approval." The
  LLM now has neither the text to re-display nor a template to wrap it in.

Full suite: 633 passing (one assertion on "warning" in the fallback message kept intact by restoring
  that token).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 1.11.2 [skip ci]
  ([`245776a`](https://github.com/mfozmen/littlepress-ai/commit/245776a5599ccd37202d1d0269e6582ad553cd00))


## v1.11.1 (2026-04-23)

### Bug Fixes

- **repl**: Remove greeting's forbidden-pattern list that was feeding the LLM
  ([`80d04b6`](https://github.com/mfozmen/littlepress-ai/commit/80d04b6c25e31c86f9ebd16ea153bc8de434dfaf))

PR #61 added a "CRITICAL — NO FAKE CONFIRMATION UI" block to ``_AGENT_GREETING_HINT`` that
  enumerated the old UI strings (``Apply this OCR transcription to page N?``, ``Approve? (y/n)``,
  ``keep_image=True``, ...) as examples of what NOT to emit. In real-session testing Sonnet read the
  list as a **template** and produced exactly those patterns verbatim — negation framing is weak for
  LLMs, literal examples are strong. The fix was making the bug worse.

Replaced the block with a positive instruction: batch all transcribe_page calls, emit ONE status
  line, move to metadata. No literal strings for Sonnet to echo.

Kept the earlier ``PROCESS THE DRAFT AUTOMATICALLY`` section's "Do NOT ask the user to approve any
  of this" language; that one is generic enough not to be shape-matched.

Full suite: 633 passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 1.11.1 [skip ci]
  ([`c789e94`](https://github.com/mfozmen/littlepress-ai/commit/c789e9457040012faf136223a392bc72ace2a227))


## v1.11.0 (2026-04-23)

### Bug Fixes

- **repl**: Forbid agent from mimicking old confirm UI in greeting
  ([#61](https://github.com/mfozmen/littlepress-ai/pull/61),
  [`904dee5`](https://github.com/mfozmen/littlepress-ai/commit/904dee588437cb5390c95f842b55e0c29acd1cac))

* fix(repl): forbid agent from mimicking the old confirm UI in greeting

After PR #60 landed the review-based-gate refactor, real-session testing showed the agent (Sonnet)
  STILL emitting y/n confirmation-style text between auto-applied tool calls -- e.g. ``Apply this
  OCR transcription to page 1? ... Approve? (y/n)``, with exact wording from the old pre-refactor
  UI.

Root cause: the tool side is correct (transcribe_page no longer takes ``confirm`` or ``keep_image``,
  OCR auto-applies), but the greeting told the LLM "the tools no longer take a confirm callback" --
  that's about the code surface. The LLM interpreted it narrowly and continued producing
  conversational pseudo-confirmations it remembered from training data on this repo's earlier
  versions.

Fix: add an explicit CRITICAL section to the greeting listing the

forbidden UI-mimicking text patterns (``Apply this OCR transcription``, ``Approve? (y/n)``,
  ``keep_image=True``, etc.) and telling the agent to emit ONE batch status line after all
  image-only pages are transcribed, then move to metadata + render.

Also updates the keep_image greeting test: the greeting now names ``keep_image`` intentionally (in
  the forbidden-pattern list), so the old "literal substring absent" check is wrong. Replaced with
  an intent-based guard that rejects only active directives (``pass keep_image``, ``use
  keep_image``, ``with keep_image=true``).

Full suite: 633 passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

* fix(agent): address PR #61 review — English-only greeting + propose_layouts description

Two findings on the greeting-forbid-fake-confirm-ui PR:

1. The new CRITICAL block re-introduced a Turkish sentence (``Onayınızı alınca sonraki sayfaya
  geçeceğim``) as a "do NOT emit" example. CLAUDE.md's English-only rule applies even to
  forbidden-pattern examples — same rule that killed yok/tamam in PR #60. Replaced with a
  language-neutral clause ("any equivalent phrased in the user's language") that instructs the agent
  to recognise the intent across languages without naming any specific non-English literal.

2. ``propose_layouts`` Tool.description still claimed the batch existed "so the user can approve the
  whole rhythm with a single yes/no". The ``confirm`` callback was removed from this tool in the
  review-based-gate refactor (PR #60), but the description continued to nudge the agent toward the
  old yes/no rhythm — exactly the residual-wording pattern this PR is trying to kill. Rewrote to
  "Auto-applies — do NOT ask the user for a yes/no; the user audits the finished PDF in the
  post-render review turn."

Full suite: 633 passing (docs-only changes; no behaviour drift).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 1.11.0 [skip ci]
  ([`dacc425`](https://github.com/mfozmen/littlepress-ai/commit/dacc42572b1130038c1449797bd2a680a8d0f843))

### Documentation

- **agent_tools**: Audit module docstring against registered tools
  ([#59](https://github.com/mfozmen/littlepress-ai/pull/59),
  [`03e63b5`](https://github.com/mfozmen/littlepress-ai/commit/03e63b5e56b7df6dff03fddcc4f73a701028404f))

Follow-up to PR #58 round-1 #5. The module docstring under-listed the confirm-gated tools (missing
  ``generate_page_illustration``) and misstated the preserve-child-voice contract — it claimed
  "every page-state mutation is gated", but ``choose_layout`` writes ``page.layout`` directly with
  no confirm, and ``set_metadata`` / ``set_cover`` land without one too.

Rewrite the contract to match reality: the confirm gate protects mutations of the child's *content*
  (page text, page image, whole-page removal). Presentation changes (metadata, cover, single-page
  layout) land directly because they're authoring decisions on top of the content, not the content
  itself. ``propose_layouts`` is still gated even though layout is presentation — the batch-level
  approval is useful on its own.

Tool-by-tool lists are now split into three groups (content-gated, batch-approved, not-gated) so a
  reader can tell at a glance what's what. CLAUDE.md's ``src/agent_tools.py`` bullet gets the same
  correction and points at the module docstring for the full contract.

No code change, no test change — the registrations and handlers are already correct; only the
  documentation was drifting.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

- **plan**: Expand transcribe_page entry with decline-misread failure
  ([`452a7f8`](https://github.com/mfozmen/littlepress-ai/commit/452a7f8e332f7fa432abe8dfb162df9af1849756))

Same Yavru Dinozor session, second failure mode: after the agent surfaced the wrong keep_image=True
  confirm and the user said n, the agent punted to "type out the text manually" instead of retrying
  with keep_image=False. That's the exact workflow the OCR tool exists to avoid. Expand the PLAN
  entry to cover both the wrong default AND the wrong decline interpretation, and list the
  regression tests the fix needs to ship with.

- **plan**: Flag wrong keep_image default on Samsung-Notes transcribe
  ([`4f133b5`](https://github.com/mfozmen/littlepress-ai/commit/4f133b5d8486b38fd797dcf654eb409bed4c044b))

Surfaced by the second Yavru Dinozor run: the agent defaults to keep_image=True when every page has
  an image, but for Samsung Notes / phone-scan exports the image IS the text and keep_image=False is
  required to avoid double-printing. Fix lives in the greeting / tool-description rewrite;
  placeholder entry so it doesn't slip.

- **plan**: Note "same question?" UX nit on transcribe_page confirm
  ([`c20cc5a`](https://github.com/mfozmen/littlepress-ai/commit/c20cc5a692a6a1885d865bc739ca1d0e31f79f35))

Follow-on from the same Yavru Dinozor session: after declining the keep_image=True branch and
  retrying with keep_image=False, the user read the re-prompt as identical because the Approve?
  (y/n) line is byte-for-byte the same across branches -- only the explanation paragraph changes.
  Cheap UX fix (inline the branch into the question line) noted as part of the broader
  transcribe_page follow-up so it lands in the same PR.

- **plan**: Relocate preserve-child-voice gate from pre-approval to post-render review
  ([`81cb051`](https://github.com/mfozmen/littlepress-ai/commit/81cb051c9369f5ef115570e6b7a6ab8da9c11619))

Yavru Dinozor test surfaced that the per-mutation confirm gate has become the UX problem the project
  is supposed to solve. Direct maintainer feedback: "it's an AI project -- produce the book, then
  ask me if there are problems."

Replace the narrow transcribe_page keep_image / decline-interp / "same question" items with a single
  superseding entry that frames the philosophy shift, sketches the new flow (auto-apply OCR,
  auto-pick keep_image, render, then ask "any issues?"), and enumerates what still keeps a confirm
  (cost-incurring illustration calls; page-removal when the page carries a drawing).

Design round must precede the first implementation PR; that PR will touch agent_tools, repl
  (greeting + confirm plumbing), CLAUDE.md, and the preserve-child-voice skill.

- **plan**: Sharpen post-render review into page-number-first question
  ([`43f8a28`](https://github.com/mfozmen/littlepress-ai/commit/43f8a28b81322b4f7d699703f2dbd8acda0f7b35))

Maintainer refinement: picture books are short, so the review step should lead with a numeric ask
  ("which page numbers have issues?") rather than a free-form "any issues?". User types a short list
  like "3, 5" or "none"; agent then drills in per page. Plain-language global asks still work for
  cross-page requests. Keeps the review loop feeling like a simple app, not an essay prompt.

### Refactoring

- **gate**: Move preserve-child-voice from pre-approval to post-render review
  ([#60](https://github.com/mfozmen/littlepress-ai/pull/60),
  [`19acd8d`](https://github.com/mfozmen/littlepress-ai/commit/19acd8ded95f5338e92296c9da5f707910853778))

* docs(spec): review-based preserve-child-voice gate design

Captures the Yavru Dinozor test's fallout: move the confirm gate from "before every write" to "after
  render". Contract becomes "input is immutable, output is reproducible" -- the child's words still
  reach the printed page verbatim, but the audit happens on the finished PDF rather than on every
  intermediate write.

Spec covers: - New contract + where it lands in CLAUDE.md and the preserve-child-voice skill. -
  Tool-by-tool table of what loses its confirm, what keeps one (cost-only gates for the AI
  illustration tools), and two new tools (apply_text_correction, restore_page). - End-to-end flow:
  greet -> auto-ingest -> render -> free-form review message -> re-render -> "none"/"yok" to ship. -
  Input-preserved guarantee as an explicit contract on .book-gen/input/ and pdf_ingest's page-NN.png
  outputs. - Test strategy (~25 confirm fixtures drop, 4 new test files), file scope, out-of-scope
  items, risks.

Also adds the pagination-blank follow-up as a separate smaller entry in docs/PLAN.md so it doesn't
  get rolled into this refactor.

* docs(plan): implementation plan for review-based preserve-child-voice gate

15 TDD tasks across 5 chunks: - Chunk 1: DraftPage.hidden + to_book filter + memory schema v2 (with
  v1 backward-compat read) - Chunk 2: apply_text_correction + restore_page (new tools, no confirm) -
  Chunk 3: drop confirms on propose_typo_fix / propose_layouts / transcribe_page; rename skip_page
  -> hide_page; swap keep_image for <BLANK>/<TEXT>/<MIXED> sentinel classification - Chunk 4: narrow
  Repl._confirm to cost-only illustration tools, rewrite _AGENT_GREETING_HINT for auto-ingest +
  review turn - Chunk 5: end-to-end review-loop integration test, CLAUDE.md Core principle rewrite,
  preserve-child-voice skill rewrite, README/PLAN sweep, PR

Plan tracks the spec at docs/superpowers/specs/ 2026-04-22-review-based-gate-design.md; if the two
  disagree the spec wins.

* feat(draft): add hidden field to DraftPage for page visibility control

Adds a `hidden: bool = False` field to the DraftPage dataclass. This is the foundation for Task 1 of
  the review-based-gate refactor, enabling downstream tools (hide_page, to_book filter, memory
  schema v2) to mark pages for exclusion from the final book.

Includes two test cases covering the default (visible) state and the hidden=True case.

* feat(draft): exclude hidden pages from book projection

The to_book function now filters out pages where hidden=True, ensuring they don't appear in the
  rendered book. This is foundational for the review-based gate flow: pages marked hidden by the
  downstream hide_page tool will be excluded from all rendered outputs.

Task 2 of the review-based-gate refactor.

* feat(memory): persist DraftPage.hidden in draft.json (schema v2)

Bump SCHEMA_VERSION 1 → 2. _to_dict now writes "hidden" per page; _from_dict reads it with a default
  of False so v1 files load cleanly. _ACCEPTED_VERSIONS = {1, 2} replaces the strict equality check,
  making old on-disk drafts fully backward-compatible while new saves always write v2.

Two new tests: round-trip of the hidden flag, and v1 legacy file loads with all pages visible.

* feat(agent): add apply_text_correction tool for post-render verbatim text updates

Adds a new agent tool that writes user-provided text verbatim into a page during the post-render
  review turn. No LLM, no prompt, no heuristics — the tool enforces the user-initiated correction
  path and rejects out-of-range pages. Includes three tests covering verbatim preservation
  (including Unicode and whitespace), bounds checking, and draft mutation.

This tool will be wired into the REPL in a later task.

* feat(agent): restore_page tool to undo post-render edits

Implement restore_page_tool factory: clears the hidden flag and re-attaches the child's original
  drawing from pdf_ingest's per-page output (.book-gen/images/page-NN.png). Concrete realisation of
  the input-preserved guarantee. Use during post-render review turn when the user says 'page N
  restore'. For text reset, use apply_text_correction with the original string.

Task 5 of refactor/review-based-gate: sibling to Task 4's apply_text_correction_tool, covering the
  undo side of the review loop.

* refactor(agent): drop confirm gate from propose_typo_fix

Typo fixes are bounded to 3 words / 30 chars per side, so auto-applying them is safe. Removing the
  y/n gate simplifies the call-site in repl.py and the factory signature. Bad fixes are caught in
  the post-render review turn instead.

Deleted tests: test_propose_typo_fix_does_not_change_draft_when_user_declines (tested removed
  confirm-flow), test_propose_typo_fix_prompt_includes_surrounding_context (tested confirm prompt
  content, no longer shown), test_agent_typo_fix_eof_at_prompt_treated_as_no (EOF-as-no behaviour
  gone), test_agent_typo_fix_user_declines_keeps_text_unchanged (user-declines branch removed).
  Replaced by test_propose_typo_fix_auto_applies_without_confirm and
  test_agent_typo_fix_auto_applies.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* refactor(agent): drop confirm gate from propose_layouts

Layout batches are safe to auto-apply — the user reviews the full rhythm after render instead of
  approving a y/n before apply. Removing the gate simplifies the factory signature and the repl
  call-site.

Deleted tests: test_propose_layouts_does_not_mutate_when_user_declines (tested removed
  decline-flow), test_propose_layouts_prompt_lists_every_page_for_user (tested confirm prompt
  content, no longer shown). Renamed test_propose_layouts_applies_all_on_user_confirmation →
  test_propose_layouts_applies_all (no confirm needed). Removed confirmed==[] assertions from
  validation tests (confirm never called). Added test_propose_layouts_auto_applies_batch as the
  canonical auto-apply regression test.

* refactor(agent): drop confirm gate from transcribe_page, add three-sentinel vision classifier

Replace the y/n confirm gate and keep_image parameter with an autonomous three-sentinel
  classification prompt. The vision model now replies with <BLANK> (hide page), <TEXT> (pure text —
  clear image, text-only layout), or <MIXED> (drawing + text — keep image and layout). Tesseract
  path is treated as <TEXT> behaviour (raw OCR, image cleared).

Removes the Samsung-Notes mis-classification failure mode: the model now self-classifies instead of
  the agent guessing keep_image. Post-render review turn is the user's catch point for any
  misclassification.

* fix(agent): _extract_sentinel skips leading blank lines; remove dead alias

_extract_sentinel took lines[0] unconditionally, so a reply like "\n<TEXT>\nhello" (leading blank
  line, common real-world shape) fell through to the no-sentinel fallback and wrote the raw model
  output verbatim into page.text with a warning prefix. Fix: scan for the first non-empty line
  before matching sentinels, matching what the docstring already claimed.

Also removes _is_blank_sentinel_reply, a backward-compat alias with zero callers that was carrying
  false "compat" weight.

* refactor(agent): rename skip_page_tool to hide_page_tool; set hidden flag instead of popping page

Replaces the destructive list-pop + confirm-gate pattern with a non-destructive flag: hide_page sets
  draft.pages[n-1].hidden = True and returns immediately — nothing is deleted, no confirm is needed.
  restore_page reverses it symmetrically.

Deleted tests: confirm-prompt wording, decline-path suggestions, last-page renumber claim, and
  confirmed-removes-and-renumbers — all tied to the old pop/confirm contract that no longer exists.

Added tests: test_hide_page_does_not_take_confirm (signature regression) and
  test_hide_page_flips_hidden_flag_without_removing (canonical behaviour).

* refactor(repl): narrow _confirm docstring to clarify cost-only gate

After the review-based-gate refactor (tasks 6-9), ``Repl._confirm`` gates only cost-incurring AI
  illustration calls (generate_cover_illustration, generate_page_illustration). Content mutations
  (OCR, typo fix, layout, page hide) run without user gates; the user audits post-render and uses
  edit tools (apply_text_correction, restore_page, hide_page) if needed.

Add regression test test_confirm_plumbing_only_wired_to_cost_tools to catch any future PR that
  accidentally re-wires confirm to a content tool.

* refactor(repl): rewrite greeting for auto-ingest + post-render review turn

Replace the old metadata-review-checkpoint greeting (summarise → approve before render) with the new
  review-based flow:

- PROCESS THE DRAFT AUTOMATICALLY: transcribe_page, propose_typo_fix, propose_layouts all run
  without per-page confirms. - ASK ONLY FOR THINGS YOU CANNOT INFER: title/author, cover choice
  (three options explicit), back-cover blurb. - RENDER IMMEDIATELY, then post a single "which page
  numbers have issues?" prompt that loops until an exit token (none/yok/ok/ship/done/tamam). -
  Review-turn tools named explicitly: apply_text_correction, restore_page, hide_page. - Removes
  series/volume questions (subsumed by title metadata). - Removes keep_image references (tool now
  uses sentinel classification). - Removes skip_page references (renamed to hide_page in T9). - Cost
  confirm stays only on generate_cover_illustration / generate_page_illustration (money gate, not
  content gate).

Tests: removed 5 stale assertions (series, volume, metadata-review

checkpoint, review-step ordering regex, summarise-verbatim). Added 5 new Task 11 tests (auto-ingest
  signal, no metadata checkpoint, review-turn tools present, no skip_page, no keep_image). 13
  greeting tests all green; full suite 614/614 passes.

* fix(repl): wire apply_text_correction and restore_page into _build_agent

Both tools were implemented in Tasks 4–5 (feat commits 997b6a6 and a65bc8a) but never registered in
  Repl._build_agent, so the agent loop couldn't dispatch them. Adds the two factory calls and their
  imports.

Also adds tests/test_review_loop.py — the Task 12 end-to-end integration test that exercises the
  full render → correction → re-render loop and would have caught this gap had it existed at review
  time.

* docs: update preserve-child-voice contract to reflect review-based gate

CLAUDE.md "Core principle" section rewritten: replace the old per-mutation y/n gate description with
  the two-invariant model (immutable input files + verbatim write paths). Architecture bullets
  updated for agent_tools.py (new tool list, cost-only confirm), draft.py (DraftPage.hidden), and
  prune.py (input-preserved guarantee / _AI_IMAGE_PATTERN contract).

src/agent_tools.py module docstring rewritten to match: drops the claim that "every mutation is
  gated behind confirm", introduces the two invariants, and groups tools by confirm behaviour
  (auto-apply / presentation / cost-gated / review-turn-only).

* docs(skill): rewrite preserve-child-voice for input-immutable/verbatim-prompt contract

Replace the per-mutation allowed/forbidden-edit framing with the two-invariant contract: (1) input
  files are write-once after pdf_ingest, (2) every write path is verbatim-only. Concrete rules call
  out the three-sentinel OCR classifier, the apply_text_correction no-strip guarantee, the
  .book-gen/input/ + page-NN.* immutability boundary, and the propose_typo_fix 3-word/30-char bound.
  The allowed/forbidden edit tables survive, reframed as tool-level guarantees rather than per-call
  approval gates. Adds a "when to invoke" section and an updated compliance checklist. Drops all
  wording that implied a confirm gate.

* docs: update README and PLAN for review-based gate refactor

README: replace per-mutation confirm descriptions with auto-apply +

post-render review loop. Add post-render review turn bullet (names apply_text_correction /
  restore_page / hide_page). Add input-immutable guarantee bullet. Remove keep_image=true and
  skip_page references; rewrite transcribe_page bullet for three-sentinel classifier. Update
  How-it-works step 3 and final-review bullet to match new flow.

PLAN.md: add refactor/review-based-gate row to Shipped table (TBD PR number — updated after PR
  opens). Remove the "Rework preserve-child-voice" planning entry from Next up (work is done).

* docs(plan): record PR #60 for review-based-gate in Shipped table

* fix(agent): address PR #60 Sonar findings

Two new issues flagged on the PR, both legitimate:

- S1481 (MINOR) propose_typo_fix_tool's ``reason`` local went dead when the confirm gate was dropped
  in T6 — the old confirm prompt was the only reader. Restored traceability by threading ``reason``
  into the reply message (``Applied on page N (<reason>). New text: ...``), so the agent's own audit
  trail surfaces *why* a fix was applied. - S1192 (CRITICAL) ``.book-gen`` was hard-coded 3x in
  src/agent_tools.py. Extracted to a module-level ``_BOOK_GEN_DIR`` constant. All three call sites
  (restore_page's original-image path, the AI-illustration output path, render_book's source_dir)
  now share the constant.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

* fix(agent): address PR #60 review findings (9 fixes + regression tests)

Finding 1: read_draft description still referenced skip_page + confirm-with-user — rewrote the
  BLANK-sentinel sentence to name hide_page / restore_page.

Finding 2: _build_image_only_note mandated 'always confirm the transcription with the user' —
  replaced with auto-apply + review-turn audit reality.

Finding 3: restore_page hardcoded .png; pdf_ingest can write .jpg (Samsung Notes). — replaced with
  glob scan, PNG-preferred when both exist.

Finding 4: Turkish tokens yok/tamam in _AGENT_GREETING_HINT violated CLAUDE.md English-only rule —
  replaced with language-neutral intent-recognition instruction.

Finding 5: unknown-sentinel fallback cleared page.image + forced text-only, destroying the child's
  drawing — fallback now only writes text, leaves image and layout untouched.

Finding 6: deleted dead confirm-dance helpers (_build_typo_prompt, _TYPO_CONTEXT_CHARS,
  _build_skip_page_prompt, _skip_preview_line, _skip_drawing_line, _skip_renumber_line,
  _build_layout_prompt); all confirmed caller-free before deletion.

Finding 7: apply_text_correction silently wrote to hidden pages whose text never reached the
  rendered PDF — auto-unhides and names the action in reply.

Finding 8: _read_draft_page_lines omitted [hidden] marker; agent couldn't see suppressed pages —
  added hidden_tag mirroring the existing [image-only] pattern.

Finding 9: load_draft default for missing version key was SCHEMA_VERSION, letting versionless JSON
  pass validation — changed sentinel to None.

Each finding paired with a regression test (10 new tests, 1 old test updated to match the renamed
  skip_page → hide_page contract).

* test(agent): close PR #60 coverage gap on new code

Sonar flagged 95.9% coverage on new code (4 missing lines). Added three regression tests and deleted
  one dead helper:

- apply_text_correction_tool ``_MSG_NO_DRAFT`` branch (line 381) →
  test_apply_text_correction_reports_no_draft_when_unloaded - restore_page_tool ``_MSG_NO_DRAFT``
  branch (line 437) → test_restore_page_reports_no_draft_when_unloaded - _extract_sentinel
  empty-reply early-return (line 946) →
  test_extract_sentinel_returns_empty_on_empty_or_whitespace_reply - _is_sentinel_reply helper —
  zero callers in src/ or tests/, removed as dead code rather than testing unused machinery.

Full suite: 628 passed (was 625; +3 new tests, 0 deletions since the removed helper had no test
  pinning it).

* fix(agent): address PR #60 round-3 doc/robustness review

Three below-threshold findings from the latest review, all cheap enough to fix in-scope:

- restore_page extension allow-list was too narrow — dropped the ``{.png, .jpg, .jpeg}`` filter and
  now accepts any file pdf_ingest may have written under ``.book-gen/images/page-NN.*``. pdf_ingest
  controls that directory; PIL returns whatever format the PDF embedded (WebP, GIF, TIFF on exotic
  exports). Regression test exercises the ``.webp`` case. - restore_page Tool.description said
  ``page-NN.png`` but the handler globs; corrected the description to ``page-NN.*`` with a note that
  the extension depends on what the PDF embedded. - apply_text_correction Tool.description didn't
  mention the auto-unhide side effect added earlier this session; now it does.

Plus two regression tests guarding the description contracts so a future rewrite can't silently
  drift them back.

Round-3 #4 (``_BOOK_GEN_DIR`` is a third definition of the ``.book-gen`` literal alongside
  memory.MEMORY_DIR / session.SESSION_DIR) is deferred to a separate consolidation PR — cross-module
  refactor, out of scope for this PR.

* fix(agent): tighten restore_page extension allow-list + regression guards

Round-4 review on PR #60, both below threshold but real:

- restore_page's F1 fix over-corrected: dropping the extension filter entirely opened a narrow gap
  where a stray non-image (``page-01.txt``, ``page-01.json``) in ``.book-gen/images/`` would be
  attached as page.image and crash the renderer. Restored an allow-list, broadened to the PIL-known
  image formats: {png, jpg, jpeg, webp, gif, tiff, tif, bmp}. Exotic

PDF exports still round-trip; accidental strays don't. Regression:
  test_restore_page_ignores_non_image_strays.

- Two round-3 regression tests used permissive ``or`` conditions that would pass even if a future
  refactor silently weakened either half. Tightened restore_page_description test to require BOTH
  ``page-NN.*`` and ``.jpg`` signals; tightened apply_text_correction_description test to require
  the canonical ``unhide`` verb (not just ``hidden``).

Full suite: 632 passing (was 631; +1 regression).

* fix(agent): add .jpeg2000 to PIL image allow-list + refresh stale test docstring

PR #60 round-5 review findings, both below threshold:

- _PIL_IMAGE_EXTS missed .jpeg2000. PDFs embedding JPEG2000 via the /JPXDecode filter land as
  page-NN.jpeg2000 (PIL format name "JPEG2000" → _extension_for returns "jpeg2000"). Narrow but real
  gap. Regression test_restore_page_accepts_jpeg2000_from_jpxdecode_streams pins the case. -
  test_restore_page_accepts_exotic_extensions_pdf_ingest_may_write's docstring still claimed "not a
  hardcoded allow-list" from the round-3 phrasing, but round-4 deliberately re-added one. Refreshed
  the docstring to describe the current PIL-known-extensions allow-list and the round-4/round-5
  scope adjustments.

Full suite: 633 passing (was 632; +1 regression).

* docs(agent): inline comment in restore_page mentions JPEG2000

PR #60 round-6 review finding, below threshold: the inline comment above the ``glob`` call in
  restore_page still listed only ``WebP, GIF, TIFF, BMP`` for exotic PDF embeddings, even though the
  round-5 commit ``0472e91`` added JPEG2000 to ``_PIL_IMAGE_EXTS`` and its module-level comment.
  Aligned the inline prose so the three places (module comment, inline comment, allow-list set) all
  name the same set of formats.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v1.10.0 (2026-04-21)

### Chores

- **release**: 1.10.0 [skip ci]
  ([`a799600`](https://github.com/mfozmen/littlepress-ai/commit/a799600eec75f75bd999a1a9aab89e94a8579a0b))

### Features

- **cleanup**: Auto-prune orphan images and old render snapshots
  ([#58](https://github.com/mfozmen/littlepress-ai/pull/58),
  [`cc9835b`](https://github.com/mfozmen/littlepress-ai/commit/cc9835b92686c5cec2e567c7425506eb00555912))

* feat(cleanup): auto-prune orphan images and old render snapshots

New src/prune.py drops PNGs under .book-gen/images/ that aren't referenced by the current draft
  (retry leftovers from generate_*_illustration calls) and snapshot PDFs beyond the most-recent keep
  versions (default 3). Auto-runs after every versioned render from both the agent tool and the REPL
  /render command; a new /prune [--dry-run] [--keep N] slash command exposes the same logic
  manually. Stable <slug>.pdf / <slug>_A4_booklet.pdf pointers, .book-gen/input/, and referenced
  cover/page images are never touched.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

* fix(cleanup): address PR #58 review — preserve child drawings, tighten guards

Four behaviour changes from the review:

- Narrow orphaned_images() to only match AI-generated filenames (cover-<10-hex>.png /
  page-<10-hex>.png). The child's extracted drawings (page-NN.png from pdf_ingest.extract_images)
  are now preserved even when the draft no longer references them — e.g. after transcribe_page
  clears the page.image for a Samsung-Notes screenshot. Without this guard an auto-prune on the next
  render would silently destroy the child's art, violating the core "child is the author" stance in
  CLAUDE.md. - Reject /prune --keep 0 (and negatives). The usage message promises "positive
  integer"; 0 would quietly wipe every snapshot. - prune() now truly swallows unexpected errors at
  the call boundary. A failure in the housekeeping hook at the end of render_book must never mask a
  successful render — the user already has their PDF on disk. - Cover _parse_prune_args error
  branches with tests (unknown token, bare --keep, non-integer, negative, zero).

Plus CLAUDE.md now documents src/prune.py and the render-time side-effect alongside the other src/
  modules.

* fix(cleanup): match real page-illustration filenames in prune regex

Reviewer round 2 on PR #58 caught that ``_AI_IMAGE_PATTERN`` missed the page-illustration shape
  entirely. ``generate_page_illustration`` calls ``_hashed_image_output_path`` with a prefix of
  ``f"page-{page_n}"``, so the filenames are ``page-<N>-<10hex>.png`` (e.g.
  ``page-1-abcdef0123.png``) — but the regex required exactly ``page-<10hex>.png``, matching only
  the cover case.

Net effect: page retries (the dominant accumulator — 8 pages x 3 retries ≈ 24 images per book per
  the PR motivation) silently accumulated forever. Covers pruned correctly. The original regression
  test only exercised the cover path and so didn't catch it.

Fix: regex now reads ``^(?:cover|page-\d+)-[0-9a-f]{10}\.png$``. The

regression test grows two new cases (``page-1-<hex>.png`` and ``page-15-<hex>.png``) that prove both
  page-retry shapes are pruned, while the child's ``page-NN.png`` drawings and user-dropped custom
  assets are still preserved.

Also expanded the module docstring's "never touched" section to explicitly name the child's
  extracted drawings — the core preserve-child-voice invariant that ``_AI_IMAGE_PATTERN`` exists to
  enforce belongs in the module contract, not only in a private helper's docstring.

* docs(prune): sync orphaned_images() docstring with page-N-hex shape

Reviewer round 3 on PR #58 caught that ``orphaned_images()``'s own docstring still described the
  pre-round-2 convention (``page-<10-hex>.png``) even though the regex, sibling comment, and module
  docstring all moved to ``page-<N>-<10hex>.png`` in 9e33fbb. Code is correct; the drift was inside
  the function's docstring example only.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>


## v1.9.0 (2026-04-19)

### Chores

- **release**: 1.9.0 [skip ci]
  ([`e954b3c`](https://github.com/mfozmen/littlepress-ai/commit/e954b3c67aae3bb25295f021f358e9903c7cc42d))

### Features

- **agent**: Generate_page_illustration — restore illustrations after OCR
  ([#57](https://github.com/mfozmen/littlepress-ai/pull/57),
  [`d101aac`](https://github.com/mfozmen/littlepress-ai/commit/d101aacf70986030914f24a29d850b522fbfd6c1))

* feat(agent): generate_page_illustration — restore illustrations after OCR

Closes the deferred "Per-page AI illustration generation" item.

PR #48 clears ``page.image`` + switches to ``text-only`` layout when ``transcribe_page`` accepts an
  OCR result, which fixes the Samsung-Notes duplicate-text bug but leaves the page without an
  illustration. This tool is the natural second half: restore (or add) a drawing on any page with a
  one-prompt round-trip through OpenAI's ``gpt-image-1``.

### Shape

Symmetric to ``generate_cover_illustration`` — same pricing-aware y/n confirm, same
  PRESERVE-CHILD-VOICE guard in the description ("describe the scene in your OWN words from the
  story's themes — do NOT quote or paraphrase the child's page text"), same 1024x1536 portrait
  sizing, same OpenAI-only REPL gate, same ``.book-gen/images/`` output directory (new prefix:
  ``page-<N>-<hash>.png``).

Inputs:

- ``page`` (required, int, 1-indexed) - ``prompt`` (required, str) - ``quality`` (optional enum: low
  / medium / high, default medium) - ``layout`` (optional enum: image-top / image-bottom /
  image-full / text-only — switches the page off text-only if the user wants a specific layout in
  the same call)

On approval: ``draft.pages[n-1].image`` set to the saved PNG, optional ``draft.pages[n-1].layout``
  set from the layout input.

### Helpers

- ``_hashed_image_output_path(session_root, prompt, prefix)`` shared between the cover + page
  variants; ``_cover_image_output_path`` now delegates to it so the two tools produce symmetric
  hashed filenames (``cover-<hash>.png`` vs ``page-<N>-<hash>.png``). -
  ``_parse_page_illustration_input`` / ``_parse_page_illustration_fields`` mirror the skip_page /
  transcribe_page parse-helper pattern — malformed input returns a tool-result string, never a
  ``KeyError`` / ``ValueError`` across the tool boundary.

### Tests (13 new in agent_tools; 3 new in REPL integration)

``agent_tools`` (13):

- Draft guard, page-range check, empty-prompt, invalid-quality, invalid-layout, missing/non-int page
  (four malformed-input cases in one test). - Confirm prompt includes price + quality + page number
  + the agent's prompt text. - Declined-confirm leaves draft untouched + provider not called. -
  Approved path: provider called with prompt + 1024x1536 + medium; ``page.image`` set +
  ``page.layout`` set when provided. - Output path lives under ``<root>/.book-gen/images/``. -
  Provider error surfaces as a clean tool-result message. - Description carries the
  PRESERVE-CHILD-VOICE guard ("own words", "child") — same strict phrase check as the cover variant.
  - Schema advertises page / prompt / quality / layout; required is ``{"page", "prompt"}``.

``repl_tools`` (3):

- Registered on OpenAI with a key. - Omitted on Anthropic / Google / Ollama. - Omitted on OpenAI
  without a key.

581 tests green (was 565).

### Docs

- README: new Status bullet describing the feature + the OpenAI gate. - PLAN.md: removed the
  "Per-page AI illustration generation" deferred line — shipped here.

* fix(agent): address PR #57 review — text-only reject, overwrite warn, doc drift

Eight findings, three critical and five sub-threshold.

### Critical

1. **``layout="text-only"`` was accepted by the handler and advertised in the schema — nonsensical
  for a tool that writes an image onto the page.** User would pay for a PNG, the file would be
  written, ``page.image`` set, and then ``page.layout = "text-only"`` would hide it. Rejected at the
  input boundary with a clear "pick image-top / image-bottom / image-full" message; dropped from the
  schema enum so the LLM doesn't suggest it.

2. **No overwrite guard when ``page.image`` was already set.** Approval silently replaced scanned
  child art, a ``keep_image=true`` preserve from ``transcribe_page``, or an earlier AI generation.
  ``_build_page_illustration_confirm_prompt`` now takes ``existing_image`` and appends "NOTE: page N
  already has an image (path) and will be REPLACED — the existing drawing cannot be recovered
  in-session" to the confirm prompt.

3. **CLAUDE.md architecture bullet didn't list ``generate_page_illustration``.** Fourth recurrence
  of the same stale-bullet pattern. Extended the list to name the new tool alongside its cover
  sibling.

### Sub-threshold

4. **Stale ``_IMAGE_COST_USD``.** Spot-checked against the OpenAI pricing page: at 1024x1536
  portrait the ballpark is low ≈ $0.02, medium ≈ $0.06 (was $0.07), high ≈ $0.25 (was $0.19).
  Updated the shared constant + refreshed the two tool descriptions and the README bullet so the
  numbers stay in sync. Comment on the constant now names the last-checked date and points at the
  pricing page for the next drift.

5. **Preserve-child-voice test was keyword-only.** Tightened to require the canonical
  ``PRESERVE-CHILD-VOICE:`` marker AND ``own words`` AND a regex ``(do not|don't) … paraphrase`` in
  the same sentence — so a rewrite dropping any piece of the guard can't pass vacuously.

7. **No filename-prefix regression test.** Added
  ``test_generate_page_illustration_filename_uses_page_n_prefix`` pinning the
  ``page-<N>-<hash>.png`` convention.

8. **PLAN's "cap old render snapshots" item widened to cover generated images too.** Every retry of
  ``generate_*_illustration`` leaves another file in ``.book-gen/images/`` (by design — the
  ``time_ns()`` token means two identical-prompt calls produce two files, so the user can compare).
  Called out as the biggest accumulator on an iterative workflow (8 pages × 3 retries × medium ≈ 24
  images per book) so the eventual prune / cap work covers this surface too.

### Not addressed in this PR

- **#6 — behavioural paraphrase check.** Reviewer's own assessment: "not a regression, but a
  behavioural check would

complete the defence." A token-overlap guard (reject if the prompt shares > K consecutive tokens
  with ``page.text``) has false-positive risk on generic child-story vocabulary ("dinozor",
  "yumurta"). Deferred to its own PR where the K threshold and the matching strategy can be picked
  deliberately.

### Tests (4 new + 2 tightened; 584 total, was 581)

- ``test_generate_page_illustration_rejects_text_only_layout`` -
  ``test_generate_page_illustration_confirm_warns_when_page_has_existing_image`` -
  ``test_generate_page_illustration_filename_uses_page_n_prefix`` -
  ``test_generate_page_illustration_description_has_preserve_child_voice_guard`` tightened (marker +
  regex). - ``test_generate_page_illustration_schema_advertises_page_prompt_quality_layout``
  tightened (``text-only`` absent from the layout enum). - Existing 11 page-illustration tests still
  passing.

- README: refreshed pricing line. - CLAUDE.md: architecture bullet now names
  ``generate_page_illustration``. - docs/PLAN.md: accumulation item widened.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.8.0 (2026-04-19)

### Chores

- **release**: 1.8.0 [skip ci]
  ([`57b50a0`](https://github.com/mfozmen/littlepress-ai/commit/57b50a08713b411263f39c799abedfb03b2b9c38))

### Features

- **agent**: Tesseract OCR fallback for transcribe_page
  ([#56](https://github.com/mfozmen/littlepress-ai/pull/56),
  [`bd05b12`](https://github.com/mfozmen/littlepress-ai/commit/bd05b125ee69c27e64f4662f440c4a5ca143321a))

* feat(agent): Tesseract OCR fallback for transcribe_page

Adds a ``method`` parameter to ``transcribe_page`` — default ``"vision"`` (existing LLM-vision path)
  or ``"tesseract"`` for a local-offline OCR pass via ``pytesseract``. Same handler, same confirm
  gate, same preserve-child-voice guards; just a different front-end.

### Why

LLM vision costs a cloud round-trip per page (~$0.005-$0.02 on most providers). Samsung-Notes-style
  matbaa yazısı — the Yavru-Dinozor-shaped draft — reads at near-100% accuracy on a modern Tesseract
  install with the ``tur`` trained-data pack, at zero API cost and offline. Per-page agent choice:
  hard-case handwriting goes through the LLM, clean typed text goes through Tesseract.

### Inputs

- ``method: "vision" | "tesseract"`` — default ``"vision"``. - ``lang: string`` — Tesseract language
  code (``"eng"`` default; ``"tur"``, ``"tur+eng"``, etc. for Turkish drafts).

### Error handling

Two distinct failure modes for Tesseract get their own clean messages:

- ``pytesseract`` not installed (Python package missing) → ``pip install pytesseract`` hint +
  suggestion to retry with ``method='vision'``. - System ``tesseract`` binary not on PATH (the
  package's ``TesseractNotFoundError``) → per-OS install hints (Windows UB-Mannheim installer,
  ``brew install`` on macOS, ``apt install tesseract-ocr tesseract-ocr-tur`` on Linux). - Any other
  Tesseract error → truncated ``str(e)[:200]`` + retry hint.

Draft is never touched before the confirm gate, so a mistyped ``method`` or missing dep leaves
  ``page.text`` untouched.

### Tests (7 new; 561 total, was 554)

- ``test_transcribe_page_defaults_to_vision_method`` — hot-path regression: no ``method`` → LLM
  branch runs, no Tesseract.

- ``test_transcribe_page_method_tesseract_uses_tesseract_not_llm`` — ``llm.chat`` is not called when
  method='tesseract'. - ``test_transcribe_page_tesseract_passes_lang_through`` — the ``lang`` input
  reaches pytesseract verbatim. -
  ``test_transcribe_page_tesseract_missing_library_returns_clean_error`` — ``pytesseract`` not
  installed, clean error + draft untouched. -
  ``test_transcribe_page_tesseract_empty_reply_does_not_overwrite`` — whitespace reply treated like
  the vision empty branch; draft keeps its existing text. -
  ``test_transcribe_page_tesseract_binary_missing_returns_clean_error`` — ``TesseractNotFoundError``
  raised by pytesseract surfaces as an install-hint message with "PATH" / "install" keywords. -
  ``test_transcribe_page_schema_advertises_method_and_lang`` — schema enumerates the two methods and
  accepts a string lang.

### Docs

- Tool description rewritten to name both engines, their use cases, and the install preconditions
  for Tesseract. - README bullet expanded: "two engines behind one tool". - ``docs/PLAN.md`` —
  Tesseract item removed from "Next up" (shipped here).

* fix(agent): address PR #56 review — extras, docs, Tesseract robustness

Eight findings (three critical, five sub-threshold). All valid.

### Critical

1. **``pytesseract`` was not declared as an optional extra.** The in-tool error's ``pip install
  pytesseract`` hint was a workaround, not a declared dependency set. Added ``tesseract =
  ["pytesseract>=0.3.10"]`` under ``[project.optional-dependencies]`` and updated the README Install
  block with ``pip install 'littlepress-ai[tesseract]'`` plus per-OS install instructions for the
  system tesseract binary + trained-data packs.

2. **CLAUDE.md architecture bullet was stale again.** PR #55 review had forced this exact bullet
  from ``(Anthropic-only)`` to ``(every real provider; model must support vision)`` but this PR
  shipped a second engine (Tesseract) and the bullet still described only vision. Updated to name
  both engines + the opt-in extra.

3. **English-only rule violated in production strings.** Four occurrences of "matbaa yazısı" — tool
  description, schema field description, helper docstring, README Status bullet. CLAUDE.md:
  test-fixture exception does NOT cover production strings. Rewritten to the English primary term
  ("typeset / printed text") with the Turkish phrase kept as an italicised parenthetical in the
  README only, where the term is the most pedagogically useful.

### Sub-threshold

4. **Empty-reply error was vision-specific on the Tesseract path.** ``_interpret_vision_reply`` was
  shared; on Tesseract an empty OCR result got the "safety filter / vision- unsupported" diagnosis.
  Renamed to ``_interpret_reply`` and gave it a ``method`` parameter. Tesseract branch now advises
  "low contrast / wrong lang / higher DPI / switch to ``method='vision'``." New test pins the
  Tesseract-specific wording.

5. **``lang`` was unvalidated before hitting the Tesseract CLI.** Bogus values (``"tur,eng"``,
  ``"../foo"``, ``"--help"``, empty string, unusual casing) surfaced as cryptic binary errors the
  user couldn't map back to their input. Added ``_validate_tesseract_lang`` — ISO-639-2/B allowlist:
  ``[a-z]{3}(\+[a-z]{3})*``. Rejected values return a clean tool-result error before the CLI is
  invoked. Two new tests — rejected-bad-langs batch and accepted-good-langs batch.

6. **Tool description oversold Tesseract's verbatim guarantee.** "Tesseract returns bytes and can't
  paraphrase at all" was misleading — OCR errors + dropped diacritics happen. Softened to "classical
  OCR engine — it will misread characters but won't rewrite or summarise, and the y/n confirm gate
  is the real preserve-child-voice guard."

7. **``except tess_not_found`` mislabelled unrelated errors.** The ``getattr(..., Exception)``
  fallback converted every pytesseract exception (OOM, permission, decode) into the "tesseract
  binary not on PATH" install hint. Switched to ``getattr(..., None)`` + ``isinstance`` check inside
  a generic handler — unrelated exceptions now fall through with their own message. New test pins
  the distinction: a ``_PermissionBoom`` exception does NOT produce the "not found on path" hint.

8. **Tesseract path skipped the PIL decode the vision path used.** Two practical consequences on
  Windows: (a) broken PNGs emitted garbage OCR instead of a clean decode error; (b) long-path /
  non-ASCII filenames tripped the CLI. Fix: wrap the image in ``with Image.open(image_path) as img``
  and pass the PIL image to ``pytesseract.image_to_string`` — pytesseract's temp-file shim handles
  path quirks when given an Image.

### Tests

4 new (560 → 564): ``tesseract_empty_reply_surfaces_tesseract_hint``,
  ``tesseract_rejects_unsafe_lang``, ``tesseract_accepts_valid_langs``,
  ``tesseract_unrelated_exception_not_mislabeled_as_binary_missing``.

Plus 1 existing test loosened: the generic ``tesseract_empty_reply_does_not_overwrite`` now checks
  for the Tesseract-specific message markers the sibling test pins in detail.

565 tests green (was 561).

* refactor(agent_tools): extract OCR-engine dispatch to close Sonar S3776

PR #56's review-fix pass added a second engine branch + ``lang`` validation to
  ``transcribe_page_tool::handler``, which pushed its cognitive complexity from ~15 to 18 on the
  PR-#56 Sonar scan (python:S3776).

Pure extract-function — same pattern as earlier in the file (``_parse_skip_page_input`` /
  ``_parse_generate_cover_input`` / ``_parse_transcribe_input``). New helper
  ``_run_ocr_engine(method, input_, page, page_n, get_llm)`` handles the method-switch, the ``lang``
  validation, and the two ``_call_*_for_transcription`` dispatches; returns the same
  ``(cleaned_reply, error)`` shape the callers used inline before.

Handler is back to a short linear script: draft guard → parse input → run OCR → interpret → confirm
  → apply. Complexity under the 15-limit again. 565 tests green, no behaviour change.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.7.0 (2026-04-19)

### Chores

- **release**: 1.7.0 [skip ci]
  ([`3ff67dc`](https://github.com/mfozmen/littlepress-ai/commit/3ff67dc0ade25b2d98932f91db5445f1a58de420))

### Features

- **llm**: Multi-provider transcribe_page via per-provider image translators
  ([#55](https://github.com/mfozmen/littlepress-ai/pull/55),
  [`ece8a9b`](https://github.com/mfozmen/littlepress-ai/commit/ece8a9b148d86eb30ba60bd2c3cf2c2c8cf18835))

* feat(llm): multi-provider transcribe_page via per-provider image translators

PR #48 review #1 flagged that ``transcribe_page`` was Anthropic-only because the other providers'
  message translators silently dropped image content blocks (the LLM would see only the text prompt
  and hallucinate a transcription). The Anthropic-only gate shipped as a safety measure; actual
  multi-provider support was deliberately deferred to this PR.

### Per-provider image wire formats

Each provider has a different multi-modal shape. Each translator grew an image-block branch in its
  native format:

**OpenAI** — ``_openai_user_messages`` now detects any ``image`` block on a user message and emits a
  single multi-modal user message whose ``content`` is an array of items: ``{type: "image_url",
  image_url: {url: "data:<mime>;base64,<data>"}}`` for images, ``{type: "text", text: ...}`` for
  text. Text-only user messages keep the string-content shape (hot path unchanged).

**Gemini** — ``_gemini_parts_from_blocks`` now emits ``Part(inline_data=Blob(mime_type, data))`` for
  image blocks, with the base64 data decoded to raw bytes (Gemini wants bytes, not the base64 string
  OpenAI and Ollama take).

**Ollama** — ``_ollama_user_messages`` now lifts image payloads into the message-level ``images``
  list that the Python client accepts, keeping the text-string ``content`` intact (Ollama's LLaVA +
  other vision models read images off ``images``, not the content array).

### Helpers

- ``_openai_multimodal_content`` builds the OpenAI content-array shape from a mixed block list. -
  Ollama + OpenAI both take a "has image?" detection pass, so plain text-only user messages stay on
  the original code path and existing tests don't rewrite.

### Gate lifted

``src/repl.py::_build_agent`` — ``transcribe_page_tool`` now registers on every real provider
  (Anthropic / OpenAI / Google / Ollama). NullProvider still omits it; there's nothing to chat with.
  The tool's description makes the vision-capability requirement explicit so the LLM knows a
  non-vision model will surface as a failed chat, not a silent hallucination.

### Tests (4 new in ``test_llm_translator_helpers.py``, 1 new in ``test_repl_tools.py``; 2 updated)

- ``test_messages_to_openai_converts_image_block_to_image_url_content_item`` -
  ``test_messages_to_openai_keeps_string_content_when_no_image`` (hot path didn't regress) -
  ``test_messages_to_ollama_lifts_image_blocks_into_images_field`` -
  ``test_messages_to_gemini_converts_image_block_to_inline_data_part`` (with a small fake
  Part/Blob/Content fixture so the test doesn't need the real google-genai SDK) -
  ``test_transcribe_page_registered_on_every_real_provider`` replaces the old Anthropic-only pin. -
  ``test_transcribe_page_omitted_on_null_provider`` keeps the offline-default behaviour pinned. -
  The ``skips_unknown_block_types`` test for ``_openai_user_messages`` updated to use ``video`` as
  the stand-in unknown — ``image`` is handled now.

### Docs

- README: removed the "Anthropic-only" claim on the ``transcribe_page`` bullet, updated the
  guardrail list (was 4, now 4 different items — the "Anthropic-only defence" dropped, replaced by
  "non-vision models fail cleanly"). - ``read_draft``'s agent-facing description now says "every
  real provider" instead of "Anthropic only for now".

548 tests green (was 544).

* fix(agent): address PR #55 review — doc drift + tool_result guards

Four findings (#1 critical, #2-3 sub-threshold, #4 a minor maintainer's-call note we skip).

### Critical

1. **Two "Anthropic-only" claims survived the PR that lifts the Anthropic-only gate.** Both fixed:

(a) ``CLAUDE.md:25`` — architecture bullet said ``transcribe_page (Anthropic-only)`` right above the
  preserve-child-voice paragraph. Load-bearing doc drift. Rewritten to "every real provider; model
  must support vision".

(b) ``transcribe_page_tool`` function docstring axis 1 still described the old gate ("Only
  registered when the active provider is Anthropic, because only AnthropicProvider.chat currently
  forwards image content blocks intact"). Both halves of that sentence became false after PR #55.
  Axis 1 rewritten to describe the new gate: registered on every real provider, but the active
  *model* still has to support vision; non-vision models surface as a failed ``llm.chat`` call with
  a truncated error message rather than a hallucinated transcription.

### Sub-threshold

2. **Image-containing user messages could silently drop ``tool_result`` blocks.** The
  image-detecting branch in ``_openai_user_messages`` / ``_ollama_user_messages`` handed the content
  list straight to the multi-modal builders, which only knew ``image`` + ``text``. A ``tool_result``
  sharing a user message with an image would vanish. Not triggered by ``transcribe_page`` today (it
  builds a fresh ``[image, text]`` pair), but a defensive handler costs nothing and future callers
  can't trip the quiet-drop trap.

Both helpers now emit ``tool_result`` blocks as separate ``role: tool`` messages first, then the
  remaining image + text blocks form the multi-modal user message. Two new invariant tests pin the
  "tool_result isn't lost when it shares a message with an image" contract — one per provider.

3. **No parametrised regression test that ``confirm`` fires on the newly-enabled providers.** The
  gate lives in the ``transcribe_page_tool`` handler (provider-agnostic), but the doc is clearer if
  the test explicitly walks each of the four providers. Added
  ``test_transcribe_page_gates_on_confirm_regardless_of_provider`` parametrised over ``anthropic`` /
  ``openai`` / ``google`` / ``ollama``; each case asserts draft.pages[0].text stays untouched +
  image + layout stay intact when ``confirm`` returns False.

### Tests

- 2 new translator invariant pins (OpenAI + Ollama tool_result defensive handling). - 4 parametrised
  cases of ``test_transcribe_page_gates_on_confirm_regardless_of_provider``. - 554 tests green (was
  548).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

### Refactoring

- **agent_tools**: Extract helpers to tame three S3776 hotspots
  ([#53](https://github.com/mfozmen/littlepress-ai/pull/53),
  [`ba92ed4`](https://github.com/mfozmen/littlepress-ai/commit/ba92ed4e78a87ccb990856ad86c52e3e75707914))

* refactor(agent_tools): extract helpers to tame three S3776 hotspots

Three of the eight remaining ``python:S3776`` cognitive-complexity findings all lived in
  ``src/agent_tools.py`` tool-factory handlers. Pure extract-function refactor (same pattern used on
  ``set_cover_tool`` / ``skip_page_tool`` / ``_render_message`` earlier); behaviour unchanged,
  existing tests cover every branch.

### Handlers refactored

**``read_draft_tool::handler`` (complexity 20 → under 15)**

- ``_read_draft_header_lines`` — the title / author / cover / page-count opener. -
  ``_read_draft_page_lines`` — per-page line composition, also collects the ``[image-only]`` indices
  it tagged. - ``_build_image_only_note`` — the single summary NOTE preserve-child-voice depends on,
  built in one place.

**``transcribe_page_tool::handler`` (complexity 19 → under 15)**

- ``_parse_transcribe_input`` — page-number + image guard + ``keep_image`` extraction, returns a
  uniform ``(page_n, page, keep_image, error)`` tuple. - ``_call_vision_for_transcription`` — LLM
  call with narrow-then-generic exception handling, truncates error bodies to 200 chars so an SDK
  that interpolates the base64 payload into a message can't echo the image back at the agent. -
  ``_interpret_vision_reply`` — empty-reply + ``<BLANK>`` sentinel branches as a single early-return
  helper. - ``_apply_transcription`` — the final write: either clear + ``text-only`` (default
  Samsung-Notes path) or preserve image (``keep_image=True`` mixed-content path).

**``generate_cover_illustration_tool::handler`` (complexity 17 → under 15)**

- ``_parse_generate_cover_input`` — prompt + quality + style validation in one pass. -
  ``_build_generate_cover_confirm_prompt`` — the pricing-aware y/n copy. -
  ``_apply_generated_cover`` — cover-image + style write after approval.

### Not in this PR

The five remaining ``python:S3776`` findings all live in ``src/providers/llm.py``
  (``_messages_to_gemini_contents``, ``_messages_to_openai``, ``_messages_to_ollama``, and the two
  ``turn()`` methods). Each provider has a different wire format and these translators are easy to
  get subtly wrong; next PR ships them on their own so review stays focused.

### Verification

- All 528 tests green. No behaviour changes. Every refactor is pure extract-function; the
  agent-facing replies and the persisted draft state are identical byte-for-byte.

### PLAN.md

Backlog entry tightened: was "6 remaining" (stale), now "5 remaining" in llm.py with the hotspots
  named.

* fix(agent_tools): address PR #53 review — input guard + SRP polish

All three sub-threshold findings from the PR review.

**#1 — ``_parse_transcribe_input`` no longer crashes on malformed input.** ``int(input_["page"])``
  used to raise ``KeyError`` when the field was absent and ``ValueError`` on ``"2nd"``, and the
  exception escaped past the tool boundary into the agent turn. Mirrors the guard PR #48 review #11
  added on ``_parse_skip_page_input``: missing key → tool-result string, non-integer → tool-result
  string. Regression test ``test_transcribe_page_handles_missing_or_bad_input_gracefully`` pins both
  branches (pre-existing bug from PR #46, never exercised with a weak-model malformed call until
  now).

**#2 — ``_read_draft_page_lines`` is now pure.** Signature changes from ``(draft, lines) ->
  list[int]`` to ``(draft) -> tuple[list[str], list[int]]``; the caller does
  ``lines.extend(page_lines)``. Removes the mixed in/out-parameter + return shape. Cosmetic but
  mirrors the shape of ``_read_draft_header_lines`` (pure return) so the two helpers read together.

**#3 — restored the "why the tag is compact" rationale at the call site.** Added a short comment
  above the ``_read_draft_page_lines`` call in ``read_draft_tool``'s handler pointing at
  ``_build_image_only_note`` for the full explanation. The read-through-at-a-glance is back without
  duplicating the docstring.

Still 529 tests green (was 528). Only new test is the input guard; the SRP polish and comment
  restoration are covered by the existing ``read_draft`` suite.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

- **llm**: Split provider translators to close the S3776 backlog
  ([#54](https://github.com/mfozmen/littlepress-ai/pull/54),
  [`9fdaf1e`](https://github.com/mfozmen/littlepress-ai/commit/9fdaf1e3f3f79ea68d12799b735551f3aac1580e))

* refactor(llm): split provider translators to close S3776 backlog

The last five ``python:S3776`` cognitive-complexity findings all lived in ``src/providers/llm.py`` —
  three message translators (Anthropic → provider) and two response translators (provider →
  Anthropic). Each provider has a different wire format; this PR ships them on their own so review
  stays focused, and every split is a pure extract-function with the existing per-provider test
  suite as a safety net.

### Translators parcelled out

**``_messages_to_openai`` (32 → under 15)**

- ``_openai_assistant_message`` collapses Anthropic blocks on an assistant message into one OpenAI
  assistant message (text concatenates, tool_use → tool_calls with JSON-string arguments). -
  ``_openai_user_messages`` expands user-message blocks into the one-``role: tool``-per-result
  sequence OpenAI expects.

**``_messages_to_ollama`` (43 → under 15)**

- ``_ollama_assistant_message`` for the dict-arguments, id-less tool_calls shape. -
  ``_ollama_user_messages`` for the name-correlated tool-result shape (Ollama keys by ``tool_name``,
  not ``tool_call_id``). - ``_build_tool_use_id_to_name_map`` lifted out as a shared helper (Gemini
  and Ollama both need this lookup).

**``_messages_to_gemini_contents`` (31 → under 15)**

- ``_gemini_parts_from_blocks`` translates one message's block list to a list of ``Part``s + a flag
  saying whether any ``tool_result`` appeared. - ``_gemini_role_for_message`` maps Anthropic's
  two-role world + tool flag to Gemini's three roles. - Uses the shared
  ``_build_tool_use_id_to_name_map``.

**``_openai_completion_to_blocks`` (~19 → under 15)**

- ``_openai_tool_use_block`` for one ``tool_call`` → one ``tool_use`` block. -
  ``_openai_finish_reason_explanation`` for the synthetic "[OpenAI stopped with reason: …]" text
  that surfaces non-standard finishes (length / content_filter) to the user.

**``_ollama_response_to_blocks`` (~18 → under 15)**

- ``_ollama_tool_use_block`` for one ``tool_call`` → one ``tool_use`` block (synthesises an id since
  Ollama doesn't issue one). - ``_parse_ollama_tool_arguments`` normalises the dict-or-string
  arguments shape with the ``__raw`` fallback on malformed JSON.

### Verification

- All 529 tests green. No behaviour changes; every refactor is pure extract-function covered by the
  pre-existing provider tests in ``tests/test_llm_providers.py`` (55 tests, every translator path
  exercised).

### PLAN.md

SonarCloud backlog item removed — all 12 original S3776 findings cleared across PRs #45, #53, and
  this one.

* fix(llm): address PR #54 review + new-code coverage on the helpers

Three sub-threshold review findings plus a dedicated coverage sweep of the extract-function helpers
  PR #54 introduced. Full coverage rose from 98% → 99% and ``src/providers/llm.py`` from 95% → 98%
  (19 uncovered lines → 7).

### Review findings

1. **``_build_tool_use_id_to_name_map`` silently changed Gemini semantics.** Pre-refactor Gemini
  guarded on ``"id" in block`` and skipped id-less ``tool_use`` blocks; pre-refactor Ollama didn't.
  The shared helper landed on Ollama's looser pattern by default, so an id-less block would write
  ``id_to_name[""] = name`` and a later ``tool_result`` with a missing ``tool_use_id`` would
  silently resolve to that name. Guard restored — id-less blocks and blocks with ``id == ""`` are
  skipped. New test ``test_tool_use_map_skips_tool_use_blocks_without_an_id`` pins the behaviour so
  a later refactor can't drop the guard again.

2. **``_parse_ollama_tool_arguments`` annotated ``-> dict`` but returned non-dicts.** When Ollama
  handed back a string like ``"null"`` / ``"42"`` / ``"[1,2,3]"``, ``json.loads`` returned ``None``
  / ``int`` / ``list``. The agent loop wraps the result as ``{"input": args}`` and expects a dict —
  a non-dict value crashed dispatch. Non-dict JSON now falls back to ``{"__raw": raw_args}`` the
  same way malformed JSON does. Pinned by the parametrised
  ``test_parse_ollama_tool_arguments_handles_every_shape``.

3. **``import json`` / ``import uuid`` inside per-call helpers** — exactly the Sonar S1128 the PR
  was closing. Hoisted both to module scope (both are used elsewhere in the file).

### Coverage sweep

Added ``tests/test_llm_translator_helpers.py`` with 15 directed unit tests on the extract-function
  helpers that the higher-level provider tests don't reach:

- id→name map: id-less skip, non-assistant / non-list filter - Gemini role mapping: default
  ``model``, tool-result wins over role, user passthrough - OpenAI user messages: text branch,
  unknown-block skip - OpenAI tool-use block: malformed JSON → ``__raw``, missing ``function`` attr
  graceful fallback - OpenAI completion: empty choices → end_turn - Unknown role fallthrough on both
  ``_messages_to_openai`` and ``_messages_to_ollama`` - Ollama response: no-message branch - Ollama
  tool-use block: synthesised id + arg passthrough - ``_parse_ollama_tool_arguments``: None / empty
  / JSON / dict / malformed / non-dict-JSON (six shapes in one parametrised test)

544 tests green (was 529).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.6.0 (2026-04-18)

### Chores

- **release**: 1.6.0 [skip ci]
  ([`4f40b73`](https://github.com/mfozmen/littlepress-ai/commit/4f40b739e21872d12e9895aebd6c08e1e1150d8d))

### Features

- **agent**: Render_book message names each output file's role
  ([#52](https://github.com/mfozmen/littlepress-ai/pull/52),
  [`c72acc4`](https://github.com/mfozmen/littlepress-ai/commit/c72acc4fd78a6ee2ac648fa2a93309d64f0e1bc8))

* feat(agent): render_book message names each output file's role

P6 — the last Yavru Dinozor second-run feedback item. A single render drops four PDFs (stable +
  versioned × A5 + booklet) by design (PR #30), but the Yavru-Dinozor run read four files as "why is
  this producing so much stuff?" because the success message named paths without naming roles.

Tightens the two message helpers so each file's job is explicit:

- **A5 stable** — "this is the file to open and read" + the viewer-open tail ("and opened it in your
  viewer" / "Open it manually …"). - **A4 booklet** — "print this one double-sided (flipped on short
  edge), fold in half, staple the spine." - **A5 snapshot** (``.v1.pdf``) — "rollback only, safe to
  ignore unless you want to compare with a later render." - **Booklet snapshot**
  (``.v1_A4_booklet.pdf``) — same framing.

No behaviour change — just user-facing copy. The ``_render_message`` and ``_impose_and_mirror``
  helpers now carry the role narration; the versioned-snapshot test was already pinning the
  "snapshot name must appear" invariant and still passes against the new copy.

### Tests

- New ``test_render_book_message_explains_the_role_of_each_output_file`` pins: "open" or "read"
  mention for A5; "print" + "double-sided"

+ "fold" + "staple" for the booklet; "snapshot" + "ignore" (or "safe to ignore" / "rollback") for
  the two versioned copies. - ``test_render_book_viewer_failure_is_non_fatal`` accepts either the
  old ("Wrote A5 book") or new ("A5 book written") opener so the test doesn't pin a single phrasing.

526 tests green (was 525).

### PLAN.md

All six Yavru-Dinozor-second-run items shipped; the section is closed out and collapsed back into
  the regular Next-up list.

* fix(agent): address PR #52 review — grammar + test tightening

Four sub-threshold findings, all valid.

1. **Grammar glitch on the common success path.** With ``opened=True``, the message read "…open and
  read and opened it in your viewer" — two conjoined ``and`` clauses with a past-tense shift.
  Restructured ``opened_tail`` so it's its own sentence ("Opened it in your viewer." / "Open it
  manually — couldn't launch a PDF viewer here."), and moved the period inside the A5 role line so
  the seam reads clean.

2. **Loose test assertions.** ``"open"`` in result also matched ``"opened it in your viewer"`` and
  ``"is it open in a PDF viewer?"``; ``"read this"`` never appeared in the code; the snapshot
  assertion had a dead third disjunct (``"ignore"`` is subsumed by ``"safe to ignore"``). The
  loosened viewer-failure assertion's ``"Wrote A5 book"`` branch was also dead (HEAD no longer uses
  that opener). Tightened every role-naming check to a multi-word marker:

- ``"to open and read"`` (A5 role) - ``"print this one double-sided"`` (booklet role) - ``"rollback
  only"`` + ``"safe to ignore"`` (snapshot role)

3. **Snapshot framing inconsistency.** The A5 snapshot line carried the ``"compare with a later
  render"`` hedge; the booklet snapshot line dropped it. Added the hedge to both so the same feature
  reads the same way in one reply. New test pins this — ``result.count("compare with a later
  render") == 2``.

4. **``impose=False`` branch was untested.** The previous test only ran ``{"impose": True}``. New
  test pins the A5-only path: role still named, snapshot still named, AND the booklet / print / fold
  / staple copy does NOT leak.

- ``test_render_book_message_explains_the_role_of_each_output_file`` tightened. - New
  ``test_render_book_message_names_a5_role_without_booklet_when_impose_false`` — positive + negative
  assertions on the A5-only path. - New
  ``test_render_book_snapshot_framing_consistent_across_a5_and_booklet`` — the hedge appears twice
  per reply. - ``test_render_book_viewer_failure_is_non_fatal`` dropped its dead ``"Wrote A5 book"``
  disjunct.

528 tests green (was 526).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.5.0 (2026-04-18)

### Chores

- **release**: 1.5.0 [skip ci]
  ([`190bbc7`](https://github.com/mfozmen/littlepress-ai/commit/190bbc70eb85856bed57a5e50101c629cada1026))

### Features

- **agent**: Metadata review step + back-cover blurb prompt
  ([#51](https://github.com/mfozmen/littlepress-ai/pull/51),
  [`b2c9b11`](https://github.com/mfozmen/littlepress-ai/commit/b2c9b1120e480311fe08486c9ee2ffb6ea7703b0))

* feat(agent): metadata review step + back-cover blurb prompt

P5 from the Yavru Dinozor second-run feedback. The live run dropped both beats: the agent never
  asked for a back-cover blurb, and it moved straight from the last layout into ``render_book``
  without giving the user a chance to catch a typo in the title / author / cover pick.

Greeting-only change, no new tools. Two new paragraphs after the cover-options block:

1. "Ask the user for a short back-cover blurb (one or two sentences about what the book is about, in
  the child's voice — set_metadata with field='back_cover_text'). Leave empty only if the user
  explicitly says they don't want one."

2. "Once title, author, cover, layouts, and back-cover text are all set, SUMMARISE the metadata back
  to the user and ask them to approve or correct any of it BEFORE rendering. Call read_draft again
  if you need to re-check the state. Do NOT jump straight from the last layout to render_book — the
  review step is the user's last chance to catch a typo before it lands in the printed PDF."

No new tool needed — ``read_draft`` already returns the full state, so the agent re-reads rather
  than taking a new "review_metadata" tool round.

### Tests (2 new; 522 total, was 520)

- ``test_greeting_includes_metadata_review_step_before_layouts`` — pins the review + approve beat,
  with independent asserts on the "review / summarise" wording AND the "approve / confirm / ask
  them" wording so a rewrite can't keep one without the other. -
  ``test_greeting_asks_for_back_cover_blurb`` — pins both the back-cover prompt and the "short
  blurb" framing so the agent doesn't push for a full-length description.

### PLAN.md

P5 moved out of Next-up; Shipped row added.

* fix(repl): address PR #51 review — child-voice guard on back cover + README

Six findings: two critical (preserve-child-voice guard missing on the back-cover path, README not
  updated), four sub-threshold tightening items.

### Critical

1. **Back-cover blurb paragraph advertised ``set_metadata`` with ``field='back_cover_text'`` without
  a preserve-child-voice guard.** CLAUDE.md explicitly names back-cover text as child-authored. The
  greeting's "in the child's voice" was ambiguous — a primed LLM reads it as permission to compose a
  blurb *in the child's style* rather than to transcribe what the user types. ``set_metadata`` has
  no confirm gate for ``_CHILD_VOICE_FIELDS``, so the greeting is the only enforcement surface.
  Mirrored the AI-cover guard:

> PRESERVE-CHILD-VOICE: the back cover is child-authored. > Record the user's exact words verbatim —
  do NOT invent, > paraphrase, or 'improve' the blurb yourself.

2. **README not updated.** New user-visible behaviour on this PR (the back-cover blurb prompt, the
  final review checkpoint, combined with P4 from last PR which also hadn't landed in the README).
  Three new Status bullets cover: series question, back-cover blurb (with the verbatim note), and
  the final review step (with the verbatim quoting).

### Sub-threshold

3. **Render ordering inconsistency.** Greeting said "review after layouts, before render", test
  docstring said "before the layout step", removed PLAN line said "after metadata". Picked one
  (layouts → summarise → render) and pinned it with a regex assertion
  ``re.search(r"layout.*summaris.*render", hint)``.

4. **"SUMMARISE the metadata" risked loose translation in non-English sessions.** Title and author
  are child-authored; a Turkish session can drift during the summary. Added: "Quote title, author,
  and back-cover text VERBATIM from what the user stored — do NOT translate or paraphrase them
  during the summary even if you've switched languages." New test pins the verbatim wording.

5. **Back-cover blurb test accepted lone ``"short"`` keyword** — tightened to require multi-word
  phrases (``"short blurb"`` / ``"one or two sentences"``) so a rewrite that drops the framing
  doesn't pass vacuously.

6. **``render_book`` has no confirm gate — the review step is purely agent-instruction.**
  Acknowledged in this PR as agent-instruction-only; a ``confirm`` gate on ``render_book`` would
  change the render UX broadly and belongs in its own PR. The greeting is the enforcement surface
  for the review step, backed by the five regex/keyword pins in ``test_agent_greeting.py``.

### Tests (3 new, 3 tightened — 525 total, was 522)

- ``test_greeting_back_cover_bullet_carries_preserve_child_voice_guard`` — Finding #1. -
  ``test_greeting_review_step_comes_before_render_and_after_layouts`` — Finding #3 (regex-ordered).
  - ``test_greeting_summarise_step_demands_verbatim_read_back`` — Finding #4. -
  ``test_greeting_asks_for_back_cover_blurb`` tightened to require multi-word phrases (Finding #5).
  - Existing review / recap test renamed to
  ``test_greeting_includes_metadata_review_step_before_render`` to match the pinned ordering.

README updated with three new Status bullets (series question, back-cover blurb, final review
  checkpoint).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.4.0 (2026-04-18)

### Chores

- **release**: 1.4.0 [skip ci]
  ([`f304c9d`](https://github.com/mfozmen/littlepress-ai/commit/f304c9dc47e89480f1b3e759ad6d0aad00723c55))

### Features

- **agent**: Always ask the series question, every book
  ([#50](https://github.com/mfozmen/littlepress-ai/pull/50),
  [`0a53a53`](https://github.com/mfozmen/littlepress-ai/commit/0a53a5351b7971b7502e29a4670c9297cdfae753))

P4 from the Yavru Dinozor second-run feedback. The maintainer's call: ask *every* book whether it's
  part of a series, not only

when the title happens to match a pattern — the user is the source of truth, and "Yavru Dinozor - 1"
  is book 1 of a series Poyraz plans to continue.

Greeting-only change. No new data fields on ``Draft`` / ``Book``: the user records the answer inside
  the title they set (e.g. ``Yavru Dinozor - 1``), which the existing cover renderer already lays
  out correctly. Saves a round-trip through ``set_metadata`` for a value that only shows up on the
  cover as part of the title anyway.

Adds to ``_AGENT_GREETING_HINT`` after the "do NOT ask a long list of questions up front" line:

ALWAYS ask the user whether this book is part of a series — every book, regardless of what the title
  looks like (don't try to infer 'yes' from seeing '- 1' or 'Book 2' in the title; the user is the
  source of truth). If the answer is yes, follow up with the volume number ('which book in the
  series is this?'). Have the user record that in the title when they set it (e.g. ``Yavru Dinozor -
  1``) so the cover renderer picks it up naturally.

### Tests (2 new; 520 total, was 518)

- ``test_greeting_always_asks_whether_the_book_is_a_series`` pins the "every book, regardless"
  behaviour — rejects a rewrite that would scope the question to a title pattern. -
  ``test_greeting_asks_for_volume_number_when_series_answer_is_yes`` pins the follow-up question so
  the agent doesn't drop half the interaction.

### PLAN.md

P4 moved out of Next-up; Shipped row added.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.3.0 (2026-04-18)

### Chores

- **release**: 1.3.0 [skip ci]
  ([`42f749b`](https://github.com/mfozmen/littlepress-ai/commit/42f749b1ca2d3dcde6ab2736a13e46625e1f1e5d))

### Features

- **agent**: Surface AI cover + poster as first-class cover options
  ([#49](https://github.com/mfozmen/littlepress-ai/pull/49),
  [`8a6b92d`](https://github.com/mfozmen/littlepress-ai/commit/8a6b92da74e719cde361f72d996c827d94d45ed4))

* feat(agent): surface AI cover + poster as first-class cover options

P3 from the Yavru Dinozor second-run feedback. On the live run Claude defaulted to "which page's
  drawing do you want for the cover?" without ever mentioning the ``generate_cover_illustration``
  tool or the ``poster`` type-only fallback — even though both are fully wired up. The user had to
  know the options existed and ask for them by name.

Tightens ``_AGENT_GREETING_HINT`` with an explicit "at the cover step, always offer all three
  options" block:

(a) reuse a page drawing — ``set_cover`` with a page number, (b) generate an AI cover —
  ``generate_cover_illustration`` (OpenAI-only; on other providers, tell the user to switch via
  ``/model``), (c) poster — type-only cover, ``set_cover`` with ``style='poster'``.

Three new tests in a new ``tests/test_agent_greeting.py`` pin the invariants so future greeting-hint
  tweaks can't silently drop one:

- ``test_greeting_mentions_cover_step_and_its_three_options`` -
  ``test_greeting_flags_openai_only_gate_for_ai_cover`` -
  ``test_greeting_still_asks_agent_to_read_draft_first`` (regression guard on the pre-existing "call
  read_draft first" behaviour — the rewrite could have dropped it)

No production-code path changes outside the hint string. 514 tests green (was 511).

PLAN.md: moved P3 out of Next-up, added a Shipped row for this PR (placeholder PR number to be
  backfilled on merge).

* fix(repl): address PR #49 review — guardrails on the cover-step hint

Five findings, one critical preserve-child-voice echo and four polish items.

### Critical

1. **Greeting advertised ``generate_cover_illustration`` without carrying the PRESERVE-CHILD-VOICE
  guard that lives on the tool's own description.** On Anthropic / Gemini / Ollama sessions the tool
  isn't registered, so its description is invisible and the greeting is the only surface that names
  the AI cover path on those sessions. Without the echo, an agent following the greeting could
  switch to OpenAI via ``/model`` and prompt the image API with paraphrased child text — defeating
  the PR #41 review round. The option (b) bullet now carries the guard verbatim:

> PRESERVE-CHILD-VOICE still applies on this path: describe the > cover scene in your OWN words from
  the story's themes — do > NOT quote or paraphrase the child's page text into the image > prompt.

### Sub-threshold

2. **``/model`` switch suggestion glossed over the OpenAI key prompt.** Adding: "warn them they'll
  be prompted for an OpenAI API key on first switch if one isn't already stored in the OS keychain."

3. **Hint mixed English slash-command tokens with a language-switch instruction.** A literal-minded
  LLM on a Turkish session could translate ``/model`` / ``/render``. Added a clause to the
  language-switch line:

> keep slash commands like /model /render /load literal — they > are REPL tokens, do NOT translate
  them.

4. **Tests pinned loose keyword substrings, not the invariants they claimed.**
  ``test_greeting_flags_openai_only_gate_for_ai_cover`` used ``"openai" in lowered or "/model" in
  lowered`` — a rewrite that kept one of the two would still pass. Split into two independent
  assertions. Other tests tightened to require tool names (``generate_cover_illustration``) and
  explicit option enumeration markers ("(a)", "(b)", "(c)") so deleting a bullet can't slip through.

5. **``poster`` was framed as one of three top-level cover paths, misleading the LLM.** The three
  real axes are "where the drawing comes from" (page / AI / none); the five templates
  (``full-bleed`` / ``framed`` / ``portrait-frame`` / ``title-band-top`` / ``poster``) are an
  orthogonal style axis. Option (a) now points at the ``select-cover-template`` skill explicitly so
  the middle three templates stay in scope.

### Tests (4 new, 3 tightened — 7 total greeting pins)

- ``test_greeting_echoes_preserve_child_voice_guard_for_ai_cover`` — Finding #1. -
  ``test_greeting_warns_about_openai_key_prompt_on_model_switch`` — Finding #2. -
  ``test_greeting_marks_slash_commands_as_non_translatable`` — Finding #3. -
  ``test_greeting_option_a_points_at_select_cover_template`` — Finding #5. - Finding #4: the three
  existing tests now take independent assertions (``openai`` AND ``/model``, tool name
  ``generate_cover_illustration``, enumeration labels "(a)"/"(b)"/"(c)").

518 tests green (was 514).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.2.2 (2026-04-18)

### Bug Fixes

- **agent**: Drop source image after OCR + skip_page tool — end of the duplicate-text bug
  ([#48](https://github.com/mfozmen/littlepress-ai/pull/48),
  [`400af87`](https://github.com/mfozmen/littlepress-ai/commit/400af876da236bfb863b550e035007bdb5d18b10))

* fix(agent): drop source image + skip_page tool — end of the duplicate-text bug

Second-run Yavru Dinozor feedback split into six items in ``docs/PLAN.md``. This PR ships the two
  that were actively making the rendered book wrong.

### P1 — Duplicate text on Samsung-Notes pages

When a PDF carries each page as a single PNG that contains *both* the child's text and the
  illustration (phone-scan / Samsung Notes exports), running ``transcribe_page`` used to leave
  ``page.image`` in place. The renderer then printed the OCR'd text *and* the image that already
  contained the same text — so every page showed the story twice.

On confirmed OCR, the tool now:

- writes the cleaned reply into ``page.text``, as before, - **clears** ``page.image`` (the text is
  already in ``page.text`` and keeping the image would double-print it), - sets ``page.layout =
  "text-only"`` so the renderer uses the text-only path.

The confirm prompt surfaces the trade-off explicitly:

> Approving also removes the source image on this page and switches > its layout to text-only — this
  avoids the renderer printing the > text twice (once inside the image, once as the page's text). An
  > AI-generated replacement illustration is a future option > (``generate_page_illustration``).

Illustration recovery is the ``generate_page_illustration`` item now listed under "Explicitly
  deferred" in ``docs/PLAN.md`` — same surface as ``generate_cover_illustration`` but writes to a
  page.

### P2 — ``skip_page`` tool

Samsung Notes trails 2-3 blank pages on most exports. PR #47's ``<BLANK>`` sentinel correctly flags
  them, but they stayed in ``draft.pages`` and both ``propose_layouts`` and the renderer treated
  them as real pages — printed blank spreads the child never meant to include.

New ``skip_page(page: int)`` tool removes a page from ``draft.pages`` after a y/n confirmation.
  Renumbers subsequent pages so later tool calls (``choose_layout``, ``set_cover``) keep referencing
  pages the way the user counts them. The confirm prompt shows whether the page has a drawing and a
  text preview so the removal is never surprise-y.

Registered in ``src/repl.py`` on every provider (no provider gate — the tool is pure draft editing,
  no external call).

### Tests (9 new, 503 total, was 494)

Transcribe (3): - ``test_transcribe_page_clears_image_and_sets_text_only_on_accept`` -
  ``test_transcribe_page_confirm_prompt_warns_about_image_replacement`` -
  ``test_transcribe_page_declined_keeps_image_and_layout_intact``

Skip-page (6): - ``test_skip_page_requires_draft`` - ``test_skip_page_rejects_out_of_range`` -
  ``test_skip_page_asks_for_confirmation_with_page_context`` -
  ``test_skip_page_declined_leaves_draft_unchanged`` -
  ``test_skip_page_confirmed_removes_page_and_renumbers`` (pins the shift-down behaviour so later
  tool calls don't target the wrong page) - ``test_skip_page_schema_requires_page``

### Live verification

Re-ran the OCR demo against Yavru Dinozor. Before: 8 pages, five with duplicated text (image + OCR),
  three blanks tagged ``image-only`` but still rendered. After: 5 clean ``text-only`` pages (1-5
  transcribed verbatim), pages 6-8 removed from the draft before rendering. The PDF opens with a
  clean five-page Turkish book.

### PLAN.md

Added the six Yavru-Dinozor-second-run items. P1+P2 shipped here; P3 (AI cover surfacing), P4
  (series + volume number question), P5 (metadata review + back-cover prompt), and P6 (render-output
  message) tracked for their own PRs. ``generate_page_illustration`` added to "Explicitly deferred"
  as the restore path for illustrations dropped by P1.

* fix(agent): address PR #48 review — preserve-child-voice guardrails

Eleven findings from the PR review: four critical preserve-child-voice / docs issues and seven
  sub-threshold polish items. Addressed in a single pass.

### Critical

1. **``transcribe_page`` was destroying drawings on mixed-content pages.** The original fix was
  right for Samsung Notes exports (pure text screenshots) but the project also targets scanned
  handwriting + drawings, where the same page image carries both text and a child's sketch. Added a
  ``keep_image: bool`` tool input (default ``False``, preserving the Samsung-Notes default). When
  the agent knows the image carries a drawing, it passes ``keep_image=true`` and the tool writes
  ``page.text`` without touching ``page.image`` or ``page.layout``. The confirm prompt names the
  destruction risk explicitly on the default path ("Any drawing on this page will also be lost") and
  names the alternative ("call this tool with ``keep_image=true`` instead").

2. **``docs/PLAN.md`` was not trimmed.** Moved P1 and P2 out of "Yavru Dinozor second-run feedback"
  under "Next up", added Shipped-table rows for PR #47 (blank-sentinel filter) and this PR.

3. **README missing the tool changes.** The ``transcribe_page`` bullet now names the image-clearing
  + layout-reset side effect and the ``keep_image`` escape hatch; added a new bullet describing
  ``skip_page`` for the blank-page cleanup flow.

4. **Module top docstring claimed an invariant that's no longer true.** "No tool rewrites page text
  freely" was literally false after PR #46 + #48. Rewrote to describe the actual contract: every
  page-state mutation is gated behind a ``confirm`` callback; lists the five tools that carry the
  gate today (``propose_typo_fix``, ``transcribe_page``, ``skip_page``, ``propose_layouts``,
  ``generate_cover_illustration``).

### Sub-threshold

5. **``skip_page`` drawing warning was a status label, not a warning.** ``drawing: yes`` → when the
  page has an image, the prompt now spells out that removal is permanent and the draft-level image
  reference is lost.

6. **``skip_page`` decline path invented tools.** The old suggestion named ``move_content`` and
  "mark as back cover" — neither exists. Narrowed to paths that actually exist: keep as a blank
  spread, or have the user type text in the conversation.

7. **``read_draft`` description didn't name ``skip_page``.** Added: "When ``transcribe_page``
  reports a page looks blank, confirm with the user and call ``skip_page`` to drop it."

8. **``transcribe_page`` description didn't mention the image-drop side effect.** Added an explicit
  SIDE EFFECT paragraph so the LLM knows not to reach for this tool on mixed-content pages without
  ``keep_image=true``.

9. **CLAUDE.md architecture bullet didn't list ``transcribe_page`` or ``skip_page``.** Extended the
  bullet + updated the preserve-child-voice line to describe the real contract.

10. **``skip_page`` confirm named a non-existent page on the last page.** "Page N+1 becomes page N"
  is only true when there *is* a page N+1. Guarded with ``if page_n < len(draft.pages):`` so
  last-page removal prints a neutral "Approve the removal?" line with no fictional renumber claim.

11. **``skip_page`` crashed the agent turn on malformed input.** ``int(input_["page"])`` raised
  ``KeyError`` / ``ValueError`` to the caller; every other tool in this file guards input. Now
  returns tool-result strings for missing / non-integer ``page``.

### Tests (8 new; 511 total, was 503)

- ``test_transcribe_page_keep_image_flag_preserves_mixed_content_page`` — Finding #1. -
  ``test_transcribe_page_confirm_prompt_warns_about_drawing_destruction`` — Finding #1 (warning
  wording), strict assertion on "any drawing will / drawing will be lost" phrasing so a later change
  can't regress the warning into a vague "future option" aside. -
  ``test_transcribe_page_description_mentions_image_side_effect`` — Finding #8. -
  ``test_skip_page_confirm_warns_explicitly_when_page_has_drawing`` — Finding #5. -
  ``test_skip_page_decline_suggestion_does_not_invent_tools`` — Finding #6 (explicit
  ``move_content`` / "mark as back cover" absence checks). -
  ``test_skip_page_last_page_confirm_does_not_promise_renumber`` — Finding #10. -
  ``test_skip_page_handles_missing_or_bad_input_gracefully`` — Finding #11 (missing key +
  non-integer value). - ``test_read_draft_description_names_the_skip_page_tool`` — Finding #7.

* refactor(agent_tools): extract skip_page prompt builders to tame complexity

Sonar finding on PR #48: ``skip_page_tool::handler`` hit cognitive complexity 21 (limit 15) after
  the review-fix round added input guards, a drawing-destruction warning, a last-page renumber
  guard, and a narrower decline suggestion.

Pure extract-function refactor, same pattern used on ``set_cover_tool::handler`` in PR #45. Split
  into:

- ``_parse_skip_page_input`` — grabs ``page`` from the input dict, handles the missing-key /
  non-integer / out-of-range cases, returns ``(page_n, error)`` so the handler can branch once. -
  ``_build_skip_page_prompt`` — composes the confirm prompt from three one-line helpers. -
  ``_skip_preview_line`` / ``_skip_drawing_line`` / ``_skip_renumber_line`` — one decision each; the
  destruction warning and last-page guard from the review round live here now.

Handler is down to: draft guard → parse → build → confirm → mutate. No behaviour change, existing
  tests pass. 511 green.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

### Chores

- **release**: 1.2.2 [skip ci]
  ([`960ee43`](https://github.com/mfozmen/littlepress-ai/commit/960ee4363d4670bb1efe0a389ea9f02c4519a783))


## v1.2.1 (2026-04-18)

### Bug Fixes

- **agent**: Transcribe_page rejects blank-image meta-responses
  ([#47](https://github.com/mfozmen/littlepress-ai/pull/47),
  [`02be7e0`](https://github.com/mfozmen/littlepress-ai/commit/02be7e0860c25bc0e966da2a00f6546403ac50d9))

* fix(agent): transcribe_page rejects blank-image meta-responses

Live test finding (Yavru Dinozor, 8-page Samsung Notes PDF with 5 pages of story + 3 trailing
  blanks): Claude vision honestly replies in English — *"The image appears to be completely
  blank/white with no visible text to transcribe."* — when the page carries no text rather than
  fabricating a transcription. The previous implementation treated those acknowledgements as
  successful OCR output and wrote the English meta-response verbatim into ``page.text``, so the
  printed book would have had three pages reading "The image appears to be completely blank/white…"
  instead of the clean trailing blanks the user expected.

Filter added to ``transcribe_page_tool`` right after the empty-reply guard: if the cleaned reply
  matches any of the known blank-image meta-phrases (``appears to be blank``, ``appears to be
  completely blank``, ``no visible text``, ``no text to transcribe``, ``cannot transcribe``, ``is
  completely blank``, ``appears to be empty``, ``there is no text``), the draft is left untouched
  and the agent gets a clear signal — "Page N looks blank to the vision model; ask the user whether
  this page was meant to be empty (trailing blank) or whether they want to skip it / mark it as the
  back cover." No user confirmation round-trip for this path because nothing is being written; the
  earlier confirm gate only runs when we have real text to propose.

False-positive coverage: the filter matches the meta-acknowledgement shape, not the word "blank" or
  "empty" in isolation — a child's story that says "The page was blank until the dragon drew a moon
  on it" still transcribes. Three new tests:

- ``test_transcribe_page_rejects_blank_image_meta_response`` pins the exact Yavru Dinozor case (full
  English acknowledgement string). - ``test_transcribe_page_rejects_varied_blank_phrases`` iterates
  four representative phrasings Claude produces for blank pages — a later rewrite can't silently
  regress on one. - ``test_transcribe_page_does_not_reject_normal_text_with_word_blank`` guards
  against false positives on story text that contains the trigger word.

491 tests green (was 488). Companion workaround in the local ``.book-gen/demo_ocr.py`` removed; the
  tool now handles this correctly without a caller-side filter.

* fix(agent): switch blank-page filter to <BLANK> sentinel

PR #47 review surfaced three related gaps in the prose-pattern filter shipped in the original commit
  on this branch:

1. **English-only + incomplete.** The 8-phrase list missed real variants (``I don't see any text``,
  ``nothing is written on this page``, ``the page is blank`` — which didn't match the "appears to
  be" prefix requirement), and skipped Turkish entirely even though Yavru Dinozor is Turkish. Every
  additional language / variant would need another phrase. 2. **False-positive test passed for the
  wrong reason.** The fixture was "The page was blank until the dragon…" which didn't contain any of
  the 8 listed phrases, so the test couldn't have caught a regression to "fail on any mention of
  'blank'". 3. **Substring ``cannot transcribe`` could eat hedged transcriptions.** "I cannot
  transcribe the last line with full confidence, but the rest reads: '…'" matched the filter and the
  real reply was discarded before the confirm gate ran.

One change fixes all three: replace the phrase list with a **sentinel**. The prompt now tells the
  vision model to answer blank pages with exactly ``<BLANK>`` — no prose, no explanation — and the
  filter just checks for that token (with a small amount of wrapping tolerance for backticks /
  quotes / whitespace).

Properties:

- **Language-agnostic.** Same sentinel regardless of prompt language; Turkish, English, and anything
  else collapse to one token. - **No false positives on story text.** A story line containing
  ``<BLANK>`` as a substring inside a longer sentence still transcribes normally — only a reply that
  *is* the sentinel trips the filter. - **Hedged transcriptions reach the confirm gate.** Anything
  that isn't the sentinel — including "I cannot transcribe the last line…" — goes through to the
  user's y/n prompt intact. - **Simpler.** One token, one check. The 8-phrase list is gone.

The confirm gate from PR #46 is still the secondary defence: if a non-compliant model ignores the
  sentinel instruction and emits prose instead (Gemini sometimes does this), the user sees the
  meta-response in the confirm preview and rejects it. Layered defence, each layer with a narrow
  job.

### Tests (6, replacing the 2 prose-pattern tests from the earlier commit)

- ``test_transcribe_prompt_asks_for_blank_sentinel_on_empty_pages`` pins the sentinel instruction in
  the prompt so a later refactor can't silently drop it. -
  ``test_transcribe_page_rejects_blank_sentinel_reply`` — exact sentinel → draft untouched. -
  ``test_transcribe_page_rejects_wrapped_blank_sentinel`` — five common wrappings (backticks,
  single/double quotes, surrounding whitespace, trailing newline) all recognised. -
  ``test_transcribe_page_hedged_transcription_reaches_confirm_gate`` — pins the no-auto-drop
  property for hedged real replies; the confirm gate is called, user decides. -
  ``test_transcribe_page_sentinel_approach_is_language_agnostic`` — Turkish meta-reply ("Görüntü boş
  görünüyor.") doesn't trip the tool-level filter but the confirm gate catches it; pins the
  layered-defence design. - ``test_transcribe_page_does_not_reject_normal_text_with_word_blank``
  rewritten with a fixture that actually embeds ``<BLANK>`` as a substring — now genuinely tests the
  false-positive property instead of passing vacuously (addresses review finding #2 directly).

### Live verification

Re-ran the OCR demo against the Yavru Dinozor PDF: Claude complied with the sentinel instruction for
  pages 6-8 (returned ``<BLANK>``), pages 1-5 transcribed verbatim as before. 494 tests green (was
  491).

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

### Chores

- **release**: 1.2.1 [skip ci]
  ([`22c8cae`](https://github.com/mfozmen/littlepress-ai/commit/22c8cae67aa1f0b1e082d1dd318256f1d121e02b))


## v1.2.0 (2026-04-17)

### Chores

- **release**: 1.2.0 [skip ci]
  ([`74c3b0d`](https://github.com/mfozmen/littlepress-ai/commit/74c3b0d457af9f268d77dbb7284ac1b3e293a5c3))

### Features

- **agent**: Transcribe_page tool — OCR image-only PDFs via LLM vision
  ([#46](https://github.com/mfozmen/littlepress-ai/pull/46),
  [`6ddbd4d`](https://github.com/mfozmen/littlepress-ai/commit/6ddbd4dfd6b8c2993b9d048b051f76a240bd6fa5))

* feat(agent): transcribe_page tool via LLM vision for image-only PDFs

Samsung Notes PDFs (and phone-scan exports generally) carry each page as a single PNG. No ``/Font``
  resource, no extractable text, ``pypdf`` / ``pdfminer`` / ``PyMuPDF`` all correctly return empty —
  but the child's text is clearly rendered inside the image. The previous fallback ("ask the user to
  type it") worked for a one-page smoke test and cratered as soon as a real draft showed up: nobody
  wants to retype their kid's eight-page dinosaur story by hand.

New agent tool ``transcribe_page(page: int)`` uses whatever multimodal LLM the user has already
  configured (Claude 3+, GPT-4o, Gemini 1.5+, LLaVA on Ollama) to OCR a single page. The page's
  image goes as a base64 content block alongside a preserve-child-voice prompt ("transcribe verbatim
  — do not fix, polish, or improve the wording"). The reply lands in ``draft.pages[n-1].text``; the
  agent then confirms the transcription with the user before treating it as ground truth.

Why vision rather than Tesseract: zero additional dependency, runs on the user's already-configured
  provider, handles Turkish matbaa yazısı and moderate handwriting out of the box, and the vision
  prompt can carry the preserve-child-voice rule directly (a plain OCR engine can't). Tesseract
  stays on the roadmap as an offline fallback for Ollama / NullProvider users.

### What the agent sees now

``read_draft``'s summary NOTE for image-only pages now points at the new tool explicitly: "Use the
  ``transcribe_page`` tool to OCR each flagged page via the active LLM's vision capability." The
  agent no longer has to guess or ask the user to transcribe by hand — it has a tool.

### Tests

Eight new unit tests in ``test_agent_tools.py`` covering:

- No-draft guard - Out-of-range page rejection - Imageless-page rejection (no vision round-trip
  wasted) - Prompt + image block shape (base64 source, preserve-child-voice verbatim wording,
  "child" context visible to the model) - Reply stored in ``draft.pages[n-1].text`` - LLM error →
  draft untouched + clean error message - Reply whitespace trimmed at edges only (interior line
  breaks preserved — the child's line breaks are part of their voice) - Schema requires only
  ``page`` (LLM reads this to know what to pass)

No behaviour change to existing tools; 480 tests green (was 472).

### Docs

- README.md — new Status bullet describing image-only PDFs + the ``transcribe_page`` escape hatch. -
  docs/PLAN.md — OCR item downgraded from Next-up priority to "Tesseract offline fallback" since the
  primary need is now met. Shipped row added for the new feature.

* fix(agent): address PR #46 review — close preserve-child-voice gaps

Seven findings — all valid, two of them critical safety issues.

### Critical

1. **Image content block was dropped on every provider except Anthropic.**
  ``AnthropicProvider.chat`` forwards messages to the SDK verbatim, so the base64 image arrives at
  Claude. The ``_messages_to_{gemini,openai,ollama}`` translators in ``src/providers/llm.py`` only
  handle ``text / tool_use / tool_result`` blocks and silently discard ``image``. The vision model
  on those providers saw only the text prompt and invented a transcription that then got written
  into ``draft.pages[n-1].text`` — the maximal form of a preserve-child-voice violation. Gate the
  tool to Anthropic at ``src/repl.py::_build_agent``, mirroring the OpenAI-only gate on
  ``generate_cover_illustration``. Per-provider image-block translation is deliberately deferred to
  its own PR; adding it under time pressure here risked subtle wire-format bugs.

2. **No user confirmation before ``page.text`` was overwritten.** ``transcribe_page`` was the only
  mutating tool in this module that skipped the ``confirm: Callable[[str], bool]`` gate. The
  module's own top comment says "the only way page text ever changes is propose_typo_fix, which
  requires a user y/n" — a contract this tool broke on day one. The handler now asks
  ``confirm(preview_prompt)`` with the OCR reply (and, when a user-typed transcription is already
  there, both the existing and the new text so the user sees what's being overwritten) and only
  writes on approval.

### Sub-threshold

3. ``read_draft``'s LLM-facing ``description`` still told the agent to "ask the user to transcribe"
  — updated to point at the ``transcribe_page`` tool, with an Anthropic-only caveat. 4. No image
  size guard. Samsung Notes pages at full resolution routinely exceed Anthropic's 5 MB per-image
  limit. Added ``_build_image_block`` with a Pillow ``thumbnail`` downscale to 1568 px on the long
  edge (Anthropic's recommended max) and a PNG re-encode so the media type stays consistent. 5. Bare
  ``except Exception`` lumped every failure into "may not support vision" and risked echoing
  multi-KB base64 payloads back into the agent when an SDK interpolated the request body into the
  error message. Split the catch: ``ImportError`` gets its own branch (SDK missing), everything else
  goes through a generic handler that truncates ``str(e)[:200]``. 6. Provider returns ``""`` (Google
  safety filter, OpenAI ``finish_reason=content_filter``) no longer silently blanks the page.
  Pre-check before ``confirm`` runs; agent gets a clear "provider returned empty text" signal and
  the draft is untouched. 7. ``docs/PLAN.md`` Shipped row: ``PR TBD`` → ``#46`` and the row now
  names the three preserve-child-voice guardrails.

Eight new pins in ``test_agent_tools.py`` on top of the eight the PR shipped:

- confirmation gate (declined → draft untouched) - confirm prompt shape (page number + preview) -
  overwrite warning when ``page.text`` is already populated - empty-reply guard - downscaling of
  oversized images (3000x4000 test fixture) - ``read_draft`` description points at
  ``transcribe_page``

And two new REPL-integration pins in ``test_repl_tools.py``:

- ``transcribe_page`` registered on Anthropic - ``transcribe_page`` NOT registered on OpenAI /
  Google / Ollama

Existing 8 transcribe_page tests updated to pass ``confirm`` through the factory — every call path
  exercised. 488 tests green (was 480).

- README.md — new Status bullet now names the three guardrails (Anthropic-only, verbatim prompt, y/n
  confirm) explicitly. - docs/PLAN.md — Shipped row finalised with PR number and guardrails.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

### Refactoring

- Clear easy SonarCloud issues + 3 cognitive-complexity wins
  ([#45](https://github.com/mfozmen/littlepress-ai/pull/45),
  [`37e1ab5`](https://github.com/mfozmen/littlepress-ai/commit/37e1ab567ffa7774844968a83b8f22f14229e508))

* refactor: clear easy SonarCloud issues + 3 cognitive-complexity wins

Knocks 6 of the 12 open SonarCloud findings off the backlog. The remaining 6 are all
  ``python:S3776`` (cognitive complexity) in larger provider-translation functions and are better
  handled in a dedicated follow-up PR so a single review can stay focused.

### Fixed

**Sonar-easy (3):**

- ``python:S5713`` in ``src/providers/image.py`` — dropped the redundant ``binascii.Error`` catch
  next to ``ValueError``; ``binascii.Error`` has been a ``ValueError`` subclass since 3.2, so the
  parent covers both. Removed the now-unused ``binascii`` import. - ``python:S3457`` in three places
  in ``src/agent_tools.py`` — dropped the ``f`` prefix on string fragments that carried no
  replacement field (poster-style suffix, generate-cover confirm prompt header, two render-failure
  hints). - ``python:S1172`` in ``src/agent_tools.py`` — ``_build_layout_prompt(draft, items)``
  never used ``draft``. Dropped the parameter and updated the single caller.

**Cognitive complexity (3):**

- ``src/repl.py::Repl.run`` (16 → under 15). Extracted ``_greet_if_draft_loaded`` (the
  pre-loaded-draft kick-off) and ``_read_loop`` (the main read / Ctrl-C / dispatch cycle). ``run``
  now reads as a three-beat linear script. - ``src/cli.py::main`` (17 → under 15). Extracted
  ``_load_pdf_into_repl`` (resolve path, mirror, restore or ingest) and
  ``_restore_saved_draft_or_migrate`` (saved-draft lookup plus the one-shot legacy-path migration).
  ``main``'s body is down to argparse, readline setup, repl construction, and a single guarded
  pre-load call. - ``src/agent_tools.py::set_cover_tool::handler`` (17 → under 15). Split into
  ``_validate_cover_inputs``, ``_apply_poster_cover``, and ``_apply_image_cover``. The handler is
  now five lines: draft guard → validate → dispatch.

### Verification

- All 472 tests green. No behaviour changed; every refactor is pure extract-function with existing
  test coverage continuing to guard the external contract.

### Follow-up (deliberately out of scope here)

Six remaining ``S3776`` findings, all in larger functions that deserve their own review cycle:

- ``src/providers/llm.py`` — 4 complexity-18-to-43 functions around content-block translation and
  ``turn()`` dispatch. - ``src/agent_tools.py`` — 2 more (``set_cover``-style handler refactor
  worked here; the other tool handlers likely need similar extraction).

Tracked in ``docs/PLAN.md``'s SonarCloud backlog item.

* docs(plan): trim SonarCloud backlog after six items clear

Review catch: CLAUDE.md requires trimming ``docs/PLAN.md`` in the same PR that ships the
  corresponding work, but the backlog bullet was left at its pre-PR shape ("12 open") and still
  listed the six rule-level targets this PR now closes (S5713, S3457, S1172, plus three S3776 wins
  in ``set_cover``, ``cli.main``, ``repl.run``). Updated to "6 remaining" with the surviving
  hotspots grouped by file: 5 × S3776 in ``src/providers/llm.py`` around the ``turn()``

dispatch, 1 × S3776 in ``src/agent_tools.py`` for a tool handler the extract-function pattern hasn't
  reached yet.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.1.1 (2026-04-17)

### Bug Fixes

- **agent**: Flag image-only PDFs and surface AI cover option
  ([#44](https://github.com/mfozmen/littlepress-ai/pull/44),
  [`ae77a81`](https://github.com/mfozmen/littlepress-ai/commit/ae77a8153485c1564ceaec33d383cd6c036c217c))

* fix(agent): flag image-only PDFs and surface AI cover option

Two agent-surface gaps the first real end-to-end test (Yavru Dinozor, a Samsung Notes PDF export)
  exposed. The product code for both was already present; the missing piece was information reaching
  the LLM correctly, so most of the diff is test coverage that pins the new contract.

### Image-only pages

Samsung Notes (and phone-scan exports generally) render each page as a single PNG screenshot. Text
  glyphs live as pixels inside the image; the PDF has no ``/Font`` resource on any page.
  ``pypdf.extract_text`` correctly returns empty, and ``read_draft`` duly showed every page as
  ``Page N (drawing, ...):`` with a trailing blank. The LLM reading that summary guessed wrong —
  "hepsinde drawing var, text yok; belki resim kitabı mı?" — and started asking the user whether
  they wanted text at all, when the child visibly had text on every page.

Fix: ``read_draft`` now decorates each image-only page with an

inline ``— image-only, no extractable text`` marker and emits a single summary NOTE at the end
  naming the pages. The NOTE spells out the preserve-child-voice invariant ("Do not invent,
  paraphrase, or 'guess' the child's words") and names the forward path ("ask the user to transcribe
  each page's text verbatim"). One warning per draft, not one per page, so the signal doesn't dilute
  on a large book.

### AI cover discoverability on non-OpenAI providers

``generate_cover_illustration`` is registered only when the active provider is OpenAI (PR #41).
  Claude / Gemini / Ollama users never see the tool, so cover-picking silently becomes a "pick one
  of your drawings or go with poster" choice — the AI option looks like it doesn't exist. Added a
  one-line hint to ``set_cover``'s description (every provider's LLM reads it) pointing the user at
  ``/model`` when they want an AI-generated cover.

### Tests

Seven new tests in ``test_agent_tools.py``:

- image-only page flag + preserve-child-voice instruction present - flag absent for pages that carry
  extracted text (no false positive) - flag absent for text-only pages without an image (no
  contradiction with "no drawing") - mixed draft: only the image-only pages appear in the summary
  note, the text-carrying pages stay untouched - explanatory NOTE fires exactly once per draft, not
  per page - NOTE wording explicitly mentions "transcribe" and child-voice - ``set_cover``
  description includes both an "AI / generate" reference and an "OpenAI / /model" switch hint

Preserve-child-voice suite stays passing: no tool rewrites page text; the change only affects how
  ``read_draft`` *reports* existing state to the agent.

### PLAN

Moved OCR from deferred → Next-up (real user need), added a ``read_draft`` hint item (now
  implemented, so this PR removes it again below), a ``generate_cover_illustration`` discoverability
  item, and a SonarCloud backlog item (12 open issues: 10 × cognitive complexity + 1 × unused param
  + 1 × f-string + 1 × redundant exception). Dedicated refactor PR follows.

* fix(agent): address PR review — echo child-voice guard, compact flag

Four findings from the PR review:

1. Main finding — ``set_cover``'s new AI-cover hint didn't echo the PRESERVE-CHILD-VOICE guard that
  PR #41 put into ``generate_cover_illustration``'s description. On Claude / Gemini / Ollama
  sessions the AI tool's description is invisible, so ``set_cover`` is the *only* place those agents
  read about AI cover generation. Without the echo, a non-OpenAI agent following the ``/model`` hint
  would show up in OpenAI with a prompt that paraphrases the child's page text — exactly the
  scenario PR #41's final review round was meant to prevent. Added a one-sentence echo
  ("PRESERVE-CHILD-VOICE applies to the AI cover prompt too: describe the cover scene in your own
  words … do not quote or paraphrase the child's page text into the prompt") and a paired test.

2. Sub-threshold — ``read_draft``'s docstring and LLM-facing ``description`` still promised only
  "text, drawing, layout" and didn't mention the new image-only flag / NOTE contract. Updated both
  so the LLM trusts the marker when it appears.

3. Sub-threshold — consistency inside this same PR. The test
  ``test_read_draft_note_only_fires_once_not_per_page`` explicitly pinned "one English-sentence
  warning per draft, not per page," but the per-page line still repeated "— image-only, no
  extractable text" for every flagged page — undermining the very single-emit rule the test was
  protecting. Replaced the per-page English phrase with a compact ``[image-only]`` tag; the full
  preserve-child-voice explanation stays in the single summary NOTE. New test pins the compact-tag /
  single-NOTE contract together.

4. Sub-threshold — PLAN.md's SonarCloud line numbers would drift with every merge. Replaced them
  with stable file + symbol pairs ("``src/agent_tools.py`` — in ``set_cover_tool``'s poster branch"
  rather than ":322") and a note to re-run the API query when starting the cleanup PR.

Tests: three new pins on top of the seven from the previous commit

in this PR, all four of the review findings now regression-guarded. 472 tests green.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

### Chores

- **release**: 1.1.1 [skip ci]
  ([`52c4daa`](https://github.com/mfozmen/littlepress-ai/commit/52c4daabb7ff923cdb90c90f3fb038fc0b74c861))

### Continuous Integration

- Re-enable auto release on push to main after v1.1.0 reset
  ([#43](https://github.com/mfozmen/littlepress-ai/pull/43),
  [`29132a7`](https://github.com/mfozmen/littlepress-ai/commit/29132a794ed97ceb8e4ab52eb1efdeec2254815f))

* ci: re-enable push-on-main release trigger alongside workflow_dispatch

With v1.1.0 cut from the previous PR, PSR's last-tag reference point is now fresh. The stale
  ``BREAKING CHANGE:`` footer from PR #38 sits behind v1.1.0 in history, so PSR won't see it again —
  future automatic bumps stay in the 1.x line until a deliberate breaking change is staged.

Restore the push trigger so merges to main auto-bump again per Conventional Commits (feat → minor,
  fix/perf → patch). Keep ``workflow_dispatch`` for emergency forced bumps, and switch its default
  from ``minor`` to ``patch`` — the one-time minor was a transition tool; the safer default for a
  one-off forced bump is patch.

PSR's own release commits are tagged ``[skip ci]`` in ``commit_message``, so the infinite push →
  release → push loop is prevented by GitHub Actions' skip-ci convention without a dedicated guard.

* ci: address PR review for push-trigger restore

Two sub-threshold findings from the PR review:

1. ``default: patch`` meant a bare manual dispatch silently forced a patch bump, even when the
  commit history would have warranted minor or major. Now that v1.1.0 is tagged and the stale
  BREAKING CHANGE footer is behind it, PSR's commit-scan is safe again — default back to empty and
  put ``""`` back in the choices list. Manual dispatchers pick a level only when they actually want
  to override; everyone else gets "what PSR thinks this should be".

2. ``paths-ignore: [CHANGELOG.md]`` added to the push trigger as defense-in-depth against the
  release → push → release loop. Today GitHub Actions' ``GITHUB_TOKEN`` auto-suppresses workflow
  re-triggers from token-authored commits, and PSR's ``[skip ci]`` commit message tag is a second
  layer. The guard becomes load-bearing the moment auth moves to a PAT (e.g. to trigger a downstream
  publish workflow from the release). Better to add it now than chase a mystery re-run later.
  ``pyproject.toml`` stays eligible because legitimate human edits (dep bumps, metadata) still need
  a release scan.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>


## v1.1.0 (2026-04-17)

### Bug Fixes

- **builder**: Stop inserting surprise blank pages in rendered books
  ([#28](https://github.com/mfozmen/littlepress-ai/pull/28),
  [`4ae2dfc`](https://github.com/mfozmen/littlepress-ai/commit/4ae2dfcd8ade9b520757d3b5f000f87a8c3d25da))

The A5 PDF used to carry two blank pages the user never asked for:

1. A blank right after the cover — the "inside-front cover left blank" bookbinding convention. In a
  short children's book this reads as "why is there an empty page?" (the maintainer flagged it on
  the first end-to-end test). 2. A conditional blank before the back cover when the overall page
  count was odd — there to keep booklet pagination even.

Neither earns its keep. imposition.impose_a5_to_a4 pads to multiples of 4 on its own when the user
  actually asks for a booklet, so the conditional pad was redundant for booklet output and wrong for
  plain A5 where nobody needs it. The inside-front blank is a bookbinding convention that doesn't
  match the "short family book" product.

New contract, pinned by four regression tests in test_builder.py: ``cover + N story pages + back
  cover`` — nothing else. 1-page book → 3 PDF pages. 5-page book → 7 PDF pages. 8-page book → 10.

Also drop the now-unused draw_blank helper from src/pages.py — no production or test path references
  it anymore.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Accept /exit in the provider picker
  ([#23](https://github.com/mfozmen/littlepress-ai/pull/23),
  [`2478190`](https://github.com/mfozmen/littlepress-ai/commit/24781907d09377cc3be64d567423357d52ebe393))

* fix(repl): accept /exit in the provider picker

Reported: typing /exit at the first-launch picker printed "Please

enter a number 1-4" instead of leaving the session. The picker's input reader only knew about
  numbers; slash commands were treated as "not a number" and re-prompted.

/exit now aborts the picker (same as EOF / Ctrl-D). Other slash commands (/help, /model, etc.) are
  meaningless before a provider is activated, so steer the user toward a number or /exit instead of
  mislabelling them as non-numeric input.

Two regression tests: /exit alone exits zero with no "enter a number" nag; a different slash command
  prints a hint that mentions /exit before the user finally picks a provider.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* docs: plan Claude-Code-style / menu and a logical slash command order

Record the two deferred UX items discussed with the maintainer:

1. A \`/\` auto-completion menu like Claude Code / Cursor, surfacing each slash command with a
  one-line description. Implementation lane: swap builtins.input for prompt_toolkit.PromptSession
  with a custom Completer.

2. Reorder the slash commands to match the typical workflow — ingest → inspect → metadata → render →
  session/auth — rather than the current registration order. Concrete order committed to PLAN.md so
  the next PR has a target to match.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Kick the agent off after a mid-session /load
  ([#27](https://github.com/mfozmen/littlepress-ai/pull/27),
  [`d543b83`](https://github.com/mfozmen/littlepress-ai/commit/d543b837a43ad27d14a83966bacfd779cd079ec0))

Reported by the maintainer: dragging a PDF onto a live session loaded the draft but the agent stayed
  silent afterwards — the user saw "Loaded 8 pages" and then nothing.

The CLI-arg bootstrap already calls agent.say(greeting) when it's launched with a PDF. That never
  fired for drag-drop or /load because those happen inside the main read loop, after run()'s "did we
  start with a draft?" check has already passed.

After a successful load, if a real (non-Null) provider is active, _cmd_load now calls
  agent.say(_AGENT_GREETING_HINT) — same prompt that kicks read_draft + a friendly "Hi, I see N
  pages..." opener. Offline provider stays silent as before.

Also updated the three pre-existing drag-drop tests: their "agent wasn't invoked at all" invariant
  is now "the raw path didn't leak to the agent as chat" — the load itself still triggers a greeting
  turn, which is the whole point of this fix.

297 tests green; src/repl.py remains at 99% coverage.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Retry with same key on transient errors instead of re-reading
  ([#22](https://github.com/mfozmen/littlepress-ai/pull/22),
  [`86939ac`](https://github.com/mfozmen/littlepress-ai/commit/86939acfe12276581bd8762d81397a4bc6ba5b1e))

Reported after the credit-balance error retry: pressing Enter at the "Press Enter to retry" prompt
  crashed the REPL with a TypeError from the Anthropic SDK ("Could not resolve authentication
  method"). The loop was re-reading the secret every iteration, so Enter returned "", and an empty
  api_key string was handed to anthropic.Anthropic() which refuses empty auth before even forming
  the HTTP request.

Split the logic:

- Outer loop (_read_and_validate_key) reads a NEW secret only when the key itself is rejected
  (KeyValidationError). - Inner loop (_retry_validation) handles the same-key retry used by
  TransientValidationError — the user hits Enter and we ping again with the *same* api_key. Ctrl-D
  at that prompt aborts cleanly.

Two new tests pin the behaviour: the same key is validated twice on Enter-retry, and Ctrl-D aborts
  without ever sending an empty string to the validator.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Strip surrounding quotes from /load paths
  ([#24](https://github.com/mfozmen/littlepress-ai/pull/24),
  [`a3e0434`](https://github.com/mfozmen/littlepress-ai/commit/a3e043467e3a07df7352ced3c05aba23e5f409dc))

* fix(repl): strip surrounding quotes from /load paths

Reported: \`/load \"C:\Users\fahri\Downloads\YAVRU DINOZOR 1.pdf\"\`

returned \"File not found\" because the REPL is not a shell — the quote characters came through
  literally and Path() looked for a file whose name started with a double-quote.

Strip a single matching pair of surrounding \" or ' before calling Path(). Two regression tests: a
  path wrapped in double quotes and one wrapped in single quotes both resolve to a loaded draft
  instead of a not-found error.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* docs: plan drag-and-drop PDF auto-load

Record the next UX ask from the maintainer: when the user drags a PDF onto the terminal window, the
  shell types out the file path. Detect that case (non-slash line that resolves to a real .pdf) and
  route it through _cmd_load automatically so the user doesn't have to type /load first. Reuses
  _unquote from PR #24.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Chores

- Drop the legacy 'python build.py' entry point
  ([#38](https://github.com/mfozmen/littlepress-ai/pull/38),
  [`2b01a6a`](https://github.com/mfozmen/littlepress-ai/commit/2b01a6a22fe11c2a9f789db38bf34d913af7caac))

* chore: drop the legacy ``python build.py`` entry point

The ``python build.py book.json`` path predates the agent flow. Every current user reaches for
  ``littlepress draft.pdf`` — nobody hand-authors a book.json any more — and the legacy CLI was only
  held in place by its own test and its own example fixtures.

Deleted:

- ``build.py`` (the standalone CLI entry) and ``tests/test_build.py`` (smoke test that drove it). -
  ``examples/book.json`` + placeholder PNGs. Only ``test_build.py`` referenced them. - README's
  "Usage — direct renderer (still works)" section and the ``book.json`` schema block. The shape is
  internal now; users hit it through the agent, never typed by hand. - CLAUDE.md references to
  ``build.py`` and the old Commands block (now shows ``littlepress`` as the primary entry).
  Project-layout list refreshed with the shape the code has actually grown into (cover templates,
  collect_input_pdf, next_version_number, etc.).

Kept:

- ``src/schema.py::load_book`` as a library API. Unused inside the project after this PR, but a
  thin, well-tested JSON → ``Book`` reader is the right shape for an external caller that wants to
  parse a ``book.json`` — cheap to keep, easy to delete later if that never materialises.

All 413 tests still pass; no production-code behaviour moved.

BREAKING CHANGE: ``python build.py book.json`` no longer exists. The only supported entry point is
  the ``littlepress`` command, which drives the interactive agent flow. Any automation relying on
  the legacy path needs to be rewritten to feed a PDF through the agent.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* ci: drop build.py from sonar.sources

The SonarCloud scan on PR #38 failed with "The folder 'build.py' does not exist" because the legacy
  entry point got deleted but sonar-project.properties still listed it under sonar.sources. Narrow
  the paths to ``src`` only — that's the whole production tree now.

* build: drop ``examples`` from hatch sdist include list

Companion to the ``examples/`` directory deletion in this same PR. Hatchling is tolerant of missing
  include paths, so this wasn't a runtime blocker — just stale config now that the directory is
  gone.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **release**: 1.0.2 [skip ci]
  ([`3cb7491`](https://github.com/mfozmen/littlepress-ai/commit/3cb7491a4a93c354a2dcbbf63f5a12d308e20b59))

- **release**: 1.0.2 [skip ci]
  ([`0876c0e`](https://github.com/mfozmen/littlepress-ai/commit/0876c0e2b01ca2931a4c5ede2738baa6fb81fe05))

- **release**: 1.0.2 [skip ci]
  ([`95e2a6c`](https://github.com/mfozmen/littlepress-ai/commit/95e2a6c8c37e9d9f02ae5a52dc0d2a8d47121767))

- **release**: 1.1.0 [skip ci]
  ([`115b7dc`](https://github.com/mfozmen/littlepress-ai/commit/115b7dc7357165d4680e23e448152f2c316f8066))

- **release**: 1.1.0 [skip ci]
  ([`7e00bf5`](https://github.com/mfozmen/littlepress-ai/commit/7e00bf5c553083d628ca7d4924ef1dd8f3caa512))

- **release**: 1.1.0 [skip ci]
  ([`0af9b30`](https://github.com/mfozmen/littlepress-ai/commit/0af9b3031066e4e84eca80847c586c328b749f6a))

- **release**: 1.1.0 [skip ci]
  ([`8fbde37`](https://github.com/mfozmen/littlepress-ai/commit/8fbde37198f247b8b868de2411eac004b75280c4))

- **release**: 1.1.0 [skip ci]
  ([`96cbe1a`](https://github.com/mfozmen/littlepress-ai/commit/96cbe1a35118f805af32357e6a2007ebf8aaa5ba))

- **release**: 1.1.0 [skip ci]
  ([`7fd4e3c`](https://github.com/mfozmen/littlepress-ai/commit/7fd4e3cab8f27ced0587d7495b935327c9f9fe13))

- **release**: 1.1.0 [skip ci]
  ([`3e223c7`](https://github.com/mfozmen/littlepress-ai/commit/3e223c746dc0d5923aa9cd149edb8b87b492dd65))

- **release**: 1.1.0 [skip ci]
  ([`748e0b5`](https://github.com/mfozmen/littlepress-ai/commit/748e0b54b4a6e0d5314d78a6e5c4d618b36d45d9))

- **release**: 1.1.0 [skip ci]
  ([`9cc8709`](https://github.com/mfozmen/littlepress-ai/commit/9cc87096b4861db28f97bfd89b646f346d2d53da))

- **release**: 1.1.0 [skip ci]
  ([`45ca1d1`](https://github.com/mfozmen/littlepress-ai/commit/45ca1d1d9e8fdbf156d00b90d2bfa12bb95e3571))

- **release**: 1.1.0 [skip ci]
  ([`410704f`](https://github.com/mfozmen/littlepress-ai/commit/410704f6d07f31dc7c471a71677b08d657dc2844))

- **release**: 1.1.0 [skip ci]
  ([`e53cab0`](https://github.com/mfozmen/littlepress-ai/commit/e53cab0e77c4de6ff3733279309939bf6144a7b0))

- **release**: 1.1.0 [skip ci]
  ([`999d89c`](https://github.com/mfozmen/littlepress-ai/commit/999d89ce1ab9db043a1322190cb08fbcb8a06358))

- **release**: 1.1.0 [skip ci]
  ([`b991923`](https://github.com/mfozmen/littlepress-ai/commit/b991923bcf065147a1d0e0cc3bee04b5b1fc69b9))

- **release**: 1.1.0 [skip ci]
  ([`270c679`](https://github.com/mfozmen/littlepress-ai/commit/270c6794527e8d284ae8c1d339e614f43090bb54))

- **release**: 1.1.0 [skip ci]
  ([`801b8d1`](https://github.com/mfozmen/littlepress-ai/commit/801b8d1866937ceaa049d0663feb028d0e4f0b06))

- **release**: 1.1.0 [skip ci]
  ([`0b4b9ae`](https://github.com/mfozmen/littlepress-ai/commit/0b4b9aeb8d2ff8108e99beea1d883dfc8aed3732))

- **release**: 1.1.0 [skip ci]
  ([`5facc08`](https://github.com/mfozmen/littlepress-ai/commit/5facc08c8bc2fe5b08a366347b3ca5cd5a367131))

- **release**: 2.0.0 [skip ci]
  ([`f7b7f08`](https://github.com/mfozmen/littlepress-ai/commit/f7b7f08a85e31394ace090997ba6b363503e6062))

- **release**: 2.0.0 [skip ci]
  ([`774f67e`](https://github.com/mfozmen/littlepress-ai/commit/774f67e3436ca8ef2277ed88ac564bfafbcb86c1))

- **release**: 2.0.0 [skip ci]
  ([`7d659cb`](https://github.com/mfozmen/littlepress-ai/commit/7d659cb8c7ce1d6fd71ec9a75749c93f1b7d9d92))

- **release**: 2.0.0 [skip ci]
  ([`5ba289c`](https://github.com/mfozmen/littlepress-ai/commit/5ba289c5e7126cedabc2a368d104ef2d225e7644))

### Continuous Integration

- Retry release push so a racing merge doesn't skip a version bump
  ([#21](https://github.com/mfozmen/littlepress-ai/pull/21),
  [`b453168`](https://github.com/mfozmen/littlepress-ai/commit/b453168bb43a8fff6200017b692dd9ea52919200))

* ci: retry release push so a racing merge doesn't skip a version bump

The Release workflow's PSR push failed with a non-fast-forward rejection when a second commit landed
  on main while PSR was bumping the version. Both the rename merge (feat!:) and the PLAN.md
  follow-up arrived within seconds; the first run couldn't push because the second had already
  updated main, and the second run analysed only docs: so no bump fired. Net effect: the feat!:
  rename never got a v1.0.0 tag.

Split the release step into two: PSR bumps and tags locally with push=false; a shell step pulls
  --rebase and pushes with up to five retries. Next push picks up the accumulated feat!: and cuts
  the major release it deserved.

Also add the "next up" section of docs/PLAN.md for the deferred multi-provider chat()
  implementations (Gemini / OpenAI / Ollama real chat + turn) — one PR per provider when we get to
  them.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* ci: move release tag to HEAD after each rebase so push doesn't orphan it

Addresses review feedback on #21.

PSR creates the release tag on its local commit C. When the retry loop pulls --rebase and the remote
  had commits to rebase onto, C becomes C' with a new SHA — but the tag still points at C. git push
  --follow-tags only pushes annotated tags reachable from the pushed ref, so the orphaned tag stays
  on the runner and never reaches the remote. Main would advance with the version bump + CHANGELOG
  but the release tag would be gone.

Capture the tag name up front (git tag --points-at HEAD) and re-point it with git tag -f "$TAG" HEAD
  after each pull --rebase. --follow-tags then has a reachable target and the tag ships with the
  commit.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **release**: Manual workflow_dispatch, reset version after broken auto-bump cycles
  ([#42](https://github.com/mfozmen/littlepress-ai/pull/42),
  [`4c4b90e`](https://github.com/mfozmen/littlepress-ai/commit/4c4b90e3db066d52d97526acccfe3952f64dd7cc))

* ci(release): switch to manual workflow_dispatch with force input

The push-on-main + ``push: false`` PSR configuration was broken in two ways:

1. ``push: false`` doesn't just skip the git push — it also tells PSR not to create the VCS release.
  Every run reported "No vcs release will be created because pushing changes is disabled", so tags
  and GitHub Releases never appeared even though the bump commit landed on main. The last real
  release on GitHub stayed at v1.0.1.

2. The manual push step had a rebase-retry loop for a race the ``concurrency: release-main +
  cancel-in-progress: false`` group already prevents. Release runs are serialised on main, so a
  second push can never interleave with an active release run.

Collapse the workflow to a single PSR step with ``push: true`` — PSR writes the bump commit, creates
  the tag, pushes both, and cuts the GitHub Release in one pass. Trigger is now
  ``workflow_dispatch``-only: releases happen when a human decides they should happen, not on every
  main-branch push. The ``force`` input (patch/minor/major/prerelease/empty) lets the maintainer
  override PSR's own calculation — needed at least once, to cut v1.1.0 past the stale ``BREAKING
  CHANGE:`` footer left over from the legacy build.py removal.

Trigger from the gh CLI: ``gh workflow run release.yml -f force=minor``. Or from the Actions UI (Run
  workflow dropdown).

* chore: reset version and CHANGELOG after botched auto-bump cycles

PSR auto-bumped pyproject.toml to 2.0.0 on the first main-branch push after PR #38 landed a
  ``BREAKING CHANGE:`` footer, but because ``push: false`` prevented the VCS release from being cut,
  the corresponding tag and GitHub Release never appeared — the last release on GitHub is still
  v1.0.1. Every subsequent ``feat:`` merge repeated the same dead bump (2.0.0 → 2.0.0, no VCS
  release) and nothing advanced past v1.0.1 externally.

Rather than tag and release v2.0.0 retroactively, reset pyproject to the last real release (1.0.1)
  and drop the auto-generated v2.0.0 section from CHANGELOG.md (1202 lines of notes for a release
  that never actually shipped). The next manual dispatch of the Release workflow with
  ``force=minor`` will cut v1.1.0, bundling everything that's landed since v1.0.1 into a single
  minor bump — appropriate for a tool with a single current user, where the breaking-change call on
  build.py removal wasn't load-bearing.

After v1.1.0, PSR's last-tag reference point is fresh and the old BREAKING CHANGE footer no longer
  controls future bumps — normal feat/fix/perf commits drive patch/minor releases from there.

* ci: address PR review for release workflow reset

Two sub-threshold findings from the PR review:

1. Default ``force: \"\"`` on the dispatch was a footgun for the very first run — ``git log
  v1.0.1..HEAD`` still contains PR #38's ``BREAKING CHANGE:`` footer, and PSR with no force would
  walk right past it and compute v2.0.0 again, re-creating the problem this PR is meant to fix.
  Default is now ``minor`` so a naive dispatch-with-defaults produces v1.1.0 instead. The empty
  option is dropped from the choices — the dispatcher has to pick a level intentionally.

2. ``upload_to_pypi`` and ``upload_to_release`` are PSR v7/v8 keys that v9 silently ignores at this
  location (the rename moved them under ``[tool.semantic_release.publish]`` as
  ``upload_to_vcs_release``). Harmless today — the behaviour we want (GitHub Release yes, PyPI no,
  no build) is already the v9 default — but stale config that looks load-bearing invites confusion.
  Dropped the dead keys plus the empty ``build_command`` and replaced the old comment with one that
  names what's actually going on.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

### Documentation

- Add layout-variety nudge to the plan
  ([`91738f8`](https://github.com/mfozmen/littlepress-ai/commit/91738f8eb7275b6f20aea57b07331a0f506399ea))

Yavru Dinozor test had a tidy but over-regular rhythm. The skill already says "no same layout 3 in a
  row, cap image-full at 30%", but the agent never sees that — .claude/skills/ is Claude Code
  context, not LLM system prompt. Fix idea noted in the plan: bake the rhythm rules into
  choose_layout's tool description and pass neighbour context in the tool input.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Add overwrite + input-folder items to plan
  ([`088d4b7`](https://github.com/mfozmen/littlepress-ai/commit/088d4b70791608d9ee858ea878eda1d7218209ff))

End-to-end feedback turned up two housekeeping gaps:

1. Every render silently overwrites the previous PDF (same slug, same path). Rendering twice loses
  the first copy with no warning — plan calls for versioned filenames alongside a stable "latest".
  2. Draft PDFs live wherever the user dropped them; memory keys off that absolute path. Moving or
  deleting the source breaks the saved session. Plan is to copy the PDF into .book-gen/input/ on
  first load and retarget source_pdf there.

Both land at the top of "Next up" because they affect data safety.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Capture four issues from the first end-to-end test
  ([`1fc14da`](https://github.com/mfozmen/littlepress-ai/commit/1fc14daf2230a77195a244aa6613cc181ba0d051))

The Yavru Dinozor test surfaced a handful of concrete gaps in the post-render UX and the cover page.
  Record them in Next up so the next PR has a clear target:

- Cover layout is cramped — the half-page split between title band and drawing makes both feel
  squeezed. Need a full-bleed / framed template pair. - Agent asks the user to design the layout
  rhythm; it should propose a rhythm itself and just ask to approve. - After render_book the user
  had to hunt for the output files — the agent should print the absolute paths and open the A5 in
  the system viewer. - AI cover generation as a new tool (ImageProvider + generate_
  cover_illustration), opt-in and priced.

Per-page illustration generation moves up into the deferred section (follow-up to cover generation).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Drop the surprise blank pages from the plan
  ([`96a7719`](https://github.com/mfozmen/littlepress-ai/commit/96a7719855df053cce03f54f2e1ae91cd88895bd))

Maintainer spotted a blank page in the first end-to-end output. Two culprits in src/builder.py: a
  blank after the cover ("inside-front cover left blank" — a real-bookbinding convention) and a
  blank before the back cover when the page count is odd. For a short children's book these both
  read as bugs — imposition.impose_a5_to_a4 already pads to multiples of 4 when a booklet is
  requested, so the pre-back-cover pad is redundant.

Listed in Next up at priority #1 — quickest win with user-visible impact.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Plan removing the legacy ``python build.py`` entry point
  ([`2e2aba2`](https://github.com/mfozmen/littlepress-ai/commit/2e2aba28d741dd810b57b4f2470b98251cd6818a))

User question on PR #37: "who will use this?" about the README's "Usage — direct renderer (still
  works)" section. Good catch — nobody does. The flow predates the agent pivot; every current user
  reaches for ``littlepress draft.pdf``. ``build.py``, the README block, and ``tests/test_build.py``
  are all dead weight.

Added as a cleanup item to Next up so it can ship as its own focused PR (deletes a file, a README
  section, and probably ``examples/book.json`` + placeholder PNGs).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Trim shipped "don't overwrite previous renders" from plan
  ([`2066444`](https://github.com/mfozmen/littlepress-ai/commit/20664445c7e818d796eecab596dab399c8cab55a))

Versioned renders (<slug>.vN.pdf snapshots alongside the stable <slug>.pdf) shipped in #30. Plan had
  the item at the top of Next up; trim it so the first entry points at the next unfinished piece
  ("Collect user PDFs in .book-gen/input/").

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- Mirror input PDFs so memory survives file moves
  ([#31](https://github.com/mfozmen/littlepress-ai/pull/31),
  [`b58dac3`](https://github.com/mfozmen/littlepress-ai/commit/b58dac3fe51c7489209de43fc39d4aa549ee1535))

* feat: mirror input PDFs into .book-gen/input/ so memory survives file moves

Today the draft PDF's ``source_pdf`` and persisted memory both key off whatever absolute path the
  user dropped the PDF at — Downloads, Desktop, a colleague's shared folder. Deleting or moving that
  file means the next run can't match what's saved; the session is gone.

collect_input_pdf() in src/draft.py copies the PDF into
  <session-root>/.book-gen/input/<stem>-<sha256[:8]>.pdf and returns that in-repo path. Both /load
  and the CLI bootstrap route through the helper before ingesting the PDF, so Draft.source_pdf and
  memory both key off a path we control. The user's Downloads folder can be cleaned without breaking
  the session.

Naming uses a content hash (first 8 hex of sha256) so: - Identical bytes always resolve to the same
  in-repo path. Reruns are idempotent; memory matches. - Different bytes with the same basename (two
  drafts both called draft.pdf) get distinct in-repo paths. Their memories stay separate instead of
  silently cross-wiring.

The helper also no-ops when the caller points at a path already under .book-gen/input/ — /load
  .book-gen/input/draft-<hash>.pdf doesn't recurse or copy onto itself.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix: address PR review for collect_input_pdf

- Migrate legacy memory on first relaunch. Users with a saved session from before this feature have
  source_pdf = the original arg path; the CLI's memory lookup now uses the hashed in-repo path,
  which wouldn't match. Silent discard of the saved state. On a first-lookup miss we fall back to
  the pre-collection path and, if that hits, re-save with the new in-repo path so subsequent
  launches skip the fallback.

- Extend the hash from 8 to 16 hex chars. 32-bit namespace crosses 50% collision probability at ~77k
  distinct PDFs — fine for a single user today, but the hedge to 64 bits is effectively free and
  makes the scheme robust if .book-gen/input/ ever gets shared across projects or the tool grows
  into batch workflows.

- Clarify collect_input_pdf's idempotency contract in the docstring. The same-hash-same-path
  invariant depends on the directory being owned by Littlepress — a user hand-editing a file in
  there breaks the assumption. Say so explicitly instead of hiding it behind "same hash ⇒ same
  bytes".

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Poster cover template + select-cover-template skill
  ([#35](https://github.com/mfozmen/littlepress-ai/pull/35),
  [`38b10ef`](https://github.com/mfozmen/littlepress-ai/commit/38b10effbb0d13f0c6e2bd781386d2f6a43a4a02))

* feat: poster cover template + select-cover-template skill

Adds the third cover template the plan called for:

- ``poster`` is type-only — huge centred title, author along the bottom, no drawing. Intended for
  books whose child-author didn't make a cover illustration, where full-bleed and framed both
  produce awkward empty illustration holes. - set_cover learns that poster doesn't need a page
  drawing: its ``page`` argument becomes optional when ``style='poster'``. Every other style still
  requires a page with an image. - VALID_COVER_STYLES + the tool schema enum expand accordingly; the
  renderer dispatcher branches to _draw_cover_poster. - Shrink-to-fit already shipped for the two
  existing templates is reused for poster so long English titles stay on the page.

And the decision mechanism the plan asked for, mirroring the select-page-layout skill:

- .claude/skills/select-cover-template/SKILL.md encodes the rules for picking between the three
  templates — no drawing → poster, long title + busy drawing → framed, dramatic illustration →
  full-bleed, quiet / small-figure → framed, default → full-bleed. CLAUDE.md references it so the
  agent consults the skill before calling set_cover.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix: address PR review for poster template + skill

Five findings, all valid:

1. Skill / code drift on the title floor. The skill documented a 16-pt minimum; the code capped at
  18-pt. Neither was right — see #3. Replaced with COVER_TITLE_MIN_READABLE = 14 in src/config.py,
  referenced by the skill as an *advisory* threshold (below this, the skill nudges you to a
  different template).

2. set_cover with style='poster' + bogus page silently accepted out-of-range pages. Moved the page
  validation before the style branch so an invalid page is rejected regardless of whether poster
  will use it. Poster still ignores a valid page, but now says so in the reply.

3. COVER_POSTER_TITLE_SIZE = 64 hit _fit_title_size's 18-pt floor for long titles — at which point
  the 18-pt text was still wider than the page. Root cause: the floor was a hard cap that could
  still clip. Dropped the floor entirely; _fit_title_size now shrinks proportionally so fit is
  guaranteed by math. Lowered the preferred poster size from 64 to 52 so the shrink-ratio isn't
  absurd. Added a regression test that captures the actual drawString font size and asserts the
  rendered width stays inside the page.

4. draw_cover's 'else: full-bleed' fallback contradicted its own docstring. Replaced with a raise on
  unknown styles so a direct Book-with-typo bypasses surface instead of rendering as the wrong
  cover.

5. Skill red-flag about not picking poster for unpolished drawings had no matching decision rule.
  Promoted it to an explicit rule: "A cover drawing exists → never pick poster."

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **agent**: Ai cover generation via OpenAI gpt-image-1
  ([#41](https://github.com/mfozmen/littlepress-ai/pull/41),
  [`526d95d`](https://github.com/mfozmen/littlepress-ai/commit/526d95da861704249ec3d992cdee6fc301ecfaf0))

* feat(agent): AI cover generation via OpenAI gpt-image-1

Optional ``generate_cover_illustration`` tool for when the child didn't draw a cover (or wants a
  different one). The tool is registered only when the active provider is OpenAI and a key is
  available — on other providers the agent doesn't see it, so there's no 401-on-first-use surprise.

New files:

- ``src/providers/image.py`` — ``ImageProvider`` protocol and ``OpenAIImageProvider`` (model
  ``gpt-image-1``). Lazy SDK import so Ollama-only users don't need ``openai`` installed. All
  failures (auth, rate, policy filter, empty response, missing SDK) surface as a single
  ``ImageGenerationError`` the tool layer reports cleanly.

- ``src/agent_tools.py::generate_cover_illustration_tool`` — takes a prompt + quality tier +
  optional cover style. Shows the prompt and an estimated cost (low ≈ $0.02, medium ≈ $0.07, high ≈
  $0.19 per portrait 1024x1536) in a y/n confirmation before any API call; on decline, nothing is
  spent and cover state is untouched. On approval the PNG lands under
  ``<session_root>/.book-gen/images/cover-<hash>.png`` and the draft's ``cover_image`` points at it.

- ``tests/test_image_provider.py`` — 8 tests covering happy path, arg forwarding, parent-dir
  creation, auth/API error wrapping, empty- response handling, missing-SDK handling, and protocol
  membership.

- ``tests/test_repl_tools.py`` — 3 integration tests for the REPL's conditional tool registration
  (OpenAI-with-key yes, other providers no, OpenAI-without-key no).

- 11 new unit tests in ``tests/test_agent_tools.py`` for the tool itself: draft requirement, prompt
  / price confirmation, decline path,

provider call, ``.book-gen/images/`` output location, style application, invalid style / quality
  rejection, provider-error surfacing, empty-prompt rejection, schema shape.

README, CLAUDE.md, and docs/PLAN.md updated to describe the new tool and move the "AI cover
  generation" item from Next-up to Shipped.

* fix(providers): address PR review for image provider and tool surface

Four findings from the PR #41 review:

1. Tool description lacked a preserve-child-voice invariant. CLAUDE.md names src/agent_tools.py as
  the place the rule is enforced; the description now explicitly forbids paraphrasing the child's
  page text into the image prompt ("PRESERVE-CHILD-VOICE: describe the cover scene in your own words
  […] do NOT quote or paraphrase the child's page text"). Also pinned by a new test
  (test_generate_cover_illustration_description_guards_child_voice).

2. Non-atomic PNG write contradicted the docstring's "atomically" promise. Added
  ``_atomic_write_bytes`` helper that writes to a sibling ``.tmp`` file and ``os.replace``s into the
  final name, matching the pattern used by memory.py / draft.py::atomic_copy. Also wrapped
  ``base64.b64decode`` so malformed base64 (binascii.Error) surfaces as ImageGenerationError rather
  than escaping raw to the agent loop.

3. OpenAI client had no timeout — the SDK default (~600 s) would hang the REPL on a network drop.
  Added an explicit 120 s timeout at client construction (long enough for quality="high" renders
  that legitimately take 30-90 s, short enough that a dead connection reaches the user promptly).

4. Error classification used defensive getattr fallbacks that were dead code (the openai SDK is a
  pinned dep), and lacked a connection/timeout branch. Switched to direct imports of
  AuthenticationError / PermissionDeniedError / APIError / APIConnectionError / APITimeoutError
  (matching validator.py::_check_openai), and split the network branch above APIError so a
  connectivity failure reports "could not be reached" instead of looking like a policy rejection.

New tests (4): - timeout kwarg passed to OpenAI client constructor - APIConnectionError wraps into a
  network-specific ImageGenerationError - malformed base64 wraps into ImageGenerationError -
  mid-write os.replace failure leaves no truncated file at final path

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

- **agent**: Auto-open the rendered A5 and surface absolute paths
  ([#29](https://github.com/mfozmen/littlepress-ai/pull/29),
  [`d3767c3`](https://github.com/mfozmen/littlepress-ai/commit/d3767c3c37ad9f3d436369db908cbb8de45e1e10))

* feat(agent): auto-open the rendered A5 and surface absolute paths

Post-test feedback: after render_book the user had to hunt through the filesystem for the output.
  Rendered book opens itself now.

- render_book_tool hands the finished A5 PDF to the platform's default PDF viewer via a new
  open_in_default_viewer helper (os.startfile on Windows, `open` on macOS, `xdg-open` elsewhere).
  Fire-and-forget; a viewer failure is silently swallowed because the file is on disk and the agent
  reply already includes the path. - The A4 booklet is a print artefact — the tool does NOT open it.
  Only the A5 reading copy pops up. - out_path is now resolved to an absolute path before the reply,
  so the agent always tells the user the full location, not a cwd-relative one. - Injectable
  open_file parameter on render_book_tool so tests can assert on calls without spawning real
  viewers, and so a future "no auto-open" mode is one-line away. - tests/conftest.py auto-mocks
  open_in_default_viewer for the whole suite — a full pytest run used to spawn a PDF viewer per
  integration render.

Five new tests pin: absolute paths in message, A5 opens, booklet does not, viewer failure is
  non-fatal, opener is not called when build_pdf errors out. 306 tests green; src/agent_tools.py at
  97% (the only gap is the platform-dispatch helper itself, trivial fire-and-forget dispatch).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(agent-tools): address PR review for auto-open

- Detach the xdg-open/open child with start_new_session=True so it doesn't become a zombie waiting
  on the Python process to reap it. - Only claim "opened in your viewer" when the opener actually
  succeeded; otherwise tell the user to open the file manually so the message never lies about what
  happened. - README Status line now mentions the auto-open behaviour (and that the booklet
  intentionally doesn't pop up — it's a print artefact). - Cover the platform dispatch in
  open_in_default_viewer directly, working around the conftest auto-mock via a module-load-time
  import binding. Gets src/agent_tools.py back to 100% coverage.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **agent**: Layout rhythm awareness in choose_layout / propose_layouts
  ([#34](https://github.com/mfozmen/littlepress-ai/pull/34),
  [`f160ed2`](https://github.com/mfozmen/littlepress-ai/commit/f160ed2b88f5f0a1b54b6a0ee2661e4f1417c320))

* feat(agent): bake rhythm rules into layout tools + echo neighbours

The first end-to-end test (Yavru Dinozor) produced a tidy but over-regular rhythm — full / top /
  bottom / full / top / bottom — that looked varied in a table but monotonous on paper. The rules
  that'd prevent this live in .claude/skills/select-page-layout, but the LLM never sees the skill at
  decision time.

Fix: lift the rhythm rules into both layout tools' descriptions

(no three-in-a-row, cap image-full at ~30 %, alternate top/bottom). Every time the agent calls
  choose_layout or propose_layouts, the rules are in context.

Plus a feedback loop: choose_layout's reply now lists the two pages before and after the one that
  just changed. The agent doesn't need a read_draft round-trip to see whether it's about to repeat
  itself — the adjacent layouts arrive with the confirmation.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* test(agent): tighten rhythm-awareness tests from PR #34 review

Three test-coverage gaps the review flagged:

1. The neighbour-summary test had pages 1, 3, 5 all seeded with image-top, so ``"image-top" in
  result`` passed whether page 3 got mutated or not. Seed every page with a distinct layout and
  assert the ``p<n>=layout`` signature for each position, including the post-mutation value for the
  page that just changed.

2. The page-number assertion was ``"2" in result and "4" in result`` — any response containing those
  digits passed, even a format refactor that dropped the ``p<n>=`` prefix. Replaced with an
  assertion on the exact ``p2=…`` / ``p4=…`` tokens plus the ``(this page)`` marker.

3. No boundary coverage for _neighbour_summary. Added three unit tests via choose_layout: first-page
  (window clamps, no p0/p-1), last-page (no p4 on a 3-page book), single-page (just the page itself,
  no ghost neighbours).

Production code unchanged — these are tests-only tightenings plus new boundary tests.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **agent**: Propose_layouts tool for whole-book rhythm approval
  ([#33](https://github.com/mfozmen/littlepress-ai/pull/33),
  [`b0eee37`](https://github.com/mfozmen/littlepress-ai/commit/b0eee3780099b089ed1d35f26491536b701f4b4e))

Per-page choose_layout is awkward for the "settle on a rhythm" phase: the agent has to ask the user
  to approve N individual decisions when what they really want to see is the full rhythm on one page
  and say yes or no to the whole thing.

propose_layouts takes every page in one call, validates the batch as a unit (out-of-range,
  duplicates, invalid layout name, image-layout on an imageless page — all rejected before prompting
  so we never half-apply), renders a readable summary, and flips the whole book on a single y/n. If
  the user declines, nothing changes and the agent can adjust or fall back to choose_layout for
  surgical tweaks.

Tool registered in Repl._build_agent alongside the per-page tool; both stay available so the agent
  can pick the right one per phase.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **pages**: Portrait-frame and title-band-top cover templates
  ([#40](https://github.com/mfozmen/littlepress-ai/pull/40),
  [`a7d5a4e`](https://github.com/mfozmen/littlepress-ai/commit/a7d5a4e67438a27c2c992e8c56f060e5df66bb9b))

* feat(pages): portrait-frame and title-band-top cover templates

Two new cover templates, completing the five-template set the plan called for (spine-wrap is
  deferred — multi-page cover support):

- ``portrait-frame``: the drawing sits inside a visible rounded-rect border (like a framed picture
  on a wall), title centred above the frame, author below it. Good for quiet single-figure
  illustrations that benefit from a stage — the border prevents the drawing from looking lonely on a
  full page.

- ``title-band-top``: a warm-toned coloured band at the top holds the title; the drawing fills the
  remaining space below; author at the bottom. More assertive than framed — the colour band lifts
  the title off the page, especially useful when a long title sits over a busy illustration that
  would swallow plain type.

Both templates use _fit_title_size for shrink-to-fit. The select-cover-template skill gains two new
  decision rules: quiet/small-figure → portrait-frame, long-title + busy drawing → title-band-top.

Also: .review_tmp/ added to .gitignore (stale files from code-review

agent).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(pages): address PR review for portrait-frame and title-band-top

Four findings:

1. portrait-frame was missing subtitle rendering — every other image-carrying template renders it.
  Added subtitle between the title and the frame, with the frame_top computed from the subtitle
  baseline when present. New test pins it.

2. title-band-top's subtitle could overflow below the coloured band when the title shrinks (long
  title → smaller title_size → subtitle baseline drops past band bottom). Added a clamp: if the
  candidate subtitle y-coordinate would exit the band, the subtitle is silently skipped rather than
  rendered over the drawing without the coloured background.

3. Skill frontmatter still said "(full-bleed, framed, poster)" and the "Goal state" section listed
  portrait-frame / title-band-top as future work. Updated the description to name all five templates
  and trimmed the goal section to only spine-wrap.

4. Decision-tree gap for long title (>32 chars) + quiet drawing. portrait-frame's narrower width
  (inset border) would shrink the title further; added rule 4: long title + quiet drawing → framed
  (not portrait-frame). portrait-frame demoted to rule 5 with an explicit "short title" qualifier.

* refactor(pages): drop dead subtitle_bottom store in title-band-top

Sonar flagged `subtitle_bottom` in `_draw_cover_title_band_top` as an unused local (rule
  python:S1854). It was copied from `portrait-frame` where the variable feeds `frame_top`; in
  `title-band-top` the image rect is driven by `band_bottom` instead, so the assignment is dead.
  Pass `candidate_y` directly to `drawString` and remove the shadow var.

Also adds `test_cover_title_band_top_renders_subtitle` pinning the subtitle contract for this
  template — the existing suite exercised the title and author but not the subtitle branch.

* fix(pages): address second-round PR review for new cover templates

Six findings from PR #40's second review pass:

1. Skill decision tree had two rules numbered `5` after the previous fix inserted rule 4 without
  cascading the renumber. Downshifted the last three to 6 / 7 / 8 so "first match wins" ordering is
  unambiguous.

2. `_draw_cover_portrait_frame` lost its descender clearance on the no-subtitle path. The earlier
  fix collapsed `frame_top` to `title_y - 4*mm` when no subtitle, losing the `title_size * 0.35`
  breathing room that full-bleed / framed both preserve. Seed `subtitle_bottom` with `title_y -
  title_size * 0.35` so the frame stays clear of 'g'/'y'/'p' descenders regardless of subtitle.

3. `VALID_COVER_STYLES` block comment listed only three templates; added bullets for
  `portrait-frame` and `title-band-top`.

4. CLAUDE.md listed only three templates in two places (architecture bullet and skill description);
  brought both in line with the five we ship.

5. `COVER_BAND_H` comment claimed it was used by `framed`; actually `title-band-top` is the second
  consumer, and `framed` doesn't use it at all. Updated the comment to reflect reality.

6. `_draw_cover_title_band_top` subtitle clamp was dead code with inverted physics in its rationale:
  shrinking the title size makes `candidate_y` larger (subtitle moves up), not smaller. The guard
  would only trip above ~57pt, but `_fit_title_size` caps at 34pt and only shrinks. Removed the
  guard and rewrote the comment to state what the geometry actually guarantees.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **pages**: Two cover templates (full-bleed and framed)
  ([#32](https://github.com/mfozmen/littlepress-ai/pull/32),
  [`37aa749`](https://github.com/mfozmen/littlepress-ai/commit/37aa749a4be4fcd2ac9935b6e79b0dab8a55f6a9))

* feat(pages): two cover templates (full-bleed and framed)

The previous draw_cover crammed title + author + image into an upper/lower split — the drawing felt
  squeezed and the text looked like an afterthought. Replace it with two deliberate templates the
  agent picks between:

- full-bleed (default): the drawing covers the full page; a translucent band at the bottom carries
  the title with the author centred inside it. Best for dramatic illustrations where the artwork is
  the point. - framed: a title band at the top, a letterboxed drawing below, the author in a thin
  strip along the bottom. Calmer; better when the illustration needs breathing room around it.

Cover carries a new ``style`` field (Cover, Draft, book.json, memory). Defaults to "full-bleed"
  everywhere so existing book.json files and saved sessions load unchanged. schema.py validates the
  style on load; agent_tools.set_cover gains an optional ``style`` arg (enum of valid styles in the
  tool schema, rejected at the tool boundary).

Cover-specific config moved to src/config.py (COVER_TITLE_SIZE, COVER_AUTHOR_SIZE, COVER_BAND_H,
  COVER_BAND_ALPHA) so visual knobs aren't buried inside pages.py.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(pages): address PR review for cover templates

- Full-bleed subtitle cleared title descenders. The old formula subtracted COVER_AUTHOR_SIZE + 2mm
  below the title baseline, which left about 3pt between descenders on 'g'/'y'/'p' at 34pt and the
  subtitle's cap height. Bumped the gap to title_size * 0.35, which gives ~12pt / 4mm — enough
  breathing room for descending glyphs. Same formula now in both cover templates.

- Shrink-to-fit long titles. COVER_TITLE_SIZE = 34 made a 25-char English title ("The Brave Little
  Dinosaur") overshoot A5 width (~420pt). Added _fit_title_size() that scales the font down
  proportionally when stringWidth exceeds the available width, with an 18pt floor so extreme cases
  clip rather than shrink to unreadable. Both cover templates call it.

- Validate cover_style at the Draft → Book boundary. Draft.cover_style is a bare str; a typo set by
  anything other than the set_cover tool (memory restore with a legacy value, manual editing, a
  future slash command) would silently render as full-bleed. to_book now raises on unknown styles so
  the REPL path has the same guarantee schema.load_book gives the standalone builder.

- Updated draw_cover docstring to match: by the time we dispatch, the style has been validated by
  either load_book or to_book, so the else-branch isn't a silent fallback for garbage input.

* docs: plan more cover templates + select-cover-template skill

The two templates shipping in PR #32 (full-bleed, framed) cover the two conventions children's books
  use most, but more are worth adding: poster (type-only, for when the child didn't draw a cover),
  portrait-frame (illustration inside a decorative border), title-band-top (colour panel behind
  title), spine-wrap (for the A4 booklet).

More importantly — *which* template fits *which* book is a judgment call, not a menu for the user to
  click through. Mirror the select-page-layout pattern: a .claude/skills/select-cover-template/
  skill encodes the decision rules (title length, tone, image aspect and busyness, whether there's
  even a cover drawing), and the agent consults it before calling set_cover. Renderer stays stupid;
  the reasoning lives in one auditable place.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **providers**: Gemini (Google Gen AI) chat + tool use
  ([#36](https://github.com/mfozmen/littlepress-ai/pull/36),
  [`eb6dca1`](https://github.com/mfozmen/littlepress-ai/commit/eb6dca1c18d24f113d706ed5c4655b8a50c53c1c))

* feat(providers): Gemini (Google Gen AI) chat + tool use

Second fully-wired provider after Anthropic. Matters because Gemini's free tier (1.5k req/day,
  tool-use capable) lets users run Littlepress without a credit card — removing the biggest adoption
  barrier new users hit today.

- GoogleProvider class in src/providers/llm.py with chat() and turn(), lazy-importing google-genai
  so users on another provider don't need the SDK installed. - Message translation at the boundary:
  the agent is written against Anthropic's content-block format, so we translate both directions.
  Assistant tool_use blocks become function_call Parts (role=model); user tool_result blocks become
  function_response Parts (role=tool), with the function name looked up from the preceding tool_use.
  Gemini doesn't always return an id on function_call, so we synthesise one so the agent can
  correlate tool_use with its tool_result. - _check_google validator pings generate_content with the
  spec's validation model (gemini-2.5-flash), classifying by the SDK's error message / status code:
  API-key-not-valid or 401/403 → KeyValidationError; everything else (quota, billing, 5xx) →
  TransientValidationError. Matches the Anthropic contract: resume keeps the saved key on transient,
  drops it on auth. - google-genai bundled as a default dependency — the whole point is letting new
  users start without hunting down extras. - find("google") + create_provider now return
  GoogleProvider when an API key is provided.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(providers): address PR review for Gemini provider

Six valid findings — five in the provider, one in the validator:

1. Timeout wasn't actually forwarded. The Gen AI SDK default is ~600 s which would freeze the REPL
  on a flaky network (PR #12 is the Anthropic equivalent). Both chat() and turn() now build their
  Client via a shared _client() helper that passes http_options=HttpOptions(timeout=60_000). Two
  regression tests pin the contract (one per entry point).

2. Parallel same-name tool calls lost correlation. The synthesised tool_use id was recorded in
  Anthropic format but dropped at translation time. Now the id is forwarded via FunctionResponse.id,
  so two simultaneous read_draft calls return two distinguishable results. Added a
  parallel-same-name test.

3. chat() crashed on SAFETY-blocked prompts. response.text is a property that *raises* ValueError
  when there are no text parts, not just returns a falsy value — `or ""` never fired. Compose the
  reply from candidates[0].content.parts directly via a new _collect_text_from_candidates helper.
  Added a SAFETY test.

4. finish_reason was ignored. SAFETY / RECITATION / MAX_TOKENS all looked like a clean end_turn, so
  the user saw silence with no hint why. _gemini_response_to_blocks now surfaces a synthetic text
  block when finish_reason is non-STOP and there's no real output — stop_reason stays "end_turn"
  since the agent has no other signal to plumb through.

5. Tool input_schema is forwarded raw to FunctionDeclaration. The current tools only use
  Gemini-compatible JSON Schema features; the provider docstring now documents the supported subset
  so a future oneOf / anyOf / $ref user knows to convert up front instead of hitting a call-time
  failure.

6. Validator auth classification was brittle. An English-only "API key" substring check would miss a
  localised reword, and a status-alone check would miss Google's 400-with-"invalid key" surface. Now
  combines isinstance(genai.errors.ClientError) with a 400/401/403 status check, falling back to
  message substrings for SDKs that don't expose the class. New test covers the 400 + ClientError
  path.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **providers**: Gpt (OpenAI) chat + tool use
  ([#37](https://github.com/mfozmen/littlepress-ai/pull/37),
  [`46e33ff`](https://github.com/mfozmen/littlepress-ai/commit/46e33ff4e5c5c9404003c5c2459d619908c7acf7))

* feat(providers): GPT (OpenAI) chat + tool use

Third fully-wired provider, mirroring the Gemini PR's shape:

- OpenAIProvider class in src/providers/llm.py with chat() and turn(), lazy-importing the openai SDK
  so users on another provider don't need it installed. - Message translation at the boundary — the
  agent stays Anthropic- shaped; the provider converts in both directions. Assistant tool_use blocks
  become role=assistant messages with a tool_calls array (arguments serialised as a JSON string, per
  the API); user tool_result blocks split into one role=tool message per result carrying the
  matching tool_call_id. - Non-stop/non-tool_calls finish reasons (length, content_filter) surface
  as a synthetic text block so the REPL isn't silent on a blocked or truncated turn. - Shared
  _client() builder keeps chat() and turn() aligned on the 60-second timeout hedge — same regression
  guard as the Anthropic and Google paths. - _check_openai validator uses the SDK's class hierarchy
  (AuthenticationError / PermissionDeniedError → KeyValidationError, APIError catch-all →
  TransientValidationError). Matches the three-way contract the REPL's resume path depends on. -
  openai bundled as a default dep — many users already have a GPT key and expect it to work without
  hunting down an optional extra. - find("openai") + create_provider now return OpenAIProvider when
  a key is provided; validation_model is "gpt-4o-mini", the cheapest tool-use-capable model.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* build: bump openai and google-genai floors to match code requirements

Review flagged that the declared lower bounds in PR #37 / PR #36 didn't match what the code actually
  needs:

- ``openai>=1.0.0``: ``PermissionDeniedError`` (caught in the auth branch of ``_check_openai``) was
  only added in 1.2.x. The ``APIError`` inheritance chain the transient-branch catch-all relies on
  stabilised even later in 1.x. Bump to 1.50 so the exception classes and hierarchy the validator
  depends on are guaranteed present.

- ``google-genai>=0.2.0``: ``FunctionResponse.id`` (used to correlate parallel same-name tool calls)
  and the stabilised ``HttpOptions`` / ``GenerateContentConfig`` shapes are 1.x-era. Bump to 1.0 so
  an install that happens to resolve to an old 0.x release doesn't import and then explode at
  runtime.

Fresh installs today resolve to modern releases so this is mostly a belt-and-suspenders fix, but
  pinning matches the code's actual expectations — future dependency-resolver changes won't silently
  pull in incompatible versions.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **providers**: Ollama local chat + tool use
  ([#39](https://github.com/mfozmen/littlepress-ai/pull/39),
  [`86748bb`](https://github.com/mfozmen/littlepress-ai/commit/86748bb9c940f2f3783080c3fc4424718dc584d2))

* feat(providers): Ollama local chat + tool use

Fourth and final fully-wired provider, completing the LLM provider work from the plan.

- OllamaProvider in src/providers/llm.py with chat() and turn(), lazy-importing the ollama client so
  users on a cloud provider don't need it installed. - Messages translate at the boundary —
  OpenAI-compatible shape with two Ollama twists: assistant tool_calls carry ``{function: {name,
  arguments: dict}}`` (no outer id — Ollama doesn't issue call ids), and tool results go as ``{role:
  tool, content, tool_name}``. Tool-use ids are synthesised internally so the agent can still
  correlate tool_use with its tool_result in the next turn. - Host (``http://localhost:11434``
  default) and model are configurable on the provider — covers users running Ollama in a container
  or on a remote LAN host. - Timeout widened to 180 s (vs 60 s for cloud) because local first- load
  inference can legitimately be slow; still finite so a stuck daemon doesn't freeze the REPL.

- _check_ollama validator pings the local daemon via ``client.list()``. Unreachable service →
  TransientValidationError with a "make sure Ollama is running" message (not KeyValidationError —
  there's no key to revoke; not ProviderUnavailable — the user can start the daemon and retry). SDK
  missing → ProviderUnavailable as with the other providers.

- validate_key no longer short-circuits on ``requires_api_key=False``. Any provider with a
  registered checker runs it — that's how Ollama's reachability ping gets invoked through the
  picker. Providers with no checker (``none``) still no-op.

- REPL's _prompt_for_provider now runs validate_key for key-less providers too. An unreachable
  daemon shows the validator's message and aborts the picker instead of activating a dead provider.

- ollama bundled as a default dep for parity with the other providers; floor at 0.4.0 so the modern
  client.list() / chat() shapes are guaranteed.

All 428 tests passing; 95% on src/providers/llm.py, 99% on src/providers/validator.py.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(providers): address PR review for Ollama provider

Three valid findings:

1. Resume path bypassed the reachability ping. _resume_or_pick short-circuited on ``not
  requires_api_key`` without checking whether the daemon was up — the exact UX gap the PR claimed to
  prevent. Added _validate_silently(spec, "") on the keyless branch, falling back to the picker on
  failure (matching the keyed-provider's resume path parity). Two new integration tests cover the
  resume happy-path and the dead-daemon fallback.

2. _check_ollama's error message hard-coded localhost:11434 even though the SDK honours OLLAMA_HOST.
  Interpolated from the env var (with the same default) so the message stays correct when users
  eventually configure a remote host.

3. _import_ollama's ``if ollama is None`` guard was unreachable: Python's import statement either
  succeeds (binding a module object, never None) or raises ImportError. Removed the dead branch. The
  same pattern in the other providers predates this PR; not touched here.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **render**: Keep numbered snapshots so renders don't clobber
  ([#30](https://github.com/mfozmen/littlepress-ai/pull/30),
  [`318bf3f`](https://github.com/mfozmen/littlepress-ai/commit/318bf3f585706f1ed6e7021b5a75fba35fdc61a7))

* feat(render): keep numbered snapshots so renders don't clobber

Both the agent's render_book tool and the REPL /render command used to write <slug>.pdf
  unconditionally — rendering the same draft twice silently destroyed the earlier PDF. Now every
  default-path render lands a versioned <slug>-vN.pdf alongside the stable <slug>.pdf, so:

- The stable name still points at the latest render (auto-open and "the book" references stay
  unchanged). - Previous renders are preserved; the user can compare drafts or roll back by copying
  a snapshot over the stable name. - The booklet is versioned the same way —
  <slug>-vN_A4_booklet.pdf alongside the stable <slug>_A4_booklet.pdf. - /render <explicit-path> is
  still the escape hatch; no versioning when the user named a destination themselves.

next_version_number() lives in src/draft.py next to slugify so both entry points share the
  version-space logic (A5 and booklet share the same counter).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(render): address review for versioned renders

- Atomic stable mirror: the render writes to a <dst>.pdf.tmp sibling and os.replace() it into
  position, so a crash mid-copy leaves either the previous stable file or the new one — never a
  half-written PDF that the auto-opener would hand to the user's viewer. New atomic_copy() helper in
  src/draft.py.

- Windows viewer-lock handling: if the stable <slug>.pdf is held open in Acrobat, os.replace raises
  PermissionError. The versioned snapshot still writes (new filename, no lock), so the render hasn't
  failed — we now catch OSError on the mirror step, log a yellow hint telling the user to close the
  viewer, and carry on instead of claiming "Render failed:" catastrophically.

- Namespace-safe version separator: change -vN to .vN. slugify emits a-z0-9_- but never '.', so
  <slug>.vN.pdf can only be produced by the versioner — a book titled "Book-V1" (slug "book-v1",
  stable book-v1.pdf) no longer poisons the version counter of an unrelated "book" slug. Tightened
  the regex in next_version_number.

- Refactor /render to cut cognitive complexity. _cmd_render used to carry the whole path-resolution
  + build + copy + impose pipeline in one function (Sonar flagged 17/15). Split into _require_title,
  _mirror_or_warn, _render_to_file, _impose_to_file, _resolve_versioned_paths, _run_custom_render,
  _run_versioned_render. Main function now does only dispatch.

- Soften the next_version_number docstring: the A5+booklet version space is shared within a single
  render call, but a bare /render followed by /render --impose leaves booklet gaps. Don't claim a
  pairing invariant that the code doesn't enforce.

- Drop the misleading "claim the slot before building" concurrency comment — next_version_number
  only reads the directory, it doesn't reserve anything. The REPL is single-threaded; nothing races.

- docs/PLAN.md gains a deferred "cap / prune old snapshots" item (infinite accumulation was a
  conscious choice but should be revisited from real usage).

- README mentions snapshots accumulate and the new .vN format.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Auto-load PDF when its path is dragged onto the terminal
  ([#25](https://github.com/mfozmen/littlepress-ai/pull/25),
  [`1dc05f0`](https://github.com/mfozmen/littlepress-ai/commit/1dc05f0a3957bd0225d58ba054ae7609e5c37cb2))

* feat(repl): auto-load PDF when its path is dragged onto the terminal

Terminals paste a file's full path when the user drags it onto the window — quoted on Windows
  (PowerShell), escaped on Unix. Detecting that case and routing it through /load saves the user
  from typing "/load " in front every time.

Non-slash input now takes a three-way split: 1. Starts with "/" → slash dispatch (unchanged). 2.
  Resolves to an existing .pdf file → treat as /load <path>. 3. Anything else → agent chat
  (unchanged).

The path classifier is deliberately conservative (.pdf extension AND file exists) so chat mentions
  like "can you open draft.pdf?" still reach the agent instead of being silently swallowed. Reuses
  the _unquote helper from PR #24 so quoted and tilde-expanded paths work.

Seven tests pin happy-path (plain path, quoted path, uppercase .PDF, ~-expansion), guard negatives
  (non-PDF file, chat with a .pdf mention but no such file), and verify /load still works.

README gets a short drag-and-drop blurb; PLAN.md's entry ships.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* test: close remaining meaningful coverage gaps

Four targeted regression tests for branches that were flagged but weren't worth a dedicated scenario
  before:

- _looks_like_pdf_path OSError path — malformed paths (Windows device names, encoding issues) must
  classify as "not a PDF" instead of crashing the dispatcher. - agent.Agent._drive with a mixed
  text+tool_use response — Claude routinely emits "let me check…" alongside the tool call; both the
  text print and the tool_use execution must happen. - _show_key_guidance when webbrowser.open
  raises — locked-down envs (no browser, permission error). URL still surfaces; no "opened the page"
  claim. - _validate_silently with no validator injected — silent resume of a saved key accepts it
  without calling anything. - keyring_store legacy-service get_password failure — load_key swallows
  and continues instead of crashing the REPL.

Total coverage 99% (up from 99% — same percentage, but 10 missed lines down to 2). The two lines
  left (Agent.messages property getter and cli.py's if __name__ == "__main__" guard) are trivial and
  not worth test-for-test's-sake scenarios.

* fix(repl): check PDF classifier before slash dispatch

Addresses review feedback on #25. Real bug on Linux / macOS: dragged paths are absolute
  ("/home/user/draft.pdf", "/Users/...") and start with "/". The original dispatch order checked
  ``line.startswith('/')`` first, so those paths were parsed as unknown slash commands and drag-drop
  silently died.

The Windows tests didn't catch this because tmp_path there starts with a drive letter (C:\Users\...)
  — not a slash.

Hoist the PDF classifier check above the slash check. The classifier is conservative (.pdf extension
  AND file exists), so real commands like /help / /exit / /render can't match.

New regression test (platform-independent, via monkeypatch) simulates the Linux-style absolute-path
  drag and asserts /load is invoked instead of /dispatch_slash.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Claude-code-style / menu with a logical command order
  ([#26](https://github.com/mfozmen/littlepress-ai/pull/26),
  [`7fb61a4`](https://github.com/mfozmen/littlepress-ai/commit/7fb61a406c113787b382b980745521171c6b1544))

* feat(repl): Claude-Code-style / menu with a logical command order

Ships the "Next up" item from PLAN.md.

- New SlashCommand frozen dataclass (name, description, handler). The full catalog lives in
  SLASH_COMMANDS at the bottom of src/repl.py; registration order there drives both /help output and
  the new / menu. Order follows the workflow — load → pages → title → author → render → model →
  logout → help → exit — rather than the incidental alphabetical / insertion order of before. -
  /help now prints each command with its one-line description aligned in a column. -
  src/cli.SlashCompleter plugs into prompt_toolkit. Typing `/` alone suggests every command with its
  description as display_meta; typing `/lo` narrows to /load + /logout; case- insensitive prefix
  match; non-slash input doesn't interrupt chat with a popup. - The CLI swaps builtins.input for a
  PromptSession wired with the completer, but only when stdin is a TTY — non-TTY (pytest, piped
  stdin, CI) falls back to input() so automation and tests keep working.

prompt_toolkit >= 3.0 added to the default dependency list; tests still inject their own read_line
  so they don't need a console.

README slash-command table mentions the new / menu and follows the workflow order; PLAN.md entry
  shipped.

Nine new tests pin the catalog order, descriptions, frozen dataclass invariant, /help output, and
  the completer's four behaviours (bare slash, prefix filter, case-insensitive, non-slash skipped).
  292 tests total; 99% coverage.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix: close six findings on the / menu PR

Addresses review feedback on #26.

1. Repl.commands property return type updated to dict[str, SlashCommand] (was SlashHandler — stale
  after the restructure). 2. Ctrl-C at the main prompt no longer dumps a traceback — matches the
  Claude-Code / shell feel: Ctrl-C clears the line and reprompts, Ctrl-D / /exit actually leaves.
  Picker, key prompt, retry prompt, and y/n confirm also treat KeyboardInterrupt as "cancel, go
  back". 3. SlashCompleter suppresses the menu when the buffer looks path-ish (contains /, \, or .)
  so drag-and-drop paste doesn't flash a /help popup mid-drag. Regression test checks several drag
  snapshots. 4. New regression test pins the non-TTY fallback: PromptSession must NOT be constructed
  when stdin.isatty() is False. 5. SlashCompleter reads document.current_line_before_cursor instead
  of text_before_cursor so a future multiline=True switch doesn't break prefix matching. 6. Comment
  on the isatty() gate rewritten — PromptSession.prompt(), not the constructor, is what needs a real
  console.

295 tests green; coverage 99%.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v1.0.1 (2026-04-15)

### Bug Fixes

- Hide offline picker option + catch broader Anthropic errors
  ([#20](https://github.com/mfozmen/littlepress-ai/pull/20),
  [`2167bcc`](https://github.com/mfozmen/littlepress-ai/commit/2167bcc7eeadaad4b3b1e3cd48c6f9dfc7a018f5))

* fix: hide offline picker option + catch broader Anthropic errors

Two bugs the maintainer hit the first time they ran \`littlepress\` for real.

1. "No model (offline)" was option 1 in the picker but doesn't do anything useful — non-slash input
  just falls to the placeholder path forever. Keep NullProvider as the internal default state (unit
  tests still use it) but drop it from the UI: new PICKER_SPECS tuple filters "none" out, and the
  picker shows only Claude / GPT / Gemini / Ollama numbered 1-4.

2. Validator used to catch only anthropic.AuthenticationError. When the maintainer pasted a valid
  key on a fresh Anthropic account with no credits, messages.create raised BadRequestError ("Your
  credit balance is too low…"), which fell through the except clause and crashed the REPL with a
  traceback.

Now catching anthropic.APIError (the parent class of both auth and billing / rate / 5xx errors) and
  re-raising as KeyValidationError with the server's message, so the user sees a clean "Anthropic
  call failed: credit balance too low…" and can Ctrl-D to add credits.

Tests: - test_picker_hides_the_offline_none_option / _shifts_numbers — pin the new picker UI. -
  test_anthropic_billing_error_surfaces_as_key_validation_error and
  _generic_api_error_does_not_crash — pin the broader error catch. - Every test that dereferenced
  picker numbers or expected "none" as the keyless fallback migrated to "4" / "ollama".

All 261 tests green; src/keyring_store.py and src/providers/llm.py remain 100% covered.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(validator): split transient errors so resume-path doesn't wipe valid keys

Addresses all five review findings on #20. The big one (#1) was that broadening the
  anthropic.APIError catch into KeyValidationError regressed PR #18's transient-vs-auth split:
  during silent resume, _resume_with_key deletes any key that raises KeyValidationError, so a
  rate-limit, a 5xx, or a billing error would silently wipe the user's saved key and force a
  re-paste.

Split the signal into two exceptions:

- KeyValidationError — key is rejected (AuthenticationError / PermissionDeniedError). First-launch
  re-prompts; resume deletes the saved key. - TransientValidationError — key is fine but the call
  couldn't complete (billing, rate-limit, 5xx, network). First-launch shows the message and lets the
  user retry or Ctrl-D; resume KEEPS the saved key and surfaces the message.

Other fixes in this PR:

2. README — removed the stale line that called "No model (offline)" a picker option and described
  what the "skip the key" path was; rewrote the first-launch paragraph around the four real
  providers plus /logout. 3. validator.py module + class docstrings — describe the three signals
  (KeyValidationError / TransientValidationError / ProviderUnavailable) and how each is meant to be
  handled. 4. getattr fallbacks narrowed from bare Exception to RuntimeError so a malformed SDK
  wouldn't accidentally catch KeyboardInterrupt. 5. Added a one-line regression test that
  find("none") still resolves to a keyless spec — the UI hides it but /logout and old session files
  still rely on it.

262 → 263 tests; src/providers/validator.py stays 100% covered.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 1.0.1 [skip ci]
  ([`990cecf`](https://github.com/mfozmen/littlepress-ai/commit/990cecf41b8a99ecc0eb2b84a2552a3e27ecb79a))


## v1.0.0 (2026-04-15)

### Chores

- **release**: 1.0.0 [skip ci]
  ([`0c98f2d`](https://github.com/mfozmen/littlepress-ai/commit/0c98f2dde294ab9211a1ef642ac4b2bc3fec5f3b))

### Documentation

- Mark littlepress-ai rename PR as shipped in PLAN.md
  ([`5873448`](https://github.com/mfozmen/littlepress-ai/commit/5873448cd504342907c7715067fc3f7ebbf3e3de))

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- Rename project to littlepress-ai ([#19](https://github.com/mfozmen/littlepress-ai/pull/19),
  [`409d418`](https://github.com/mfozmen/littlepress-ai/commit/409d418d6de2921153513b9c06da21ecca6c580c))

* chore: rename project to littlepress-ai

Package name: child-book-generator → littlepress-ai (PyPI name). Primary command: littlepress, with
  a littlepress-ai alias so that `uvx littlepress-ai` and `pipx run littlepress-ai` work without
  --from. Brand / title: Littlepress.

BREAKING CHANGE: the `child-book-generator` console script is gone. Users who had it installed
  should `pip install littlepress-ai` and type `littlepress` (or `littlepress-ai`) instead.

Keyring migration: SERVICE moves to "littlepress"; load_key transparently reads any key stored under
  the legacy "child-book-generator" service on first call and moves it to the new name — users who
  already pasted a key don't have to re-paste. Tests cover the migration happy path, the "both
  stores populated" case (current wins), and a read-only keyring that blocks the move but still
  yields the legacy value for this session.

Sonar project key in sonar-project.properties and the README badges are updated to
  mfozmen_littlepress-ai — they'll 404 until SonarCloud binds the renamed GitHub repo (or the
  project is manually renamed in SonarCloud).

GitHub URLs in README / CLAUDE.md / docs all updated. CHANGELOG.md historical URLs are left on the
  old name: GitHub redirects keep them working, and they're accurate about what the repo was called
  at the time.

244 tests still green; both `littlepress` and `littlepress-ai` console scripts resolve to
  src.cli:main.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* test: lift coverage on fonts/pages + fix five Sonar code smells

Coverage: total goes from 98% to 99% with the fonts.py missing-fonts

branch and every pages.py layout branch now exercised.

- tests/test_fonts.py — assert register_fonts raises a FileNotFoundError with the DejaVu download
  link when no .ttf is on the search path, and that _find returns None when SEARCH_DIRS doesn't
  contain the file. Closes the 80% -> 100% gap on src/fonts.py. - tests/test_pages.py — drive each
  draw_page layout (image-full with and without text, image-bottom, image-top, text-only, image-*
  with no image falling back to text-only) plus _wrap edge cases (blank paragraphs surviving, a word
  too wide for the line starting a fresh one) and _draw_text_block's non-centered align path.

Refactors triggered by SonarCloud critical code-smell findings (no behaviour change, all 255 tests
  stay green):

1. src/agent_tools.py — duplicated "(unset — ask the user)" and "No draft loaded. Ask the user to
  provide a PDF first." literals collapse to _MSG_UNSET / _MSG_NO_DRAFT module constants. 2.
  src/agent_tools.py — propose_typo_fix_tool.handler split into _reject_typo_fix / _find_typo_match
  / _build_typo_prompt helpers to bring cognitive complexity under the 15 limit. 3. src/repl.py —
  _resume_or_pick split into _saved_spec + _resume_with_key; each helper has one responsibility and
  fits in the complexity budget. 4. src/pages.py — _wrap split into _wrap_paragraph; the outer loop
  is now a two-branch paragraph iterator.

* fix(keyring): sweep orphaned legacy entries + keep child-book-generator alias

Addresses review feedback on #19 for the two real issues.

1. Keyring legacy entries could orphan forever. load_key used to do the legacy → current migration
  only when the current service had no entry. If set_password(current) succeeded but delete_password
  (legacy) failed, the next load_key would find the current entry first and short-circuit before
  re-entering the migration loop — the stale legacy credential then lived in the OS keychain
  indefinitely. Fix: every load_key now sweeps any legacy entry sitting next to a valid current one,
  and delete_key (used by /logout) clears legacy entries too.

2. Dropping the child-book-generator console script with no alias silently broke editable installs
  that had the old name on their PATH. Add child-book-generator as a deprecated alias in
  [project.scripts] for one release; plan to remove in the next minor bump.

Two new regression tests pin the sweep behaviour on both load_key and delete_key paths. 257 tests
  green.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### BREAKING CHANGES

- The `child-book-generator` console script is gone. Users who had it installed should `pip install
  littlepress-ai` and type `littlepress` (or `littlepress-ai`) instead.


## v0.7.0 (2026-04-15)

### Chores

- Consolidate slugify and refresh docs ([#17](https://github.com/mfozmen/littlepress-ai/pull/17),
  [`365ca46`](https://github.com/mfozmen/littlepress-ai/commit/365ca46ab9aeb2f40b37a118accc76e2f1355b0f))

* chore: consolidate slugify and refresh CLAUDE.md + README

Ships PR #17 from docs/PLAN.md (cleanup). Nothing behavioural changes; the codebase just shrinks a
  bit and the docs stop describing the pre-agent world.

- Drop build._slugify. build.py imports slugify from src.draft, which is the single source of truth
  (the REPL's /render and the agent's render_book tool already use it). Their tests in
  tests/test_draft.py cover every branch; the three duplicate tests in tests/test_build.py go away.
  - CLAUDE.md Architecture section redrawn around the agent-first flow (cli → repl → agent → tools →
  renderer). Adds the new modules (agent, agent_tools, memory, providers) that shipped between PRs
  #13-#16. Old "Current state" section and the p1/p2 phase hint in Open TODOs are gone —
  docs/PLAN.md is the single roadmap now. - README Status bullet list rewritten as a short "what it
  does today" paragraph. The feature-by-feature ✅ list served the pivot era but isn't how users read
  a README.

225 tests green.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* docs: trim shipped items from PLAN.md and name the agent in slugify bullet

Addresses both review findings on #17.

1. PLAN.md still listed the slugify consolidation and the README/ CLAUDE.md refresh as pending work
  even though this PR ships them. Remove both bullets. Convert the rest of the cleanup list
  ("_CHECKERS placeholder", "Draft vs Book", "examples/", "slash commands") into "intentionally
  kept" items so the decision is documented for future cleanup passes.

2. CLAUDE.md said slugify was shared by "the REPL's /render and build.py" — skipped the agent's
  render_book tool (arguably the primary caller in the agent-first flow). Reword to name all three
  call sites.

225 tests still green.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **release**: 0.7.0 [skip ci]
  ([`00886c1`](https://github.com/mfozmen/littlepress-ai/commit/00886c1e897be0eac6cc18c518217290e9bac515))

### Documentation

- Mark agent-first pivot plan as shipped
  ([`bbcd84c`](https://github.com/mfozmen/littlepress-ai/commit/bbcd84cbd7970a104c46fa62f84ce232c047ebb5))

All five PRs (#13-#17) from docs/PLAN.md merged. Rewrite the file as a status record of what
  shipped, which earlier cleanup candidates were intentionally kept (with reasoning), and which
  items stay deferred unless the user asks. The "Done when" checklist is now all boxes checked.

Docs-only; no code change.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- **repl**: Guided API-key setup + keyring so users paste only once
  ([#18](https://github.com/mfozmen/littlepress-ai/pull/18),
  [`1a1ec9c`](https://github.com/mfozmen/littlepress-ai/commit/1a1ec9c3bfe2b719a53fc6bcad98af6ed7527d3f))

* feat(repl): guided API-key setup + keyring so users paste only once

Ships PR #18. Two UX wins in one commit:

1) Zero-extras install. anthropic and keyring move out of the [anthropic] optional extra and into
  default dependencies, so `pip install child-book-generator` just works — no extra dance for the
  user to remember.

2) One-time key entry. - ProviderSpec gains key_url + key_steps so each cloud provider carries its
  own onboarding text (Anthropic, OpenAI, Google). - _prompt_for_provider opens the provider's
  key-creation page in the user's default browser and prints a numbered set of steps above the
  secret prompt — new users aren't hunting for the link. - After a successful validation the REPL
  writes the key to the OS credential manager via keyring (Windows Credential Manager / macOS
  Keychain / Linux Secret Service). - _resume_or_pick reads the key back on the next launch and
  re-validates silently. A valid key means the user never sees a prompt at all. If the key was
  rotated/revoked, we delete it and drop back to the prompt. - New /logout command forgets the saved
  key and drops the session to offline so the user can switch accounts. - All keyring failures
  (headless Linux, locked-down containers) degrade silently — the REPL keeps working; the user just
  has to re-paste next launch.

Testing hardening: - tests/conftest.py auto-isolates the keyring (in-memory fake) so no test touches
  the developer's OS credential manager, and auto-blocks webbrowser.open so a suite run doesn't
  flood the browser with tabs.

Coverage: src/keyring_store.py 100%, src/repl.py stays near 100%.

Total 98%. 239 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(repl): close five review findings on #18

1. _validate_silently used to catch every Exception and return False, so a transient network timeout
  during silent resume-validation would silently delete the user's saved key. Narrow the deletion to
  KeyValidationError only: other exceptions keep the saved key and surface a "couldn't verify"
  warning — the key might still be valid, and forcing a re-paste over a flaky network is hostile. 2.
  docs/PLAN.md: move keyring persistence out of "explicitly deferred" and into the shipped-PR table;
  this PR is the one that lands it. 3. validator.py's missing-SDK install hint pointed at the old
  [anthropic] optional extra, which this PR removes. Suggest pip install --force-reinstall instead.
  4. keyring_store.delete_key used a fragile getattr(...).__dict__.get(...) guard for
  PasswordDeleteError. A bare except Exception already followed and covered the real failure modes;
  simplify to one clause. 5. _show_key_guidance assumed webbrowser.open either opens or raises, but
  on headless Linux (no $DISPLAY / $BROWSER) it returns False silently. Check the return value and
  only print "opened the page in your browser" when it actually did.

Two new regression tests pin the transient-error and headless-browser behaviours. 241/241 green;
  src/keyring_store.py stays 100% covered.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.6.0 (2026-04-15)

### Chores

- **release**: 0.6.0 [skip ci]
  ([`82066f0`](https://github.com/mfozmen/littlepress-ai/commit/82066f05b2e00f917e832582d8821373c0bd0fb4))

### Features

- **memory**: Persist the draft so the next launch resumes
  ([#16](https://github.com/mfozmen/littlepress-ai/pull/16),
  [`82e71a3`](https://github.com/mfozmen/littlepress-ai/commit/82e71a398671396856cd00719a819ff8d69e238e))

* feat(memory): persist the draft so the next launch resumes

Ships PR #16 from docs/PLAN.md. After every REPL turn (slash command or agent tool call) the current
  Draft is written to .book-gen/draft.json. When the user runs 'child-book-generator draft.pdf'
  again and a memory file exists whose source_pdf matches, the CLI restores that draft instead of
  re-ingesting from the PDF — the agent picks up with title / author / cover / per-page layouts and
  edits already in place and only asks about what's still missing.

- src/memory.py — save_draft / load_draft + atomic write via tempfile + os.replace. Corrupt /
  missing / non-object JSON degrades to load_draft -> None so the REPL falls back to a fresh ingest.
  load_draft takes expected_source so memory for draft A isn't silently applied to draft B. -
  Preserve-child-voice: whitespace on cover_subtitle and back_cover_text round-trips verbatim
  through the serialiser. - Repl._persist_draft fires after the agent greeting turn and after every
  _dispatch call. Write failures surface as a dim 'could not save draft memory' line and never kill
  the session. - CLI: when given a PDF, prefer memory.load_draft over draft.from_pdf if one matches.
  Mismatched memory is ignored.

Coverage: src/memory.py, src/repl.py, src/draft.py all 100%;

total 98%. 220 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(memory): harden draft persistence per review feedback on #16

Addresses all eight findings. Six were correctness / crash-safety bugs; two were misleading
  docstrings.

- Path normalisation: _to_dict now resolve()s every path before serialising, and load_draft compares
  resolved paths. `./book.pdf` and `/abs/book.pdf` referring to the same file both unlock the
  memory; the CLI also resolve()s the argv PDF before handing it to the REPL. - fsync before
  os.replace so a power loss between replace() and writeback can't leave a zero-byte draft.json and
  silently wipe the session's state. - Stale tmp sweep: every save_draft removes any sibling
  .draft.*.tmp files from a prior SIGKILL crash. Cleanup is best-effort and tolerates unlink
  failures. - Schema versioning: serialised dict carries "version": 1. Unknown future versions fall
  through to None instead of reading stale fields with new meanings. - ensure_ascii=False: Turkish
  and emoji stay readable in draft.json, not escaped into \uXXXX. Aligned with preserve-child-voice
  (the child's actual words are visible on disk). - _resolve() falls back to .absolute() on OSError
  so Windows paths that can't be resolved still compare cleanly. - Module docstring: say "after each
  user interaction" (covers slash commands and agent turns) and drop the misleading claim of a
  dedicated typo-approval log — approved fixes already live in DraftPage.text, which round-trips
  verbatim.

228 tests; src/memory.py stays 100% covered.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.5.0 (2026-04-15)

### Chores

- **release**: 0.5.0 [skip ci]
  ([`715bbf4`](https://github.com/mfozmen/littlepress-ai/commit/715bbf49893a801fe1dab1c8b82312482ff13b62))

### Features

- **agent**: Render_book tool — agent produces the finished PDF itself
  ([#15](https://github.com/mfozmen/littlepress-ai/pull/15),
  [`781c52b`](https://github.com/mfozmen/littlepress-ai/commit/781c52bcd991c77505880c2a9f0738e62066ea99))

Ships PR #15 from docs/PLAN.md. Once the draft has a title (and ideally author + cover), the agent
  can call render_book itself instead of asking the user to type /render.

- src/agent_tools.render_book_tool wraps to_book + build_pdf + optional impose_a5_to_a4. Output goes
  to <session-root>/.book-gen/output/<slug>.pdf, mirroring the slash command. - impose=true also
  writes <slug>_A4_booklet.pdf; a booklet failure keeps the A5 on disk and surfaces the error in the
  tool result. - Guards: no draft, no title, build failure — each returns a descriptive string the
  agent can relay, never raises. - Schema exposes only impose (bool); required=[] so the agent can
  call it with no arguments for the A5-only path.

REPL registers the tool with get_session_root = (session_root or cwd)/.book-gen so the slash command
  and the agent tool put files in the same place.

Coverage: src/agent_tools.py and src/repl.py remain 100%; total 98%.

204 tests.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.4.0 (2026-04-15)

### Chores

- **release**: 0.4.0 [skip ci]
  ([`5901df2`](https://github.com/mfozmen/littlepress-ai/commit/5901df26af9ab74488ca0bae2020392ad59d6760))

### Features

- **agent**: Edit tools — typo fix, metadata, cover, layout
  ([#14](https://github.com/mfozmen/littlepress-ai/pull/14),
  [`1c28559`](https://github.com/mfozmen/littlepress-ai/commit/1c28559ebc44d2730484c9581105d57884954250))

* feat(agent): edit tools — typo fix, metadata, cover, layout

Ships PR #14 from docs/PLAN.md. The agent now has four additional tools plus a user-confirmation
  path so it can actually build up a book through conversation:

- propose_typo_fix(page, before, after, reason) — the ONLY way page text ever changes. Bounded to
  mechanical substitutions (≤30 chars and ≤3 words per side) and requires a REPL-level y/n. Rejects
  missing 'before' substrings so the agent can't invent edits. - set_metadata(field, value) — title,
  author, cover_subtitle, back_cover_text. Page text is explicitly NOT a valid field; the enum on
  the input_schema keeps the model honest, and the handler double-checks. - set_cover(page) — use
  one of the draft's drawings as the cover. Rejects pages without a drawing. - choose_layout(page,
  layout, reason) — set per-page layout. Enforces select-page-layout rule 1 (imageless → text-only)
  at the tool boundary; rejects invalid layout names.

Infrastructure: - Draft grows layout, cover_image, cover_subtitle, back_cover_text fields (all
  optional, default empty). to_book projects them into the Book the renderer wants. -
  Repl._confirm(prompt) reads a y/n via the existing read_line, accepting 'y' / 'yes' / 'evet' / 'e'
  for yes and treating EOF / anything else as no. Preserve-child-voice: silence is never 'yes,
  change the kid's words'.

Coverage: src/agent_tools.py, src/repl.py, src/draft.py, all

100%; total 98%. 193 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(agent): close three preserve-child-voice holes in edit tools

Addresses review feedback on #14. Each finding was a real path for agent-driven silent mutation of
  the child's words; each now has a regression test.

1. propose_typo_fix accepted empty 'before', turning a 'fix' tool into a 'insert arbitrary text at
  position 0' tool. Reject empty 'before' explicitly, before prompting the user.

2. propose_typo_fix did naive substring replace — 'cat' → 'dog' rewrote 'scatter' into 'sdogter'.
  Match with word boundaries (\b via regex) so only whole-word typos match, and include ±25 chars of
  surrounding page text in the y/n prompt so the user sees what they're approving instead of just 'a
  → b'.

3. set_metadata silently .strip()'d every value, including the child-voice fields cover_subtitle and
  back_cover_text. Keep the strip on title/author (conventional metadata) but preserve whitespace
  verbatim for child-voice fields.

197 tests; src/agent_tools.py remains 100% covered.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.3.0 (2026-04-15)

### Chores

- **release**: 0.3.0 [skip ci]
  ([`023c5ab`](https://github.com/mfozmen/littlepress-ai/commit/023c5abef0fdd8f801e90d7231fb8a681f9194f5))

### Documentation

- Replace phase files with agent-first PLAN.md
  ([`928ec6f`](https://github.com/mfozmen/littlepress-ai/commit/928ec6f8c3ce1bd8210ae3809eb1b6bfaaa139bf))

Drop the p0-p5 phase files that described the old slash-command-heavy roadmap. The project is
  pivoting to an agent-first CLI — the user points at a PDF, a model walks the conversation, the
  book comes out the other side.

New docs/PLAN.md lays out the pivot as four feature PRs (#13 agent core, #14 edit tools, #15 render
  tool, #16 project memory) plus a cleanup PR (#17) to cut anything the agent-first flow makes
  redundant. Deferred items (keyring, OCR, illustration generation, parametric layout) are called
  out explicitly so we don't drift back into feature creep.

docs/README.md now points at PLAN.md as the single source of truth for open work.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- **agent**: Tool-use agent loop with read_draft tool
  ([#13](https://github.com/mfozmen/littlepress-ai/pull/13),
  [`af2b5fd`](https://github.com/mfozmen/littlepress-ai/commit/af2b5fd81831f80ccd608b3288b27b9164657e67))

* feat(cli): accept a PDF path positionally and auto-load it

First slice of the agent-first pivot (docs/PLAN.md #13). Running `child-book-generator draft.pdf`
  now drops the user into the REPL with the draft already ingested — no manual /load step. Missing
  or unreadable PDFs exit non-zero with a clear error.

Repl grows a set_draft() seam the CLI uses to inject the draft before run() starts.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* feat(agent): tool-use agent loop with a read_draft tool

First slice of the agent-first pivot (docs/PLAN.md PR #13). When a real LLM is active, non-slash
  input now flows through an Agent that can call tools instead of a plain single-turn chat.

New pieces: - src/agent.py — Agent, Tool, AgentResponse. The agent drives an LLM turn-loop using
  Anthropic's content-block wire format: text blocks print, tool_use blocks fire handlers,
  tool_result blocks get fed back until the LLM emits end_turn. - src/agent_tools.py —
  read_draft_tool factory. Read-only summary of the loaded Draft; the child's text flows through
  verbatim (preserve-child-voice is enforced by tool surface — there is no tool that edits page
  text). - LLMProvider grows a turn(messages, tools) method. AnthropicProvider implements it with
  the SDK's tools parameter; NullProvider raises so the offline path short-circuits before an agent
  call.

REPL wiring: - _build_agent constructs an Agent with read_draft on every provider activation (both
  the first-run picker and /model). - _dispatch_chat now calls self._agent.say(line) instead of the
  raw llm.chat(). - When the CLI pre-loads a draft AND a real provider is active, run() opens with a
  scripted "greet the user and read the draft" turn. Offline stays quiet.

CLI: - child-book-generator draft.pdf auto-loads the draft via repl.set_draft() before run() starts.
  Missing / unreadable PDFs exit non-zero with a clear error.

Coverage: src/agent.py, src/agent_tools.py, src/repl.py,

src/providers/llm.py all 100%; total 98%. 168 tests.

* docs: refresh stale module docstrings in repl.py and providers/llm.py

Both docstrings pre-dated this PR and pointed at: - the old docs/p2-01-tool-suite-and-agent-loop.md
  (consolidated into docs/PLAN.md in 928ec6f), and - "agent-backed behaviour lands in a follow-up
  PR" / "chat() is single-turn" claims that this PR itself disproves.

Rewrite both to describe the current shape: LLMProvider has chat() for quick text replies and turn()
  for the agent tool-use loop; the REPL routes non-slash input through the agent.

Addresses review feedback on #13.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.2.0 (2026-04-13)

### Chores

- **release**: 0.2.0 [skip ci]
  ([`086efcc`](https://github.com/mfozmen/littlepress-ai/commit/086efcc94ec8cb3c2a275acc3defb43935cd80bd))

### Features

- **repl**: Forward non-slash input to the active LLM
  ([#12](https://github.com/mfozmen/littlepress-ai/pull/12),
  [`17fbee4`](https://github.com/mfozmen/littlepress-ai/commit/17fbee470a226ebbce59fc09271853d2dcb22b3d))

* feat(repl): forward non-slash input to the active LLM for single-turn chat

Add an LLMProvider protocol and two concrete implementations in src/providers/llm.py:

- NullProvider — offline default; chat() raises so callers must gate. - AnthropicProvider — Claude
  via the anthropic SDK (lazy import so the offline path doesn't need the extra installed).

create_provider(spec, api_key) returns the right instance; providers that haven't grown chat() yet
  (OpenAI / Google / Ollama) fall back to NullProvider so the REPL keeps running with the offline
  placeholder.

Wire the REPL to build an LLMProvider on activation (initial and /model) through an injectable
  llm_factory. Non-slash input now:

- With NullProvider: prints "(no model selected — pick one with /model) <input>" so the user knows
  why nothing happened. - With a real provider: forwards the line verbatim (preserve-child- voice)
  and prints the plain-text reply.

Errors from the LLM (network, rate limits, etc.) surface as "LLM error: <msg>" and the REPL keeps
  running instead of crashing.

Single-turn today — each line is sent as a fresh one-message conversation. Multi-turn memory and
  tool use land with the agent loop (p2-01) in a follow-up PR.

Coverage: src/providers/llm.py and src/repl.py both 100%; total 98%.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(llm): bound the Anthropic chat SDK call with a finite timeout

The SDK default is ~600 s; a flaky network would freeze the REPL mid-conversation for up to 10
  minutes. Pass a 60 s timeout when constructing the Anthropic client inside AnthropicProvider.chat
  — same shape as the validator's ping timeout fixed in PR #6.

New test asserts the chat client is built with a non-None timeout in the 0-300 s range, so a future
  refactor can't silently drop it.

Addresses review feedback on #12.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.1.0 (2026-04-13)

### Bug Fixes

- **ci**: Correct action major versions
  ([`d42bef5`](https://github.com/mfozmen/littlepress-ai/commit/d42bef5297dd6563b171dde8fd1d08e43dbba097))

actions/setup-python v7 does not exist — revert to v6 (current latest). Bump
  SonarSource/sonarqube-scan-action v6 → v7 (current latest).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 0.1.0 [skip ci]
  ([`8c47e96`](https://github.com/mfozmen/littlepress-ai/commit/8c47e96e118f8d6279665eb3505bd21959e0aaee))

### Continuous Integration

- Bump GitHub Actions to latest major versions
  ([`a46d0bd`](https://github.com/mfozmen/littlepress-ai/commit/a46d0bd911202fe4d5fd15291b6f4960856a0ecb))

Update actions/checkout v4→v6, actions/setup-python v5→v7, and SonarSource/sonarqube-scan-action
  v4→v6.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Stop running the PSR build step until we actually publish
  ([#11](https://github.com/mfozmen/littlepress-ai/pull/11),
  [`e3dbf03`](https://github.com/mfozmen/littlepress-ai/commit/e3dbf038817ae45b105abf594ee42fe61b51bfe9))

The release workflow was failing on every push to main because PSR's default build_command (python
  -m pip install build && python -m build) couldn't install into the /psr/.venv inside the action's
  container. Since upload_to_pypi is false and we're not publishing artifacts yet, the build step
  produces nothing we use.

Set build_command = "" and upload_to_release = false so PSR only: - bumps the version in
  pyproject.toml per Conventional Commits - writes CHANGELOG.md - tags the release - cuts a GitHub
  Release with auto-generated notes

The publish-action step in release.yml is dropped for the same reason; it gets added back when PyPI
  (or another artifact target) lands.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Documentation

- Add SonarCloud badges and refresh README
  ([`5905f50`](https://github.com/mfozmen/littlepress-ai/commit/5905f50287d91579403e6d2f3dee8185926cb93f))

Add Quality Gate, Coverage, Maintainability, Reliability, Security, and License badges linked to the
  SonarCloud project. Update the Project layout section to reflect the current tree (examples/,
  tests/, src/pdf_ingest) and root-anchored gitignore. Add a short Testing section and a Roadmap
  covering the dynamic PDF ingestion pipeline. Restate the "child as real author" principle in the
  tagline.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Adopt Conventional Commits convention
  ([`a6a79d8`](https://github.com/mfozmen/littlepress-ai/commit/a6a79d85eb8adf4f0d9ee2ae915e8c8716f3fa99))

Require the generating-conventional-commits skill for every commit in this repo so messages stay
  standardized and automation-friendly.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Allow non-English strings as test fixture input data
  ([`0704e90`](https://github.com/mfozmen/littlepress-ai/commit/0704e90eaa3a9cc042fe051694c2c2d8ab2d1675))

Codify the rule the maintainer set on 2026-04-13 after review feedback confused Turkish/emoji
  fixture strings for an English-only violation. Test fixture input (Unicode content, OCR Turkish
  samples, preserve-child-voice round-trips) may use any language — the surrounding code stays
  English.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Move roadmap into per-task files under docs/
  ([`6340658`](https://github.com/mfozmen/littlepress-ai/commit/63406580210972dd5cdb550761f0d67770793f18))

Keep README focused on what the project is and how to use it. Move internal planning into docs/ —
  one Markdown file per open task, deleted when the task ships.

Phase 1 tasks drafted: image extraction, book.json synthesis, interactive gap-fill for missing
  metadata, --from-pdf CLI wiring, opt-in handwriting OCR. Phase 2 (layout improvements)
  placeholder.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Pivot plan to AI-first interactive CLI
  ([`ecd9a31`](https://github.com/mfozmen/littlepress-ai/commit/ecd9a31e42a83e9f4dccd1bf466843dccb4de3ed))

Replace the old Phase 1-2 task files with a new phase plan covering: packaging/zero-install launch
  (p0), REPL + provider selection (p1), tool suite + agent loop (p2), illustration generation (p3),
  OCR (p4), and layout assistance (p5). Update preserve-child-voice skill to draw the line at
  story-vs-surface: mechanical typo/OCR fixes allowed, story and meaning never change.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Promote conventional-commits skill to project-level
  ([`da9c98c`](https://github.com/mfozmen/littlepress-ai/commit/da9c98c15d3b3b6f10535b70a51659d17177faad))

Move generating-conventional-commits from user-level to .claude/skills/ so the repo-specific
  type-selection rules (notably: CI config is `ci:`, never `fix(ci):`) travel with the project.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Reframe README around PDF-driven ingestion
  ([`29a007e`](https://github.com/mfozmen/littlepress-ai/commit/29a007ef29804d021e803c281481a61096828ec6))

The primary input is a child's draft PDF, not a hand-authored book.json. Update the tagline, add a
  "How it works" section, mark the current JSON-only flow as temporary, and preview the coming
  --from-pdf command. book.json is now positioned as an intermediate checkpoint, not the main input.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Require one branch and PR per feature or fix
  ([`23a5e67`](https://github.com/mfozmen/littlepress-ai/commit/23a5e67ec06d923aac9d2f9a84587e3b88a38ef1))

Codify the branch-and-PR workflow that the maintainer adopted on 2026-04-13: no direct-to-main
  commits for production code, every

change goes through a branch named <type>/<slug> and a PR for review. Docs-only changes may still go
  directly to main.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- **cli**: Ship child-book-generator console entry point
  ([#2](https://github.com/mfozmen/littlepress-ai/pull/2),
  [`2eba7b3`](https://github.com/mfozmen/littlepress-ai/commit/2eba7b3c213a8727992d9375729e4264cba91122))

* feat(cli): ship child-book-generator console entry point

Add pyproject.toml with package metadata, dependencies, and a console script (child-book-generator =
  src.cli:main) so the project can be launched with uvx / pipx / pip install without a venv dance.
  src/cli.py is a minimal stub that handles --version and --help today; the interactive REPL lands
  in Phase 1 (docs/p1-01).

Drop requirements.txt in favour of the [dev] extra in pyproject, and point CLAUDE.md + the
  SonarCloud workflow at the new install path. README gains a zero-install section listing uvx,
  pipx, and pip paths.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* ci: automate releases with python-semantic-release

Add a release workflow that runs on every push to main. It reads the Conventional Commit history,
  bumps the version in pyproject.toml accordingly (feat -> minor, fix/perf -> patch, BREAKING CHANGE
  -> major), tags the release, writes CHANGELOG.md, and publishes the artifacts to a GitHub Release.

Configure python-semantic-release in pyproject.toml so the version field is managed by the tool — no
  manual bumps. Start the pyproject version at 0.0.0; the first release run on main will compute the
  real version from the commit history.

Also cover the previously-untested _resolve_version() fallback in src/cli.py so the
  PackageNotFoundError branch is exercised.

* ci: align release workflow with repo's v6 action versions

sonar.yml and prior CI commits (a46d0bd, d42bef5) standardized on actions/checkout@v6 and
  actions/setup-python@v6. The new release workflow was pinned to @v4 / @v5 — bring it in line.

Addresses review feedback on #2.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **examples**: Add runnable example book
  ([`9dcbc53`](https://github.com/mfozmen/littlepress-ai/commit/9dcbc53d5096b6c5abddf09534734314c9968a1e))

Adds examples/book.json plus four placeholder PNG illustrations so new users can produce a PDF
  immediately with: python build.py examples/book.json

Root-anchor the book.json and images/ gitignore patterns so the private user content is still
  ignored while examples/ is tracked. README gets a "Try the example" section.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **pdf-ingest**: Extract embedded images per PDF page
  ([#1](https://github.com/mfozmen/littlepress-ai/pull/1),
  [`83dde82`](https://github.com/mfozmen/littlepress-ai/commit/83dde8286d3a09fd48db378022197e3d8f8c7319))

* feat(pdf-ingest): extract embedded images per PDF page

Add extract_images(pdf_path, out_dir) -> list[Path | None] to walk the PDF and write each page's
  first embedded image to disk as page-NN.png. Pages without an image return None so downstream
  gap-fill can ask.

This feeds the upcoming load_pdf agent tool: the REPL agent will call it when a PDF is loaded, then
  ask the user per page whether to keep the extracted drawing or generate a new illustration.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(pdf-ingest): derive image extension from bytes, not PDF label

pypdf's image_file.name can be extensionless on some PDFs (e.g. 'Im0'), which made the .name-based
  suffix fall back to '.png' even when the underlying bytes were JPEG. Use PIL's detected format
  instead so the file extension always matches the actual bytes.

Addresses review feedback on #1.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **pdf-ingest**: Extract raw page text without transforming it
  ([`4af1934`](https://github.com/mfozmen/littlepress-ai/commit/4af1934969b394903577e11e0df21846aa255b34))

First step of the dynamic ingestion pipeline. extract_pages(pdf_path) returns each page's text via
  pypdf, in order, with no cleaning or rewriting — honouring the preserve-child-voice contract.

TDD: RED via NotImplementedError stub, GREEN via minimal pypdf call.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /load slash command ingests a PDF draft
  ([#7](https://github.com/mfozmen/littlepress-ai/pull/7),
  [`36208d6`](https://github.com/mfozmen/littlepress-ai/commit/36208d6a12925cdd052a852c06fb2496d3f86fc9))

* feat(repl): /load slash command ingests a PDF draft into the session

Add src/draft.py with Draft / DraftPage dataclasses and a from_pdf() helper that zips
  extract_pages() + extract_images() into a page-ordered structure. Unlike schema.Book this is
  deliberately lenient — a freshly-ingested draft may still be missing title/author/cover, and
  filling those gaps is what the REPL walks the user through.

Wire a new /load slash command into the REPL: - /load — usage hint - /load <path> — ingest the PDF,
  populate repl.draft, print a one-line summary ("Loaded N pages (M with an embedded
  illustration).") - Missing / non-PDF input — reports a clean error, state unchanged. - Re-running
  /load replaces the previous draft.

Extracted images land under <session-root>/.book-gen/images/ so the existing gitignore rule covers
  them and session state stays in one directory.

Preserve-child-voice: the ingestion path copies page text verbatim

from pdf_ingest.extract_pages(). No editing at this layer.

Coverage: src/draft.py and src/repl.py at 100%; total 97%. 99 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(repl): expand ~ in /load paths and parse each PDF only once

Addresses two review findings on #7:

1. /load ~/drafts/book.pdf failed with "File not found" because the path string was handed to Path()
  without expanduser(). Call .expanduser() before the existence check.

2. from_pdf() parsed the PDF twice — once in extract_pages() and once in extract_images() — because
  each helper opened its own PdfReader. This was the concern flagged on #1 and deferred to the
  consolidation point; from_pdf IS that consolidation point, so open the reader once and thread it
  through both helpers. extract_pages() and extract_images() now accept an optional reader kwarg for
  the same reason.

New tests pin both fixes: a tilde-expansion test and a PdfReader call-count guard in from_pdf.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /pages introspection plus /title and /author metadata setters
  ([#8](https://github.com/mfozmen/littlepress-ai/pull/8),
  [`d3c8885`](https://github.com/mfozmen/littlepress-ai/commit/d3c8885697bd9c239869d6d7f433592611c5c206))

Add three slash commands that operate on the in-memory draft:

- /pages list each page with a "drawing" / "no image" marker and a preview of the child's text
  (truncated past 60 characters with an ellipsis so long narrations don't flood the terminal). -
  /title [name] no-arg shows the current title; with arg sets it. Surrounding whitespace is
  stripped. - /author [name] same shape — no-arg shows, arg sets.

All three refuse to run without a loaded draft and point the user at /load. Draft gains title and
  author string fields (default empty).

The child's text flows through verbatim: /pages renders a preview, never edits the source. /title
  and /author only touch metadata — the child's words are never routed through either command.

Coverage: src/repl.py and src/draft.py remain 100%. 112 tests total.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /render --impose writes the A4 booklet alongside the A5
  ([#10](https://github.com/mfozmen/littlepress-ai/pull/10),
  [`b457453`](https://github.com/mfozmen/littlepress-ai/commit/b45745345c0eda3a9293c57bd7de1cc4d199b271))

* feat(repl): /render --impose also writes the A4 saddle-stitch booklet

Parse --impose on /render. When set, the command builds the A5 PDF as before and then calls
  src.imposition.impose_a5_to_a4 to write a sibling <slug>_A4_booklet.pdf — ready to print
  double-sided on A4, fold, and staple.

Positional path arg and --impose are order-independent: /render --impose /render --impose
  custom/out.pdf /render custom/out.pdf --impose

If the booklet step fails, the A5 stays on disk so the user isn't empty -handed; the imposition
  error is reported and the REPL keeps running.

Coverage: src/repl.py remains 100%; 128 tests total.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(repl): preserve whitespace in /render path and guard tilde branch

Addresses review findings on #10:

1. /render --impose my book.pdf (two spaces) used to go through args.split() + ' '.join() and
  silently collapse into a different filename. Replace the naive tokenisation with a regex that
  strips the --impose token as a standalone word, leaving the rest of the args string exactly as
  typed. New regression test pins a custom path that contains a double-space path component.

2. Add a regression test that /render ~/book.pdf expands the tilde. The expanduser() call was
  already there (from PR #7) but had no test guarding it against a future refactor.

src/repl.py stays 100% covered; 130 tests.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /render builds the A5 PDF from the loaded draft
  ([#9](https://github.com/mfozmen/littlepress-ai/pull/9),
  [`62671c0`](https://github.com/mfozmen/littlepress-ai/commit/62671c06f54439908b6af955bffc77bf380f4ecb))

* feat(repl): /render builds the A5 PDF from the loaded draft

Ship the end-to-end slice: user runs /load, /title, (/author), then /render and gets a real PDF on
  disk. No LLM involvement yet — this is the deterministic pipeline the agent loop (p2-01) will
  later call as a tool.

New helpers in src/draft.py: - to_book(draft, source_dir) — project Draft into the strict Book shape
  the renderer wants. Rewrites absolute image paths to relative-under-source_dir; falls back to the
  absolute path when an image lives outside (preserve-child-voice covers drawings too). Rejects
  empty/whitespace titles so the renderer never produces an unnamed file. - slugify(title) —
  filesystem-safe filename, mirroring build._slugify. The two should be consolidated in a follow-up
  PR.

New slash command /render: - /render → writes to <session>/.book-gen/output/<slug>.pdf - /render
  <path> → custom output location (tilde-expanded) - Missing draft / missing title → guided error,
  not crash - Build failures surface as "Render failed: <msg>" instead of tearing down the REPL.

README documents /render and updates the Status section to call out the load → set meta → render
  flow.

Coverage: src/draft.py and src/repl.py both 100%; total 97%. 124 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(draft): mark imageless pages as text-only per select-page-layout rule 1

to_book was constructing every Page without an explicit layout, so imageless pages silently picked
  up the schema default 'image-top'. CLAUDE.md's select-page-layout skill is explicit that imageless
  pages must render as 'text-only' — otherwise the page has an empty image slot and the stored
  book.json lies about its own layout.

Apply only rule 1 of the decision tree here. The rest of the selector (aspect-ratio branching,
  fit-check, rhythm) lands with src/layout_selector.py under p5-01 per the skill's integration hook.

Addresses review feedback on #9.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Interactive shell skeleton with slash-command dispatch
  ([#3](https://github.com/mfozmen/littlepress-ai/pull/3),
  [`e1f05c7`](https://github.com/mfozmen/littlepress-ai/commit/e1f05c79b6fb86d176c95cedd7e2f1b79abaf905))

* feat(repl): add interactive shell skeleton with slash-command dispatch

Wire the CLI entry point to a Rich-backed Repl that reads lines, routes slash commands through a
  dispatch table, and echoes non-slash input as a placeholder until the agent loop lands (p2-01).
  First commands: /help lists everything registered, /exit returns zero. EOF exits cleanly, unknown
  commands report an error without tearing the session down.

Repl takes injected read_line and console collaborators so the loop is unit-testable without real
  stdin — tests script a list of lines and inspect a Rich Console wired to a StringIO buffer. Add
  rich as a core dependency.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* docs: reflect interactive REPL in README

Reframe the How-it-works section around the interactive CLI, list what's shipped vs. in-flight under
  Status, and document the first slash commands (/help, /exit). Keep the direct renderer path for
  users who hand-author book.json.

* docs: require README updates alongside user-facing PRs

Codify the rule the maintainer set on 2026-04-13 after noticing the REPL skeleton PR shipped without
  a README entry. User-visible changes (commands, flags, install paths, deps, slash commands) must
  update README.md in the same PR, not a follow-up.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Persist provider choice across launches via .book-gen/session.json
  ([#5](https://github.com/mfozmen/littlepress-ai/pull/5),
  [`4470795`](https://github.com/mfozmen/littlepress-ai/commit/4470795b3e03839b4a5a41445d80cdbdedf16a2e))

Introduce src/session.py with a small Session dataclass and atomic save/load helpers. The REPL
  accepts an optional session_root; when set, it writes the selected provider to
  .book-gen/session.json on activation and restores it on the next launch so the user isn't asked
  which model to use every single time.

API keys are NOT persisted in this slice — users still enter them each launch. Keyring integration
  lands in a follow-up PR, per docs/p1-02-session-state.md.

Resilience: - Missing, corrupt, or non-object session.json silently falls through to the first-run
  picker instead of crashing. - Unknown saved provider names also fall through. - EOF on the resume
  key prompt exits cleanly without half-activating. - Atomic write via tempfile + os.replace; if
  serialization fails, the tmp file is cleaned up and the exception propagates.

Wire the CLI to pass session_root=Path.cwd(), gitignore .book-gen/, and update README's Status entry
  to mention the persistence.

Full coverage on src/repl.py and src/session.py; 74 tests total.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Provider picker with masked API-key entry and /model command
  ([#4](https://github.com/mfozmen/littlepress-ai/pull/4),
  [`b7126cd`](https://github.com/mfozmen/littlepress-ai/commit/b7126cda0f88ecffa6d2dd0e394d495a4bf18dd3))

* feat(repl): provider picker with masked API-key entry and /model command

First launch now asks which LLM provider to use (Claude, GPT, Gemini, Ollama, or offline). Providers
  that need an API key prompt the user through a separate read_secret collaborator so the key never
  reaches the rendered console — CLI wires it to getpass; tests wire a scripted reader and assert
  the key is absent from the buffer.

/model re-runs the picker mid-session. Aborting the switch (EOF on stdin or on the key prompt)
  leaves the previous provider intact.

Provider specs live in src/providers/llm.py as frozen dataclasses — just metadata for now. Real
  chat() wiring and SDK imports land with the agent loop (p2-01) in a follow-up PR.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* test(repl): cover provider-picker edge cases and cli.py getpass wiring

Fill in the branches coverage flagged missing plus a set of edge cases the picker could hit in the
  wild:

- EOF at the API-key prompt (first-run and /model) — exits / keeps previous provider without
  activating the half-picked spec. - Non-positive, zero, and float inputs at the number prompt
  reprompt. - Blank lines at the number prompt are ignored. - API key has surrounding whitespace
  stripped. - /model into a key-less provider clears any previous key. - /help, /exit, /model
  tolerate trailing arguments. - Unicode (emoji, Turkish) in non-slash input survives the echo. -
  ProviderSpec instances are frozen (the picker relies on SPECS being an immutable catalogue).

Also add a CLI-level regression guard that Anthropic's API key is read through getpass, not through
  builtins.input — to prevent a future rewire from echoing the key to the terminal.

src/repl.py reaches 100% coverage; total coverage 95%.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Validate API keys against the provider before accepting them
  ([#6](https://github.com/mfozmen/littlepress-ai/pull/6),
  [`4cc8965`](https://github.com/mfozmen/littlepress-ai/commit/4cc89657157402d05f75a75e447ab9635d21f5f9))

* feat(repl): validate API keys against the provider before accepting them

Add src/providers/validator.py with validate_key(spec, api_key), which raises KeyValidationError
  when the key won't authenticate. First implementation: Anthropic — sends a tiny ping via the SDK
  and surfaces

AuthenticationError as a rejection. SDK imports are lazy so users who stay offline or on Ollama
  don't need to install anything extra; picking Anthropic without the SDK installed produces a clear
  "pip install 'child-book-generator[anthropic]'" message.

REPL takes an optional validate callable and re-prompts for a key whenever the validator rejects it.
  Aborting (EOF) after a rejection returns to the previous provider on /model, and to a no-provider
  exit on first-run. Tests stub the validator so the REPL flow is covered without a network
  dependency; separate unit tests exercise the real validator against a module-shaped fake of the
  Anthropic SDK.

Add the 'anthropic' optional extra in pyproject.toml and point README at it for users who want live
  key validation.

Coverage: src/providers/validator.py, src/repl.py, src/session.py,

src/providers/llm.py all at 100%; 86 tests total.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(validator): separate missing-SDK from bad-key and bound the ping

Addresses four review findings on #6:

1. Missing SDK now raises ProviderUnavailable (a new exception sibling to KeyValidationError), which
  the REPL handles by aborting the current picker run instead of looping the key prompt forever. 2.
  The Anthropic ping runs with a 5-second timeout so a flaky network can't hang the REPL at the key
  prompt (SDK default is ~600 s). 3. Move the validation model id onto ProviderSpec.validation_model
  so model retirements are a one-line change in src/providers/llm.py, not a hunt inside the
  validator. 4. Tighten the comment around AuthenticationError — it's raised on 401 response, not
  "before the request finishes".

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **skills**: Add select-page-layout guardrail for pixel-perfect page composition
  ([`c0062fe`](https://github.com/mfozmen/littlepress-ai/commit/c0062fee0436491fb2f72b2afb9f5e76c6f10e5a))

Project-level skill codifying how a page in a child's picture book should be laid out. Works
  alongside preserve-child-voice: layout decisions never touch the child's words, only where those
  words sit on the page.

Scope: - Reads text length, image aspect ratio, neighbour-page rhythm, and A5 geometry from
  src/config.py. - Maps inputs to one of today's four layouts (image-top, image-bottom, image-full,
  text-only) via an explicit decision tree. - Mandates a pixel-level fit-check before committing a
  layout: compute wrapped line count against the target slot, fall back to a taller slot if it
  overflows, never shrink below 12 pt. - Rhythm rule: no 3-in-a-row of the same layout when a
  compatible alternative exists, but fit always wins over rhythm. - Documents the goal state
  (parametric layout engine) so the skill keeps its value once src/pages.py grows beyond four fixed
  layouts. - Reserves src/layout_selector.py::suggest_layout() as the code hook that must mirror the
  skill's rules verbatim when built.

CLAUDE.md adds it to the project skill list.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Testing

- Characterize existing behavior across schema, imposition, build, pdf-ingest
  ([`3031643`](https://github.com/mfozmen/littlepress-ai/commit/303164364267f80d4b6648f28ba20fcde466c1f3))

Grows the suite from 2 to 18 tests (coverage 92%):

- schema: missing/empty title, default author/cover/back_cover, default layout "image-top", invalid
  layout rejection, missing image file - pdf_ingest: empty PDF -> [], preserve-child-voice verbatim
  contract (typos and quirky spellings pass through untouched) - imposition: _booklet_order for
  4/3/8 pages (known saddle-stitch orders) - build: _slugify covers Turkish chars, spaces,
  symbol-only fallback; main() end-to-end against examples/book.json, missing-file error path, and
  --impose booklet generation

Also ignore test/coverage artifacts (.coverage, .pytest_cache/, coverage.xml, htmlcov/).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
