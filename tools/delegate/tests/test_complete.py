"""Offline tests for ``_common.complete()``'s finish_reason contract (BUG-213).

Before BUG-213, ``complete()`` raised only when the returned content was empty
and never read ``finish_reason``. A completion that stopped at ``max_tokens``
with content already emitted was returned as a whole answer — and on the
``adlc-write`` path, written to ``--target`` under a success line. The single
most important assertion in this file is therefore
``test_length_with_content_raises``: a ``length`` finish MUST fail even when
there is content to return.

The client is a stand-in with the one attribute chain ``complete()`` touches,
``client.chat.completions.create(...)``. No network, no SDK objects.
"""

import importlib.util
import os
from importlib.machinery import SourceFileLoader
from types import SimpleNamespace

import pytest

import _common

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.dirname(HERE)


def _resp(content, finish_reason="stop", reasoning_tokens=None, choices=True):
    """Build the minimal response shape ``complete()`` reads."""
    usage = None
    if reasoning_tokens is not None:
        usage = SimpleNamespace(
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens)
        )
    if not choices:
        return SimpleNamespace(choices=[], usage=usage)
    choice = SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish_reason
    )
    return SimpleNamespace(choices=[choice], usage=usage)


class _Client:
    def __init__(self, resp):
        self.calls = []
        create = self._create
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        self._resp = resp

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


def _run(resp, max_tokens=20000):
    return _common.complete(_Client(resp), "m", [{"role": "user", "content": "q"}], max_tokens)


# --- the regression that matters -------------------------------------------

def test_length_with_content_raises():
    """A ``length`` finish with content already emitted must NOT be returned.

    This is the BUG-213 write-path failure: 188 lines ending in a bare
    ``assert`` were handed back as a whole file. Returning here would let
    ``adlc-write`` persist it under ``wrote:``.
    """
    partial = "def test_a():\n    assert"
    with pytest.raises(SystemExit) as exc:
        _run(_resp(partial, finish_reason="length"), max_tokens=16384)
    msg = str(exc.value)
    assert "truncated" in msg
    assert "finish_reason=length" in msg
    assert "16384" in msg, "the message names the cap that was hit"
    assert f"{len(partial.strip())} characters" in msg, "the caller learns it was partial, not empty"
    assert "discarded" in msg
    # The partial output itself is never leaked through the message.
    assert partial not in msg


def test_length_with_empty_content_raises_and_says_so():
    with pytest.raises(SystemExit) as exc:
        _run(_resp("", finish_reason="length"), max_tokens=8192)
    msg = str(exc.value)
    assert "finish_reason=length" in msg
    assert "no output was emitted" in msg
    assert "8192" in msg


def test_length_reports_reasoning_tokens_when_provider_gives_them():
    with pytest.raises(SystemExit) as exc:
        _run(_resp("x", finish_reason="length", reasoning_tokens=14706))
    assert "14706 tokens reasoning" in str(exc.value)


def test_length_without_usage_details_still_raises_cleanly():
    """Every level of ``usage`` is optional across providers; absence is not an error."""
    resp = _resp("x", finish_reason="length")
    resp.usage = SimpleNamespace()  # usage present, no completion_tokens_details
    with pytest.raises(SystemExit) as exc:
        _common.complete(_Client(resp), "m", [], 100)
    msg = str(exc.value)
    assert "truncated" in msg
    assert "tokens reasoning" not in msg, "no count is reported when the provider gave none"


def test_length_whitespace_only_counts_as_no_output():
    with pytest.raises(SystemExit) as exc:
        _run(_resp("   \n\t", finish_reason="length"))
    assert "no output was emitted" in str(exc.value)


# --- non-length finishes -----------------------------------------------------

def test_stop_with_content_returns_it_unchanged():
    assert _run(_resp("hello\n", finish_reason="stop")) == "hello\n"


def test_stop_with_empty_content_names_the_reason_not_max_tokens():
    """The old message asserted ``increase --max-tokens`` for every empty result.

    A ``stop`` finish with nothing in it did not hit the cap; raising the cap
    cannot help, and the message must not send the operator there (LESSON-581).
    """
    with pytest.raises(SystemExit) as exc:
        _run(_resp("", finish_reason="stop"))
    msg = str(exc.value)
    assert "finish_reason=stop" in msg
    assert "increase --max-tokens" not in msg
    assert "will not help" in msg


def test_content_filter_with_empty_content_names_content_filter():
    with pytest.raises(SystemExit) as exc:
        _run(_resp("", finish_reason="content_filter"))
    assert "finish_reason=content_filter" in str(exc.value)


def test_missing_finish_reason_with_empty_content_reports_unknown():
    resp = _resp("")
    del resp.choices[0].finish_reason
    with pytest.raises(SystemExit) as exc:
        _common.complete(_Client(resp), "m", [], 100)
    assert "finish_reason=unknown" in str(exc.value)


def test_none_content_with_stop_is_treated_as_empty():
    """Some providers return ``content: null`` rather than ``""``."""
    with pytest.raises(SystemExit) as exc:
        _run(_resp(None, finish_reason="stop"))
    assert "empty completion" in str(exc.value)


def test_no_choices_keeps_the_existing_message():
    with pytest.raises(SystemExit) as exc:
        _run(_resp("", choices=False))
    assert "no choices" in str(exc.value)


def test_max_tokens_is_forwarded_to_the_api():
    client = _Client(_resp("ok"))
    _common.complete(client, "model-x", [{"role": "user", "content": "q"}], 4321)
    assert client.calls == [
        {"model": "model-x", "messages": [{"role": "user", "content": "q"}], "max_tokens": 4321}
    ]


# --- the shared default --------------------------------------------------------

def _load_cli(name):
    path = os.path.join(DELEGATE_DIR, name)
    modname = "_cli_complete_" + name.replace("-", "_")
    loader = SourceFileLoader(modname, path)
    spec = importlib.util.spec_from_loader(modname, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _default_max_tokens(module):
    for action in module._build_parser()._actions:
        if "--max-tokens" in action.option_strings:
            return action.default
    raise AssertionError("--max-tokens not declared")


def test_shared_default_value():
    """20000 clears every measured draw (BUG-213); a lower value is a regression."""
    assert _common.DEFAULT_MAX_TOKENS == 20000


@pytest.mark.parametrize("cli", ["adlc-read", "adlc-write"])
def test_cli_default_is_the_shared_constant(cli):
    """Both CLIs read the SAME constant — they drifted apart once (8192 vs 16384)."""
    assert _default_max_tokens(_load_cli(cli)) is _common.DEFAULT_MAX_TOKENS
