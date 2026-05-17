---
id: LESSON-022
title: "Eager top-level imports defeat pre-API guards in CLI wrappers"
component: "adlc/tools/kimi"
domain: "adlc/tools"
stack: ["python"]
concerns: ["correctness", "testability", "privacy", "fail-loud"]
tags: ["imports", "guards", "lazy-import", "dependency-light", "cli", "exfiltration-notice"]
req: BUG-056
created: 2026-05-17
updated: 2026-05-17
---

## Context

`tools/kimi/tests/test_cli_warn.py` had 4 tests failing silently since at
least REQ-413 (the test/CLI pair that added the exfiltration notice and the
`--dry-run` / clobber-guard contracts). REQ-425 verify flagged the failures
as out-of-scope; they were root-caused 2026-05-15 but the fix sat unshipped
in the working tree until BUG-056 (2026-05-17).

The failing tests assert that the privacy notice, `--dry-run` exit, and
"target already exists" clobber guard all run **before** `get_client()` —
explicitly so users see the privacy notice (and dry-runners avoid needing a
key) even when the API is never called. Both `ask-kimi` and `kimi-write`
have inline comments stating "Notice fires ... BEFORE get_client()".

The root cause: `_common.py` did `import openai` at module top level. Both
CLIs do `import _common` before anything else, so on any machine without
the `openai` SDK installed the CLI crashed at module load — *before* the
arg parser, dry-run gate, clobber guard, or notice could fire. The 4 tests
that asserted positive behavior ("notice IS in stderr", "dry-run exits 0",
"clobber message present") failed. The other 4 ("notice NOT in stderr",
"returncode != 0") passed by accident — a Python traceback satisfies both
negative assertions.

The fix moved `import openai` inside `get_client()` (also reachable from
`complete()`, which only runs after `get_client()` succeeds). The module's
own docstring claimed "Dependency-light by design" — the eager import
contradicted that intent.

## Lesson

**For CLI wrappers with pre-API guards (privacy notices, dry-runs, validity
checks, clobber protections), defer heavy/optional imports until the code
path that actually needs them.** Top-level `import foo` for a network SDK
means `python cli.py --dry-run` fails on machines without `foo` — even
though `--dry-run` was specifically designed not to need it. This is a
silent contract violation: users who never intended to call the API can't
even run `--help`.

## Why It Matters

The bug is **invisible on any machine that has the optional SDK installed**
— including most dev boxes — so it survives normal local test runs and
ships. It only manifests on a clean interpreter (fresh CI, a teammate's
box, a minimal container), exactly where the privacy/exfiltration notice
*most* needs to fire. A guard that silently doesn't run is worse than no
guard. Verification must be made load-bearing by deliberately running in an
environment where the optional dep is **absent** (BUG-056 used a throwaway
openai-less venv: 4-failed→8-passed; the project's normal `kimi-venv` run
was green before *and* after and proved nothing).

## How to apply

- Audit shared-helper modules that CLIs import unconditionally. If they
  pull in a network SDK / heavy dep at module top, push that import into
  the function that actually uses it.
- When a docstring promises "dependency-light," enforce it: `python -c
  "import _common"` should succeed without optional deps installed.
- When designing tests for pre-API guards, deliberately run them in an
  environment where the API SDK is *not* installed. If a positive
  assertion (e.g. "notice IS in stderr") and the negation pair (e.g.
  "notice NOT in stderr") can both pass against a traceback, the negative
  test is masking the bug. Add a positive assertion to every guard test —
  e.g. require `returncode == 0` for `--dry-run`, or grep for a specific
  user-facing string for clobber guards, so a traceback fails the test
  loudly.
- More generally: a "negative" assertion alone (X not in output) is a weak
  signal. Pair it with a positive assertion that the *expected* alternate
  path executed (specific exit code, specific message).

## Applies When

- Reviewing/adding any CLI wrapper or shared helper that imports an
  optional/network SDK at module scope while also offering an offline path
  (`--help`, `--dry-run`, validation, a privacy/consent notice).
- Designing tests for "guard runs before the API" contracts — run them
  without the SDK.

## Related

- BUG-056 — this fix (lazy `import openai` in `tools/kimi/_common.py`).
- LESSON-009 (hotfix verify finds what original verify missed) — same
  pattern: a regression that test coverage *should* have caught sat on
  `main` because the test asserted only the negative side of the contract.
- LESSON-006 (fail-loud installers) — the "dependency-light by design"
  promise is the kimi-tools equivalent of fail-loud: violations should be
  visible at import time, not at test-collection time.
