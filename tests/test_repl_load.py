import io

from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from rich.console import Console

from src.providers.llm import find
from src.repl import Repl


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _make(tmp_path, lines):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(lines),
        console=console,
        provider=find("none"),
        session_root=tmp_path,
    )
    return repl, buf


def _write_pdf(tmp_path, pages):
    path = tmp_path / "draft.pdf"
    c = canvas.Canvas(str(path), pagesize=A5)
    for i, page in enumerate(pages):
        if page.get("image"):
            src = tmp_path / f"_src_{i}.png"
            Image.new("RGB", (80, 60), page["image"]).save(src)
            c.drawImage(ImageReader(str(src)), 50, 200, width=200, height=150)
        if page.get("text"):
            c.setFont("Helvetica", 14)
            c.drawString(50, 400, page["text"])
        c.showPage()
    c.save()
    return path


def test_load_without_argument_prints_usage(tmp_path):
    repl, buf = _make(tmp_path, ["/load", "/exit"])
    repl.run()

    assert "usage" in buf.getvalue().lower()
    assert repl.draft is None


def test_load_missing_file_reports_error_and_leaves_state(tmp_path):
    repl, buf = _make(tmp_path, ["/load does/not/exist.pdf", "/exit"])
    repl.run()

    assert "not found" in buf.getvalue().lower()
    assert repl.draft is None


def test_load_valid_pdf_populates_draft(tmp_path):
    pdf = _write_pdf(
        tmp_path,
        [
            {"text": "once upon a time", "image": (255, 0, 0)},
            {"text": "the owl flew home"},
        ],
    )

    repl, buf = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    assert repl.draft is not None
    assert len(repl.draft.pages) == 2
    assert "2 pages" in buf.getvalue()
    # Only the first page had a drawing.
    assert "1 with" in buf.getvalue() or "1 page with" in buf.getvalue()


def test_load_writes_images_under_session_root(tmp_path):
    pdf = _write_pdf(tmp_path, [{"image": (0, 255, 0)}])

    repl, _ = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    # Images go under .book-gen/images/ so they're gitignored with the
    # rest of session state.
    images_dir = tmp_path / ".book-gen" / "images"
    assert images_dir.is_dir()
    assert list(images_dir.iterdir()), "expected at least one extracted image"


def test_load_on_non_pdf_reports_error(tmp_path):
    bad = tmp_path / "not-a-pdf.txt"
    bad.write_text("hello")

    repl, buf = _make(tmp_path, [f"/load {bad}", "/exit"])
    repl.run()

    assert "could not read" in buf.getvalue().lower()
    assert repl.draft is None


def test_load_mirrors_the_pdf_into_book_gen_input(tmp_path):
    """``/load`` must mirror the source PDF into ``.book-gen/input/``
    so the session's state keys off a path we own — the user can delete
    the original later without losing memory."""
    external_dir = tmp_path / "Desktop"
    external_dir.mkdir()
    pdf = _write_pdf(external_dir, [{"text": "hi"}])

    repl, _ = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    input_dir = tmp_path / ".book-gen" / "input"
    assert input_dir.is_dir()
    collected = list(input_dir.glob("*.pdf"))
    assert len(collected) == 1
    assert collected[0].read_bytes() == pdf.read_bytes()
    # The draft points at the in-repo copy, not the original path.
    assert repl.draft.source_pdf == collected[0]


def test_loading_twice_replaces_previous_draft(tmp_path):
    pdf_a = _write_pdf(tmp_path / "a" if (tmp_path / "a").mkdir() or True else tmp_path, [{"text": "first"}])
    pdf_b_dir = tmp_path / "b"
    pdf_b_dir.mkdir()
    pdf_b = _write_pdf(pdf_b_dir, [{"text": "second"}, {"text": "third"}])

    repl, _ = _make(tmp_path, [f"/load {pdf_a}", f"/load {pdf_b}", "/exit"])
    repl.run()

    assert repl.draft is not None
    assert len(repl.draft.pages) == 2
    # /load collects the PDF into .book-gen/input/; source_pdf is the
    # in-repo copy, not the original. We just check the content lines
    # up (2 pages → pdf_b's story).
    assert repl.draft.source_pdf.is_file()
    assert repl.draft.source_pdf.read_bytes() == pdf_b.read_bytes()


def test_load_kicks_the_agent_off_when_a_real_provider_is_active(tmp_path):
    """Dragging a PDF (or typing /load) mid-session must trigger the
    same agent greeting the CLI uses when it's launched with a PDF
    arg. Otherwise the user sees "Loaded N pages" and... silence.
    The agent needs a nudge to call read_draft and start asking
    questions."""
    import io

    from rich.console import Console

    from src.agent import AgentResponse
    from src.providers.llm import find

    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    class _StubLLM:
        def __init__(self):
            self.calls: list = []

        def turn(self, messages, _tools):
            self.calls.append(list(messages))
            return AgentResponse(
                content=[{"type": "text", "text": "Hi! I see 1 page."}],
                stop_reason="end_turn",
            )

    llm = _StubLLM()
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted([f"/load {pdf}", "/exit"]),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.run()

    assert repl.draft is not None
    # The agent was invoked after the load (once, with the greeting).
    assert len(llm.calls) == 1
    # The greeting the agent sees mentions reading the draft.
    first_user_message = llm.calls[0][0]
    assert first_user_message["role"] == "user"
    assert "read_draft" in first_user_message["content"].lower()
    # And the agent's reply surfaced to the user.
    assert "I see 1 page" in buf.getvalue()


def test_load_is_quiet_on_offline_provider(tmp_path):
    """Offline (NullProvider) — /load should NOT try to talk to the
    agent. Just load and stay silent."""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, buf = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    assert repl.draft is not None
    # No "agent error" / no greeting attempt.
    assert "agent error" not in buf.getvalue().lower()


def test_load_expands_tilde_in_path(tmp_path, monkeypatch):
    # Make ~ resolve to a directory we control so the test doesn't touch the
    # developer's real home directory.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows

    pdf = _write_pdf(fake_home, [{"text": "hello from home"}])
    assert pdf.parent == fake_home

    repl, _ = _make(tmp_path, [f"/load ~/{pdf.name}", "/exit"])
    repl.run()

    assert repl.draft is not None
    assert len(repl.draft.pages) == 1


def test_load_strips_surrounding_double_quotes(tmp_path):
    """Users copy-pasting Windows-style paths with spaces often wrap
    them in double quotes (PowerShell habit). The REPL isn't a shell,
    so the quotes arrive as literal characters — `/load` must strip
    them so Path() doesn't look for a file whose name starts with ""."""
    spaced = tmp_path / "oglum kitabi.pdf"
    pdf = _write_pdf(
        spaced.parent if spaced.parent.exists() else tmp_path,
        [{"text": "hi"}],
    )
    # Rename the produced file to the intended name with spaces.
    spaced.unlink(missing_ok=True)
    pdf.rename(spaced)

    repl, buf = _make(tmp_path, [f'/load "{spaced}"', "/exit"])
    repl.run()

    assert repl.draft is not None
    assert "not found" not in buf.getvalue().lower()


def test_load_strips_surrounding_single_quotes(tmp_path):
    """Same for 'single quotes' — common from Linux / macOS pastes."""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, buf = _make(tmp_path, [f"/load '{pdf}'", "/exit"])
    repl.run()

    assert repl.draft is not None
    assert "not found" not in buf.getvalue().lower()


def test_load_quoted_path_with_spaces(tmp_path):
    spaced_dir = tmp_path / "my drafts"
    spaced_dir.mkdir()
    pdf = _write_pdf(spaced_dir, [{"text": "hi"}])

    # The arg is everything after `/load ` — no shell quoting required.
    repl, _ = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    assert repl.draft is not None
    # /load mirrors the PDF into .book-gen/input/ — the in-repo copy
    # has the same bytes but a hashed filename, not the original path.
    assert repl.draft.source_pdf.is_file()
    assert repl.draft.source_pdf.read_bytes() == pdf.read_bytes()


def test_load_pdf_auto_ingests_image_only_pages(tmp_path):
    """End-to-end: loading an image-only PDF via /load triggers
    deterministic ingestion (via ``ingest_image_only_pages``) before
    any agent turn — the agent sees a draft that's already been OCR'd.

    The scripted LLM's ``chat`` method plays the vision-OCR role;
    ``turn`` must never be called during ingestion (it would mean the
    agent started before ingestion finished).
    """
    import io

    from rich.console import Console

    from src.providers.llm import find

    # Build a 2-page image-only PDF (no text layer, only embedded images).
    pdf = tmp_path / "draft.pdf"
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    c = rl_canvas.Canvas(str(pdf), pagesize=A5)
    for i in range(2):
        img_path = tmp_path / f"_src_{i}.png"
        Image.new("RGB", (120, 160), (200, 200, 200)).save(img_path)
        c.drawImage(ImageReader(str(img_path)), 50, 200, width=300, height=400)
        c.showPage()
    c.save()

    class _LLM:
        name = "anthropic"

        def __init__(self):
            self.chat_calls = 0
            self.turn_calls = 0
            self.chat_calls_at_first_turn: int | None = None

        def chat(self, *_a, **_kw):
            self.chat_calls += 1
            return f"<TEXT>\nPage {self.chat_calls} transcribed"

        def turn(self, *_a, **_kw):
            # Record how many chat (OCR) calls had already happened
            # the first time the agent's tool-use loop fires.  Ingestion
            # must be complete (chat_calls == 2) before this point.
            if self.chat_calls_at_first_turn is None:
                self.chat_calls_at_first_turn = self.chat_calls
            self.turn_calls += 1
            if self.chat_calls == 0:
                raise AssertionError(
                    "agent should not have started yet — ingestion must "
                    "finish before the first agent turn"
                )
            from src.agent import AgentResponse

            return AgentResponse(
                content=[{"type": "text", "text": "draft looks good"}],
                stop_reason="end_turn",
            )

    llm = _LLM()
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted([f"/load {pdf}", "/exit"]),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.run()

    assert repl.draft is not None, "draft should be loaded"
    assert llm.chat_calls == 2, (
        f"expected 2 chat calls (one per image-only page), got {llm.chat_calls}"
    )
    # The agent may greet the user after ingestion, but it must not
    # start its tool-use loop BEFORE ingestion completes.  If
    # chat_calls_at_first_turn is None the agent never turned (also
    # fine); if it is set it must equal 2 (all pages already OCR'd).
    if llm.chat_calls_at_first_turn is not None:
        assert llm.chat_calls_at_first_turn == 2, (
            "agent turn fired before ingestion completed: "
            f"chat_calls at first turn = {llm.chat_calls_at_first_turn}, "
            "expected 2"
        )
    # Both pages should have text populated by the ingestion pass.
    for i, page in enumerate(repl.draft.pages):
        assert page.text.strip(), (
            f"page {i + 1} text is empty — ingestion did not populate it"
        )
