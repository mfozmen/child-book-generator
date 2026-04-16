"""Unit tests for the LLMProvider implementations in src/providers/llm.py."""

import sys
import types

import pytest

from src.providers.llm import (
    AnthropicProvider,
    GoogleProvider,
    LLMProvider,
    NullProvider,
    OpenAIProvider,
    create_provider,
    find,
)


def _fake_anthropic_module(reply_text="hello from claude"):
    class Messages:
        def __init__(self):
            self.last_kwargs: dict = {}

        def create(self, **kwargs):
            self.last_kwargs = kwargs
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text=reply_text)]
            )

    class Client:
        last_client: "Client | None" = None

        def __init__(self, *, api_key, timeout=None):
            self.api_key = api_key
            self.timeout = timeout
            self.messages = Messages()
            Client.last_client = self

    module = types.ModuleType("anthropic")
    module.Anthropic = Client
    return module


def test_null_provider_chat_raises():
    with pytest.raises(NotImplementedError):
        NullProvider().chat([{"role": "user", "content": "hi"}])


def test_anthropic_provider_returns_reply_text(monkeypatch):
    fake = _fake_anthropic_module(reply_text="the dragon is fine")
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    provider = AnthropicProvider(api_key="sk-test")
    reply = provider.chat([{"role": "user", "content": "how is the dragon?"}])

    assert reply == "the dragon is fine"


def test_anthropic_provider_forwards_messages(monkeypatch):
    fake = _fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    provider = AnthropicProvider(api_key="sk-test")
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "again"},
    ]
    provider.chat(msgs)

    assert fake.Anthropic.last_client.messages.last_kwargs["messages"] == msgs


def test_anthropic_provider_passes_bounded_timeout_to_sdk(monkeypatch):
    """Regression guard: the SDK default timeout (~600 s) would freeze
    the REPL on a flaky network. The chat client must be constructed with
    a short, finite timeout — see PR #6 for the validator's equivalent."""
    fake = _fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    AnthropicProvider(api_key="sk").chat([{"role": "user", "content": "hi"}])

    timeout = fake.Anthropic.last_client.api_key  # sanity — client was built
    assert timeout == "sk"
    # The keyword actually forwarded to Anthropic():
    last = fake.Anthropic.last_client
    # Stored on the fake in the last_kwargs of the builder — we need to
    # inspect the constructor arg directly.
    # Rebuild assertion: the fake client stores timeout alongside api_key.
    assert hasattr(last, "timeout")
    assert last.timeout is not None and 0 < last.timeout <= 300


def test_anthropic_provider_without_sdk_raises_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)

    provider = AnthropicProvider(api_key="sk-test")
    with pytest.raises(ImportError):
        provider.chat([{"role": "user", "content": "hi"}])


def test_create_provider_returns_null_for_offline_spec():
    spec = find("none")
    provider = create_provider(spec, api_key=None)
    assert isinstance(provider, NullProvider)


def test_create_provider_returns_anthropic_with_key():
    spec = find("anthropic")
    provider = create_provider(spec, api_key="sk-test")
    assert isinstance(provider, AnthropicProvider)


def test_create_provider_falls_back_to_null_for_unwired_providers():
    # Ollama hasn't shipped chat() yet. The factory hands back a
    # NullProvider so the REPL keeps working with the "(no model
    # selected)" placeholder until it lands.
    spec = find("ollama")
    provider = create_provider(spec, api_key="x")
    assert isinstance(provider, NullProvider)


def test_create_provider_returns_google_with_key():
    spec = find("google")
    provider = create_provider(spec, api_key="AIzaFake")
    assert isinstance(provider, GoogleProvider)


def test_create_provider_returns_openai_with_key():
    spec = find("openai")
    provider = create_provider(spec, api_key="sk-test")
    assert isinstance(provider, OpenAIProvider)


def test_llm_provider_is_usable_as_type_hint():
    # Both implementations satisfy the protocol — a sanity check that
    # future code can type-hint LLMProvider without importing either
    # implementation.
    p: LLMProvider = NullProvider()
    q: LLMProvider = AnthropicProvider(api_key="x")
    assert p is not None and q is not None


# --- turn() (tool-use) ----------------------------------------------------


def _fake_anthropic_with_turn(response_blocks, stop_reason="end_turn"):
    """Fake SDK whose messages.create returns the given content blocks."""
    class Block:
        """Small shim that supports both attribute and dict access."""

        def __init__(self, data):
            self._data = data

        def __getattr__(self, name):
            if name in self._data:
                return self._data[name]
            raise AttributeError(name)

        def model_dump(self):
            return dict(self._data)

    class Messages:
        def __init__(self):
            self.last_kwargs: dict = {}

        def create(self, **kwargs):
            self.last_kwargs = kwargs
            return types.SimpleNamespace(
                content=[Block(b) for b in response_blocks],
                stop_reason=stop_reason,
            )

    class Client:
        last_client = None

        def __init__(self, *, api_key, timeout=None):
            self.api_key = api_key
            self.timeout = timeout
            self.messages = Messages()
            Client.last_client = self

    module = types.ModuleType("anthropic")
    module.Anthropic = Client
    return module


def test_null_provider_turn_raises():
    from src.agent import Tool

    tool = Tool(
        name="noop",
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=lambda _i: "ok",
    )
    with pytest.raises(NotImplementedError):
        NullProvider().turn([], [tool])


def test_anthropic_provider_turn_returns_text_response(monkeypatch):
    fake = _fake_anthropic_with_turn(
        [{"type": "text", "text": "hi there"}],
        stop_reason="end_turn",
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    response = AnthropicProvider(api_key="sk").turn(
        [{"role": "user", "content": "hello"}], tools=[]
    )

    assert response.stop_reason == "end_turn"
    assert response.content == [{"type": "text", "text": "hi there"}]


def test_anthropic_provider_turn_returns_tool_use_response(monkeypatch):
    fake = _fake_anthropic_with_turn(
        [
            {"type": "text", "text": "let me check"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "read_draft",
                "input": {},
            },
        ],
        stop_reason="tool_use",
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    response = AnthropicProvider(api_key="sk").turn(
        [{"role": "user", "content": "what's in the draft?"}],
        tools=[],
    )

    assert response.stop_reason == "tool_use"
    names = [b.get("name") for b in response.content if b.get("type") == "tool_use"]
    assert names == ["read_draft"]


def test_anthropic_provider_turn_forwards_tool_schemas_to_sdk(monkeypatch):
    from src.agent import Tool

    fake = _fake_anthropic_with_turn([{"type": "text", "text": "ok"}])
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    tool = Tool(
        name="read_draft",
        description="Read the loaded PDF draft",
        input_schema={"type": "object", "properties": {}},
        handler=lambda _i: "",
    )
    AnthropicProvider(api_key="sk").turn(
        [{"role": "user", "content": "hi"}],
        tools=[tool],
    )

    last = fake.Anthropic.last_client.messages.last_kwargs
    assert "tools" in last
    assert last["tools"] == [
        {
            "name": "read_draft",
            "description": "Read the loaded PDF draft",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]


def test_anthropic_provider_turn_uses_bounded_timeout(monkeypatch):
    fake = _fake_anthropic_with_turn([{"type": "text", "text": "ok"}])
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    AnthropicProvider(api_key="sk").turn(
        [{"role": "user", "content": "hi"}],
        tools=[],
    )
    timeout = fake.Anthropic.last_client.timeout
    assert timeout is not None and 0 < timeout <= 300


def test_block_to_dict_handles_blocks_without_model_dump(monkeypatch):
    """Older SDK versions return attribute-only objects (no model_dump).
    The converter must still produce correct dicts for text and tool_use."""
    from src.providers.llm import _block_to_dict

    class PlainText:
        type = "text"
        text = "hi"

    class PlainToolUse:
        type = "tool_use"
        id = "t1"
        name = "read_draft"
        input = {"k": "v"}

    class Mystery:
        type = "unknown_block_type"

    assert _block_to_dict(PlainText()) == {"type": "text", "text": "hi"}
    assert _block_to_dict(PlainToolUse()) == {
        "type": "tool_use",
        "id": "t1",
        "name": "read_draft",
        "input": {"k": "v"},
    }
    # Unknown blocks at least carry their type — the agent can ignore them.
    assert _block_to_dict(Mystery()) == {"type": "unknown_block_type"}


# --- GoogleProvider (Gemini) -------------------------------------------


def _install_fake_google_genai(
    monkeypatch,
    *,
    response_parts=None,
    finish_reason="STOP",
):
    """Install a minimal fake of ``google.genai`` so GoogleProvider
    can be exercised without network access.

    ``response_parts`` — list of Part-like objects to hand back from
    ``generate_content``. If None, the fake returns no candidates.
    ``finish_reason`` — the stop signal on the first candidate.
    """

    class Content:
        def __init__(self, role=None, parts=None):
            self.role = role
            self.parts = list(parts or [])

    class FunctionResponse:
        def __init__(self, name=None, response=None, id=None):
            self.name = name
            self.response = response
            self.id = id

    class Part:
        def __init__(
            self, text=None, function_call=None, function_response=None
        ):
            self.text = text
            self.function_call = function_call
            self.function_response = function_response

        @classmethod
        def from_text(cls, text):
            return cls(text=text)

    class FunctionCall:
        def __init__(self, name, args=None, id=None):
            self.name = name
            self.args = args or {}
            self.id = id

    class FunctionDeclaration:
        def __init__(self, name, description=None, parameters=None):
            self.name = name
            self.description = description
            self.parameters = parameters

    class Tool:
        def __init__(self, function_declarations=None):
            self.function_declarations = function_declarations or []

    class GenerateContentConfig:
        def __init__(self, tools=None):
            self.tools = tools or []

    class HttpOptions:
        def __init__(self, timeout=None, **kw):
            self.timeout = timeout
            self.kwargs = kw

    types_mod = types.ModuleType("google.genai.types")
    types_mod.Content = Content
    types_mod.Part = Part
    types_mod.FunctionCall = FunctionCall
    types_mod.FunctionResponse = FunctionResponse
    types_mod.FunctionDeclaration = FunctionDeclaration
    types_mod.Tool = Tool
    types_mod.GenerateContentConfig = GenerateContentConfig
    types_mod.HttpOptions = HttpOptions

    class Candidate:
        def __init__(self, content, finish_reason="STOP"):
            self.content = content
            self.finish_reason = finish_reason

    class Response:
        def __init__(self):
            if response_parts is not None:
                self.candidates = [
                    Candidate(
                        Content(role="model", parts=response_parts),
                        finish_reason=finish_reason,
                    )
                ]
            else:
                self.candidates = []

        @property
        def text(self):
            # Real SDK raises ValueError when there are no text parts
            # (e.g. SAFETY-blocked). Mirror that so the provider has
            # to defensively iterate parts itself.
            if not self.candidates:
                raise ValueError("No candidates available.")
            parts = getattr(self.candidates[0].content, "parts", None) or []
            texts = [getattr(p, "text", None) for p in parts]
            if not any(texts):
                raise ValueError("No text parts in response.")
            return "".join(t or "" for t in texts)

    class Models:
        def __init__(self):
            self.last_kwargs: dict = {}

        def generate_content(self, **kwargs):
            self.last_kwargs = kwargs
            return Response()

    class Client:
        last_client: "Client | None" = None

        def __init__(self, *, api_key, http_options=None, **kw):
            self.api_key = api_key
            self.http_options = http_options
            self.kwargs = kw
            self.models = Models()
            Client.last_client = self

    genai_mod = types.ModuleType("google.genai")
    genai_mod.Client = Client
    genai_mod.types = types_mod

    google_mod = types.ModuleType("google")
    google_mod.genai = genai_mod

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)
    return genai_mod, types_mod


def test_google_provider_chat_returns_reply_text(monkeypatch):
    _, types_mod = _install_fake_google_genai(monkeypatch)
    text_part = types_mod.Part.from_text(text="hello from gemini")
    _install_fake_google_genai(monkeypatch, response_parts=[text_part])

    reply = GoogleProvider(api_key="AIzaFake").chat(
        [{"role": "user", "content": "hi"}]
    )

    assert reply == "hello from gemini"


def test_google_provider_chat_handles_safety_blocked_response(monkeypatch):
    """Real SDK's ``response.text`` property *raises* ``ValueError`` when
    there are no text parts (e.g. SAFETY finish). ``chat`` must compose
    the reply from ``candidates[0].content.parts`` so a blocked prompt
    returns an empty string instead of a traceback."""
    _install_fake_google_genai(
        monkeypatch, response_parts=[], finish_reason="SAFETY"
    )

    # Must not raise.
    reply = GoogleProvider(api_key="k").chat(
        [{"role": "user", "content": "bad prompt"}]
    )
    assert reply == ""


def test_google_provider_chat_passes_bounded_timeout_via_http_options(monkeypatch):
    """The Gen AI SDK's default timeout is ~600 s, which would freeze
    the REPL on a flaky network — see PR #12 for the Anthropic
    equivalent. The client must be constructed with
    ``http_options=HttpOptions(timeout=<ms>)`` so the ping is bounded."""
    _, types_mod = _install_fake_google_genai(monkeypatch)
    text_part = types_mod.Part.from_text(text="ok")
    genai_mod, _ = _install_fake_google_genai(
        monkeypatch, response_parts=[text_part]
    )

    GoogleProvider(api_key="k").chat([{"role": "user", "content": "hi"}])

    http_options = genai_mod.Client.last_client.http_options
    assert http_options is not None
    # Timeout is in milliseconds at the SDK level; bound to something
    # short enough that a hung network won't freeze the REPL for
    # minutes but long enough to cover legitimate slow replies.
    assert 0 < http_options.timeout <= 300_000


def test_google_provider_chat_translates_user_messages_to_gemini_contents(monkeypatch):
    _, types_mod = _install_fake_google_genai(monkeypatch)
    text_part = types_mod.Part.from_text(text="ok")
    genai_mod, _ = _install_fake_google_genai(
        monkeypatch, response_parts=[text_part]
    )

    GoogleProvider(api_key="k").chat(
        [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
    )

    sent = genai_mod.Client.last_client.models.last_kwargs
    contents = sent["contents"]
    # Three contents with alternating roles (user/model/user) and text parts.
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[0].parts[0].text == "first"
    assert contents[1].parts[0].text == "reply"
    assert contents[2].parts[0].text == "second"


def test_google_provider_without_sdk_raises_import_error(monkeypatch):
    # Simulate the SDK being unavailable.
    monkeypatch.setitem(sys.modules, "google", None)
    monkeypatch.setitem(sys.modules, "google.genai", None)

    with pytest.raises(ImportError):
        GoogleProvider(api_key="k").chat([{"role": "user", "content": "hi"}])


def test_google_provider_turn_returns_text_response(monkeypatch):
    genai_mod, types_mod = _install_fake_google_genai(
        monkeypatch,
        response_parts=[types.ModuleType("placeholder")],  # replaced below
    )
    # Build a real text Part using the fake types module.
    text_part = types_mod.Part.from_text(text="hello there")
    # Replace the response_parts by reinstalling with the right Part.
    _install_fake_google_genai(monkeypatch, response_parts=[text_part])

    response = GoogleProvider(api_key="k").turn(
        [{"role": "user", "content": "hi"}], tools=[]
    )

    assert response.stop_reason == "end_turn"
    assert response.content == [{"type": "text", "text": "hello there"}]


def test_google_provider_turn_returns_tool_use_when_model_calls_a_function(monkeypatch):
    _, types_mod = _install_fake_google_genai(monkeypatch)
    parts = [
        types_mod.Part.from_text(text="let me check"),
        types_mod.Part(
            function_call=types_mod.FunctionCall(
                name="read_draft", args={}
            ),
        ),
    ]
    _install_fake_google_genai(monkeypatch, response_parts=parts)

    response = GoogleProvider(api_key="k").turn(
        [{"role": "user", "content": "what's in the draft?"}], tools=[]
    )

    assert response.stop_reason == "tool_use"
    kinds = [b["type"] for b in response.content]
    assert kinds == ["text", "tool_use"]
    tool_block = response.content[1]
    assert tool_block["name"] == "read_draft"
    # An id is synthesised so the agent can match tool_use → tool_result
    # even when Gemini didn't return one.
    assert tool_block["id"]
    assert tool_block["input"] == {}


def test_google_provider_turn_forwards_tool_schemas_to_sdk(monkeypatch):
    from src.agent import Tool as AgentTool

    genai_mod, types_mod = _install_fake_google_genai(
        monkeypatch,
        response_parts=[types.ModuleType("placeholder")],
    )
    text_part = types_mod.Part.from_text(text="ok")
    _install_fake_google_genai(monkeypatch, response_parts=[text_part])
    # Re-resolve — the above reinstalls the module, refetch types.
    import importlib
    genai_mod = sys.modules["google.genai"]
    types_mod = sys.modules["google.genai.types"]

    tool = AgentTool(
        name="read_draft",
        description="Read the loaded PDF draft",
        input_schema={"type": "object", "properties": {}},
        handler=lambda _i: "",
    )
    GoogleProvider(api_key="k").turn(
        [{"role": "user", "content": "hi"}], tools=[tool]
    )

    sent = genai_mod.Client.last_client.models.last_kwargs
    config = sent["config"]
    assert len(config.tools) == 1
    fn_decls = config.tools[0].function_declarations
    assert [fd.name for fd in fn_decls] == ["read_draft"]
    assert fn_decls[0].description == "Read the loaded PDF draft"
    assert fn_decls[0].parameters == {"type": "object", "properties": {}}


def test_google_provider_turn_translates_tool_result_messages_back_to_gemini(monkeypatch):
    """A full turn — the agent sends back a tool_result from a prior
    tool_use. Translation must surface it as a ``function_response``
    Part on a ``tool``-role Content so Gemini can continue the
    conversation. The function_response carries both the ``name``
    (looked up from the prior tool_use) AND the synthesised ``id``
    so parallel calls to the same tool don't cross-wire."""
    _, types_mod = _install_fake_google_genai(monkeypatch)
    text_part = types_mod.Part.from_text(text="done")
    genai_mod, types_mod = _install_fake_google_genai(
        monkeypatch, response_parts=[text_part]
    )

    messages = [
        {"role": "user", "content": "read the draft"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "sure"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "read_draft",
                    "input": {},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "Title: Book\n1 pages.",
                }
            ],
        },
    ]

    GoogleProvider(api_key="k").turn(messages, tools=[])

    sent = genai_mod.Client.last_client.models.last_kwargs
    contents = sent["contents"]
    roles = [c.role for c in contents]
    # user → model → tool
    assert roles == ["user", "model", "tool"]
    # The function_response part carries the tool name + id.
    fr_part = contents[2].parts[0]
    assert fr_part.function_response.name == "read_draft"
    assert fr_part.function_response.id == "toolu_1"
    assert fr_part.function_response.response == {
        "result": "Title: Book\n1 pages."
    }


def test_google_provider_turn_preserves_id_for_parallel_same_name_tool_calls(monkeypatch):
    """If Gemini emits two ``function_call`` parts with the same name
    in one turn, the agent's two ``tool_result`` blocks must translate
    back to ``function_response`` parts whose ``id`` fields match the
    synthesised tool_use ids — otherwise Gemini has no way to tell
    which call a given result belongs to."""
    _, types_mod = _install_fake_google_genai(monkeypatch)
    text_part = types_mod.Part.from_text(text="continuing")
    genai_mod, types_mod = _install_fake_google_genai(
        monkeypatch, response_parts=[text_part]
    )

    messages = [
        {"role": "user", "content": "check both pages"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_A",
                    "name": "read_draft",
                    "input": {},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_B",
                    "name": "read_draft",
                    "input": {},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_A", "content": "A"},
                {"type": "tool_result", "tool_use_id": "toolu_B", "content": "B"},
            ],
        },
    ]

    GoogleProvider(api_key="k").turn(messages, tools=[])

    contents = genai_mod.Client.last_client.models.last_kwargs["contents"]
    fr_parts = contents[2].parts
    # Two function_response parts, distinguishable by their id.
    ids = [p.function_response.id for p in fr_parts]
    assert ids == ["toolu_A", "toolu_B"]
    # Contents match the tool outputs one-to-one.
    assert [p.function_response.response["result"] for p in fr_parts] == ["A", "B"]


def test_google_provider_turn_handles_empty_response(monkeypatch):
    """A response with no candidates (e.g. safety blocking) must not
    crash — the turn returns end_turn with no content."""
    _install_fake_google_genai(monkeypatch, response_parts=None)

    response = GoogleProvider(api_key="k").turn(
        [{"role": "user", "content": "hi"}], tools=[]
    )

    assert response.stop_reason == "end_turn"
    assert response.content == []


def test_google_provider_turn_surfaces_non_stop_finish_reason_to_the_user(monkeypatch):
    """When Gemini ends a turn for a non-STOP reason (SAFETY, MAX_TOKENS,
    RECITATION) the agent otherwise sees silence. Surface a synthetic
    text block that names the reason so the REPL isn't mysteriously
    quiet — the user at least sees *why* the model stopped."""
    _install_fake_google_genai(
        monkeypatch, response_parts=[], finish_reason="SAFETY"
    )

    response = GoogleProvider(api_key="k").turn(
        [{"role": "user", "content": "bad prompt"}], tools=[]
    )

    # One synthetic text block naming the finish reason.
    assert response.stop_reason == "end_turn"
    text_blocks = [b for b in response.content if b.get("type") == "text"]
    assert text_blocks, "expected a surfaced warning text block"
    assert "SAFETY" in text_blocks[0]["text"]


def test_google_provider_turn_passes_bounded_timeout_via_http_options(monkeypatch):
    """``turn()`` gets the same timeout hedge as ``chat()`` — a hung
    tool-use round is exactly as bad as a hung chat round."""
    _, types_mod = _install_fake_google_genai(monkeypatch)
    text_part = types_mod.Part.from_text(text="ok")
    genai_mod, _ = _install_fake_google_genai(
        monkeypatch, response_parts=[text_part]
    )

    GoogleProvider(api_key="k").turn(
        [{"role": "user", "content": "hi"}], tools=[]
    )

    http_options = genai_mod.Client.last_client.http_options
    assert http_options is not None
    assert 0 < http_options.timeout <= 300_000


# --- OpenAIProvider ----------------------------------------------------


def _install_fake_openai(
    monkeypatch,
    *,
    reply_text=None,
    tool_calls=None,
    finish_reason="stop",
    raise_error=None,
):
    """Install a minimal fake of the ``openai`` module so OpenAIProvider
    can be exercised without network access.

    ``reply_text`` / ``tool_calls`` shape the completion response.
    ``finish_reason`` mirrors OpenAI's ``choices[0].finish_reason``.
    ``raise_error`` — "auth" | "bad_request" | "api" | None.
    """

    class AuthenticationError(Exception):
        pass

    class PermissionDeniedError(AuthenticationError):
        pass

    class BadRequestError(Exception):
        pass

    class APIError(Exception):
        pass

    class RateLimitError(APIError):
        pass

    class Function:
        def __init__(self, name, arguments):
            self.name = name
            self.arguments = arguments

    class ToolCall:
        def __init__(self, id, name, arguments):
            self.id = id
            self.type = "function"
            self.function = Function(name, arguments)

    class Message:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

    class Choice:
        def __init__(self, message, finish_reason):
            self.message = message
            self.finish_reason = finish_reason

    class Completion:
        def __init__(self, message, finish_reason):
            self.choices = [Choice(message, finish_reason)]

    class Completions:
        def __init__(self):
            self.last_kwargs: dict = {}

        def create(self, **kwargs):
            self.last_kwargs = kwargs
            if raise_error == "auth":
                raise AuthenticationError("Invalid API key")
            if raise_error == "permission":
                raise PermissionDeniedError("permission denied")
            if raise_error == "bad_request":
                raise BadRequestError("billing: insufficient quota")
            if raise_error == "rate":
                raise RateLimitError("rate limit exceeded")
            if raise_error == "api":
                raise APIError("upstream 500")
            tool_call_objs = [
                ToolCall(tc["id"], tc["name"], tc["arguments"])
                for tc in (tool_calls or [])
            ] or None
            return Completion(
                Message(content=reply_text, tool_calls=tool_call_objs),
                finish_reason,
            )

    class Chat:
        def __init__(self):
            self.completions = Completions()

    class Client:
        last_client: "Client | None" = None

        def __init__(self, *, api_key, timeout=None, **kw):
            self.api_key = api_key
            self.timeout = timeout
            self.kwargs = kw
            self.chat = Chat()
            Client.last_client = self

    module = types.ModuleType("openai")
    module.OpenAI = Client
    module.AuthenticationError = AuthenticationError
    module.PermissionDeniedError = PermissionDeniedError
    module.BadRequestError = BadRequestError
    module.APIError = APIError
    module.RateLimitError = RateLimitError
    monkeypatch.setitem(sys.modules, "openai", module)
    return module


def test_openai_provider_chat_returns_reply_text(monkeypatch):
    _install_fake_openai(monkeypatch, reply_text="hello from gpt")

    reply = OpenAIProvider(api_key="sk-test").chat(
        [{"role": "user", "content": "hi"}]
    )

    assert reply == "hello from gpt"


def test_openai_provider_chat_translates_user_messages_to_openai_messages(monkeypatch):
    fake = _install_fake_openai(monkeypatch, reply_text="ok")

    OpenAIProvider(api_key="k").chat(
        [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
    )

    sent = fake.OpenAI.last_client.chat.completions.last_kwargs
    # Plain-string messages pass through unchanged.
    assert sent["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ]


def test_openai_provider_chat_passes_bounded_timeout(monkeypatch):
    """The SDK's default timeout is generous; the REPL needs a tight
    bound so a flaky network doesn't freeze the key prompt for
    minutes."""
    fake = _install_fake_openai(monkeypatch, reply_text="ok")

    OpenAIProvider(api_key="k").chat([{"role": "user", "content": "hi"}])

    client = fake.OpenAI.last_client
    assert client.timeout is not None
    assert 0 < client.timeout <= 300


def test_openai_provider_chat_handles_empty_content_gracefully(monkeypatch):
    """A finish_reason of ``content_filter`` can leave ``message.content``
    as ``None``. Return an empty string rather than crashing."""
    _install_fake_openai(
        monkeypatch, reply_text=None, finish_reason="content_filter"
    )

    reply = OpenAIProvider(api_key="k").chat(
        [{"role": "user", "content": "bad prompt"}]
    )
    assert reply == ""


def test_openai_provider_without_sdk_raises_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)

    with pytest.raises(ImportError):
        OpenAIProvider(api_key="k").chat([{"role": "user", "content": "hi"}])


def test_openai_provider_turn_returns_text_response(monkeypatch):
    _install_fake_openai(monkeypatch, reply_text="hello", finish_reason="stop")

    response = OpenAIProvider(api_key="k").turn(
        [{"role": "user", "content": "hi"}], tools=[]
    )

    assert response.stop_reason == "end_turn"
    assert response.content == [{"type": "text", "text": "hello"}]


def test_openai_provider_turn_returns_tool_use_when_model_calls_function(monkeypatch):
    _install_fake_openai(
        monkeypatch,
        reply_text="let me check",
        tool_calls=[
            {"id": "call_abc", "name": "read_draft", "arguments": "{}"}
        ],
        finish_reason="tool_calls",
    )

    response = OpenAIProvider(api_key="k").turn(
        [{"role": "user", "content": "what's in the draft?"}], tools=[]
    )

    assert response.stop_reason == "tool_use"
    # Both the text preamble and the tool_use block surface.
    kinds = [b["type"] for b in response.content]
    assert kinds == ["text", "tool_use"]
    tool_block = response.content[1]
    assert tool_block["id"] == "call_abc"
    assert tool_block["name"] == "read_draft"
    assert tool_block["input"] == {}


def test_openai_provider_turn_parses_tool_call_arguments_json(monkeypatch):
    """OpenAI returns arguments as a JSON string; the agent expects a
    dict. Translation must decode."""
    _install_fake_openai(
        monkeypatch,
        reply_text=None,
        tool_calls=[
            {
                "id": "call_1",
                "name": "propose_typo_fix",
                "arguments": '{"page": 2, "before": "dragn", "after": "dragon", "reason": "typo"}',
            }
        ],
        finish_reason="tool_calls",
    )

    response = OpenAIProvider(api_key="k").turn(
        [{"role": "user", "content": "fix typos"}], tools=[]
    )

    tool_block = next(b for b in response.content if b["type"] == "tool_use")
    assert tool_block["input"] == {
        "page": 2,
        "before": "dragn",
        "after": "dragon",
        "reason": "typo",
    }


def test_openai_provider_turn_forwards_tool_schemas_to_sdk(monkeypatch):
    from src.agent import Tool as AgentTool

    fake = _install_fake_openai(monkeypatch, reply_text="ok")
    tool = AgentTool(
        name="read_draft",
        description="Read the loaded PDF draft",
        input_schema={"type": "object", "properties": {}},
        handler=lambda _i: "",
    )
    OpenAIProvider(api_key="k").turn(
        [{"role": "user", "content": "hi"}], tools=[tool]
    )

    sent = fake.OpenAI.last_client.chat.completions.last_kwargs
    assert sent["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "read_draft",
                "description": "Read the loaded PDF draft",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def test_openai_provider_turn_translates_tool_result_messages_back_to_openai(monkeypatch):
    """Agent's tool_result blocks must land on the SDK as role=tool
    messages with the matching ``tool_call_id``. An assistant message
    with tool_use blocks becomes role=assistant + tool_calls array."""
    fake = _install_fake_openai(monkeypatch, reply_text="done")

    messages = [
        {"role": "user", "content": "read it"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "sure"},
                {
                    "type": "tool_use",
                    "id": "call_abc",
                    "name": "read_draft",
                    "input": {"page": 1},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_abc",
                    "content": "Page 1: Hello",
                }
            ],
        },
    ]

    OpenAIProvider(api_key="k").turn(messages, tools=[])

    sent = fake.OpenAI.last_client.chat.completions.last_kwargs
    sent_msgs = sent["messages"]
    # user → assistant-with-tool_calls → tool-result
    assert sent_msgs[0] == {"role": "user", "content": "read it"}
    assistant = sent_msgs[1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "sure"
    assert assistant["tool_calls"] == [
        {
            "id": "call_abc",
            "type": "function",
            "function": {
                "name": "read_draft",
                "arguments": '{"page": 1}',
            },
        }
    ]
    assert sent_msgs[2] == {
        "role": "tool",
        "tool_call_id": "call_abc",
        "content": "Page 1: Hello",
    }


def test_openai_provider_turn_preserves_ids_for_parallel_tool_calls(monkeypatch):
    fake = _install_fake_openai(monkeypatch, reply_text="continuing")

    messages = [
        {"role": "user", "content": "check both pages"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_A",
                    "name": "read_draft",
                    "input": {},
                },
                {
                    "type": "tool_use",
                    "id": "call_B",
                    "name": "read_draft",
                    "input": {},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_A", "content": "A"},
                {"type": "tool_result", "tool_use_id": "call_B", "content": "B"},
            ],
        },
    ]

    OpenAIProvider(api_key="k").turn(messages, tools=[])

    sent = fake.OpenAI.last_client.chat.completions.last_kwargs["messages"]
    # Two separate tool messages with distinct tool_call_ids.
    tool_msgs = [m for m in sent if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_A", "call_B"]
    assert [m["content"] for m in tool_msgs] == ["A", "B"]


def test_openai_provider_turn_surfaces_non_stop_finish_reason(monkeypatch):
    """``length`` (truncation) / ``content_filter`` (policy block) must
    not vanish silently. Surface a warning text block so the user sees
    why the turn ended."""
    _install_fake_openai(
        monkeypatch, reply_text=None, finish_reason="content_filter"
    )

    response = OpenAIProvider(api_key="k").turn(
        [{"role": "user", "content": "bad"}], tools=[]
    )

    texts = [b["text"] for b in response.content if b.get("type") == "text"]
    assert texts
    assert "content_filter" in texts[0]


def test_openai_provider_turn_passes_bounded_timeout(monkeypatch):
    fake = _install_fake_openai(monkeypatch, reply_text="ok")

    OpenAIProvider(api_key="k").turn(
        [{"role": "user", "content": "hi"}], tools=[]
    )

    client = fake.OpenAI.last_client
    assert client.timeout is not None
    assert 0 < client.timeout <= 300
