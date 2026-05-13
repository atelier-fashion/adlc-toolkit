"""Shared helpers for the Kimi delegation CLIs.

Dependency-light by design: only ``os`` from the stdlib plus ``openai``.
"""

import os

import openai

_API_KEY_VAR = "MOONSHOT_API_KEY"
_BASE_URL = "https://api.moonshot.ai/v1"
_DEFAULT_MODEL = "kimi-k2.5"


def get_client():
    """Return an ``openai.OpenAI`` client pointed at the Moonshot API.

    Raises ``SystemExit`` naming the env var if it is unset. The key value is
    never printed.
    """
    api_key = os.environ.get(_API_KEY_VAR)
    if not api_key:
        raise SystemExit(
            f"{_API_KEY_VAR} is not set — add `export {_API_KEY_VAR}=\"...\"` to ~/.zshrc"
        )
    return openai.OpenAI(base_url=_BASE_URL, api_key=api_key)


def get_model():
    """Return the Kimi model name (overridable via ``KIMI_MODEL``)."""
    return os.environ.get("KIMI_MODEL", _DEFAULT_MODEL)


def pack_corpus(paths):
    """Read each path and join them as ``<file path='...'>`` blocks, in order.

    Callers put files before the question so the corpus prefix can be cached.
    """
    blocks = []
    for p in paths:
        with open(p, "r") as fh:
            content = fh.read()
        blocks.append(f"<file path='{p}'>\n{content}\n</file>")
    return "\n\n".join(blocks)


def complete(client, model, messages, max_tokens):
    """Call ``chat.completions.create`` and return the content string.

    Raises ``SystemExit`` if the model returns empty/whitespace content.
    """
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content
    if not content or not content.strip():
        raise SystemExit("empty completion — increase --max-tokens")
    return content
