"""Image-generation providers.

A narrow seam between the agent's ``generate_cover_illustration`` tool
and an external image API. We intentionally keep the protocol small —
prompt in, PNG file on disk out — so swapping providers later (Stability,
Replicate, a local Stable Diffusion daemon) is a one-file change.

The contract every provider implements:

- ``generate(prompt, output_path, size, quality) -> Path`` — write a PNG
  at ``output_path`` and return the same path. Raises
  ``ImageGenerationError`` for anything the caller shouldn't retry
  with the same inputs (auth failure, rate limit, policy rejection,
  missing SDK). Network blips should also surface as
  ``ImageGenerationError`` — the tool layer reports a clean message
  to the user rather than guessing at retry semantics.

The only concrete provider today is ``OpenAIImageProvider`` (model
``gpt-image-1``). The SDK import is lazy so a user on an Ollama-only
path doesn't need it installed.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Protocol, runtime_checkable


class ImageGenerationError(Exception):
    """Raised when an ``ImageProvider.generate`` call can't produce a
    PNG the caller can use — auth failure, API error, empty response,
    missing SDK. The tool layer forwards the message to the user."""


@runtime_checkable
class ImageProvider(Protocol):
    def generate(
        self,
        prompt: str,
        output_path: Path,
        size: str = "1024x1536",
        quality: str = "medium",
    ) -> Path: ...


class OpenAIImageProvider:
    """OpenAI ``gpt-image-1`` adapter.

    Uses the same API key the LLM provider uses — we assume the user
    has one OpenAI credential, not two. Responses come back as
    base64-encoded PNG; we decode and write them atomically.
    """

    MODEL = "gpt-image-1"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def generate(
        self,
        prompt: str,
        output_path: Path,
        size: str = "1024x1536",
        quality: str = "medium",
    ) -> Path:
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImageGenerationError(
                "The 'openai' SDK is missing from this install. Try: "
                "pip install --force-reinstall littlepress-ai"
            ) from e

        client = openai.OpenAI(api_key=self._api_key)
        auth_error = getattr(openai, "AuthenticationError", None) or RuntimeError
        perm_error = getattr(openai, "PermissionDeniedError", None) or auth_error
        api_error = getattr(openai, "APIError", None) or RuntimeError

        try:
            response = client.images.generate(
                model=self.MODEL,
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
            )
        except (auth_error, perm_error) as e:
            raise ImageGenerationError(f"OpenAI rejected the request: {e}") from e
        except api_error as e:
            raise ImageGenerationError(f"OpenAI image generation failed: {e}") from e

        b64 = response.data[0].b64_json if response.data else None
        if not b64:
            raise ImageGenerationError(
                "OpenAI returned an empty image — often means the prompt "
                "hit a policy filter. Rephrase and try again."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(b64))
        return output_path
