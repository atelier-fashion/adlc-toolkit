---
id: BUG-056
title: "Eager top-level `import openai` in tools/kimi/_common.py defeats pre-API guards"
status: in-review
severity: high
created: 2026-05-17
updated: 2026-05-17
component: "adlc/tools/kimi"
domain: "adlc/tools"
stack: ["python"]
concerns: ["correctness", "testability", "privacy", "fail-loud"]
tags: ["imports", "guards", "lazy-import", "dependency-light", "cli", "exfiltration-notice"]
---

## Description

`tools/kimi/_common.py` performs `import openai` at module top level. Both
Kimi CLIs (`ask-kimi`, `kimi-write`) do `import _common` before anything
else, so on any machine where the `openai` SDK is not installed the CLI
crashes at module load — *before* the argument parser, the privacy/
exfiltration notice, the `--dry-run` gate, or the clobber guard can run.
The module docstring claims "Dependency-light by design", which the eager
import contradicts.

## Reproduction Steps

1. On a machine (or venv) where `openai` is **not** installed.
2. Run `python tools/kimi/ask-kimi --dry-run ...` (or `--help`, or any
   invocation that should be answerable without an API call).
3. Observe: `ImportError: No module named 'openai'` traceback at import
   time.
4. Run `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/test_cli_warn.py -q`
   — the 4 positive-assertion tests fail.

## Expected Behavior

The privacy/exfiltration notice, `--dry-run` exit (0), and "target already
exists" clobber guard all run **before** `get_client()` — by contract
(both CLIs carry inline comments stating "Notice fires ... BEFORE
get_client()"). A user who never calls the API should still see the privacy
notice and be able to `--dry-run` / `--help` with no API key and no SDK.

## Actual Behavior

`import _common` → top-level `import openai` → `ImportError` at module load.
The 4 positive-assertion tests in `test_cli_warn.py` ("notice IS in
stderr", "dry-run exits 0", "clobber message present") fail. The 4
negative-pair tests pass *by accident* because a Python traceback also
satisfies "notice NOT in stderr" / "returncode != 0".

## Environment

- Platform: any machine without the `openai` SDK installed
- Version: present since ~REQ-413 (added the notice / dry-run / clobber
  contracts); has sat unshipped on the working tree since 2026-05-15.

## Root Cause

Verified against `origin/main` (`tools/kimi/_common.py:9`): the module does
`import openai` at top level. `import os` / `import sys` precede it; the
`openai` import is the only heavy/optional dependency and it is eager.

Both CLIs (`ask-kimi:14`, `kimi-write`) do `import _common  # noqa: E402`
as their first project import — *before* `argparse`, the `--dry-run` gate,
the clobber guard, and `_common.emit_exfil_notice()`. `ask-kimi:63-68`
documents the contract explicitly: "Notice fires after the dry-run gate and
after path validation, but BEFORE get_client()".

Because Python executes `_common`'s top-level `import openai` at the moment
`import _common` runs, on any interpreter without the `openai` SDK the
process dies with `ImportError` at module-load time — strictly before any
guard can run. The 4 positive-assertion tests in `test_cli_warn.py`
(`test_ask_kimi_notice_fires_by_default`,
`test_ask_kimi_dry_run_does_not_emit_notice`,
`test_kimi_write_notice_fires_by_default`,
`test_kimi_write_clobber_guard_fires_before_notice`) fail; the negative-pair
tests pass by accident because a traceback also satisfies "notice NOT in
stderr" / "returncode != 0". The bug is **masked on any machine that
happens to have `openai` installed** (e.g. this dev box), which is why it
sat unshipped — it only manifests on a clean/SDK-less interpreter. The
module docstring's "Dependency-light by design" is contradicted by the
eager import.

Fix: defer `import openai` into `get_client()` (the only function that
needs it; `complete()` only runs after `get_client()` succeeds).

## Resolution

Moved `import openai` from `_common.py` module top level into
`get_client()` (the only consumer; `complete()` runs only after
`get_client()` succeeds). Added a docstring note explaining the laziness so
a future reader doesn't "tidy" it back to a top-level import. No behavior
change when `openai` IS installed; when it is NOT, the pre-API guards
(privacy/exfiltration notice, `--dry-run`, clobber check) now run as
contracted instead of dying at import.

Verification was made **load-bearing** by running `test_cli_warn.py` in an
isolated venv WITHOUT `openai` (the bug is masked on any box that has the
SDK — including the dev machine — so the project's normal
`~/.claude/kimi-venv` run would pass before *and* after and prove nothing):

- Before fix, openai-less venv: `4 failed, 4 passed` — failures show
  `_common.py:9 import openai / ModuleNotFoundError` (exact reproduction).
- After fix, openai-less venv: `8 passed`.
- Regression sweep, `~/.claude/kimi-venv/bin/pytest tools/kimi/tests/`
  (openai present): `68 passed`.
- `import _common` succeeds with no `openai` installed.

## Files Changed

- `tools/kimi/_common.py` — remove top-level `import openai`; add lazy
  `import openai` inside `get_client()`; docstring note on why it is lazy.

