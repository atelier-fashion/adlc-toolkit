---
id: BUG-054
title: "lint-skills check.py leaks absolute filesystem paths into stdout/CI logs"
status: open
severity: low
created: 2026-05-16
updated: 2026-05-16
component: "tools/lint-skills"
domain: "tooling"
stack: ["python"]
concerns: ["security"]
tags: ["info-disclosure", "path-leak", "linter", "ci-logs"]
---

## Description

`tools/lint-skills/check.py`'s `run()` has two branches in the per-skill loop
that emit a `Finding` whose `file` field and/or `message` contains an absolute
filesystem path. Findings are printed to stdout by `main()` and therefore land
in CI logs, disclosing the runner's absolute directory layout (home dir,
checkout path, worktree slug). Low-severity information disclosure — found by
the security-auditor during REQ-435's verify phase (Low #1 / Low #2) and
explicitly declared OUT OF SCOPE for REQ-435, hence this standalone bugfix.

Two leak points (current 5-check version, `check.py` lines ~432–440):

- **Leak 1 — `except OSError` branch.**
  `Finding(str(skill_path), 1, "io-error", f"could not read: {exc}")`.
  Both the label `str(skill_path)` *and* `str(exc)` leak the absolute path:
  `str()` of an `OSError` raised by `Path.read_text()` is
  `[Errno 13] Permission denied: '/abs/path/.../SKILL.md'`.

- **Leak 2 — `except ValueError` branch.**
  When `skill_path.relative_to(root)` raises `ValueError`, the code falls
  back to `rel = str(skill_path)` (the absolute path), which is then used as
  the finding label by every subsequent `check_*` call. The symlink guard in
  `find_skill_files` normally makes this branch unreachable, but if reached it
  leaks.

## Reproduction Steps

1. From the repo root, create an unreadable SKILL.md under the scan root:
   `mkdir -p /tmp/leakrepo/x && : > /tmp/leakrepo/x/SKILL.md && chmod 000 /tmp/leakrepo/x/SKILL.md`
2. Run `python3 tools/lint-skills/check.py --root /tmp/leakrepo`
3. Observe stdout.

## Expected Behavior

The `io-error` finding label is root-relative (basename fallback if
`relative_to` fails) and the message contains only the POSIX reason — e.g.
`x/SKILL.md:1: io-error: could not read: Permission denied`. No absolute path
appears anywhere in stdout. The `ValueError` fallback uses the basename, never
the absolute path.

## Actual Behavior

The absolute path is emitted twice:
`/tmp/leakrepo/x/SKILL.md:1: io-error: could not read: [Errno 13] Permission denied: '/tmp/leakrepo/x/SKILL.md'`
— disclosing the absolute filesystem layout in stdout / CI logs.

## Environment

- Platform: adlc-toolkit repo (toolkit dogfood; symlink-install, no staging layer)
- Version: `tools/lint-skills/check.py` at HEAD `b16f4e0` (REQ-436, 5-check version); Python 3

## Root Cause

`run()` constructs the per-skill finding label from the raw `skill_path`
without ever reducing it to a non-leaking form:

- The `except OSError` branch emits `Finding(str(skill_path), 1, "io-error",
  f"could not read: {exc}")`. `str(skill_path)` is the absolute path, and
  `str(exc)` for an `OSError` raised by `open()`/`read_text()` is
  `[Errno N] <strerror>: '<absolute path>'` — the path is disclosed twice.
- The label for all *other* checks is `rel`, computed as
  `str(skill_path.relative_to(root))` with an `except ValueError` fallback of
  `rel = str(skill_path)` — the absolute path. This single `rel` is threaded
  into every `check_*` call, so the fallback leaks through *all five* checks
  at once, not just one finding.

LESSON-007 confirmation: a full sweep of all nine `Finding(` constructions
shows every other finding uses the `rel` parameter, which originates **only**
in `run()`. `load_partials_blob` and `find_skill_files` only `continue` on
error and never emit a path. Therefore producing one non-leaking label in
`run()` — used for both the io-error finding and the `rel` threaded into the
checks — closes every leak point. There is no hidden third site.

Edge cases: `Path.relative_to()` is pure path arithmetic and raises only
`ValueError` (never `OSError`), so a narrow `except ValueError` basename
fallback is correct and sufficient. `OSError.strerror` from
`open()`/`read_text()` is the path-free POSIX reason string (CPython sets it
via `os.strerror(errno)`; the path lives separately in `exc.filename`); it is
`None` only for a hand-constructed `OSError`, which cannot arise from
`read_text()`. The strerror-`None` fallback must therefore be a constant, not
`str(exc)`/`exc`, or it would re-leak.

## Resolution

Added a single `_safe_label(skill_path, root) -> str` helper that returns the
root-relative path, falling back to the **basename** (`skill_path.name`) on
`ValueError` — never the absolute path. The narrow `except ValueError` is
exact: `Path.relative_to` is pure path arithmetic and cannot raise `OSError`.

`run()` now computes this label once per file *before* the read, so both leak
points use it: the `io-error` finding's label is the safe label (was
`str(skill_path)`), and the same label is threaded into all five `check_*`
calls (the old `except ValueError: rel = str(skill_path)` absolute fallback is
deleted). The `io-error` message now uses `exc.strerror or 'I/O error'` — the
path-free POSIX reason, with a constant fallback so it can never re-leak via
`str(exc)`.

Verified red-green: the new regression test fails against the pre-fix HEAD
(absolute tmp path present in stdout) and passes with the fix. Full suite
(`tools/kimi/tests/` + `tools/lint-skills/tests/`) green at 91 passed.

Scope was strictly the two `run()` branches — no check logic touched
(consistent with REQ-435's Out-of-Scope).

## Files Changed

- `tools/lint-skills/check.py` — add `_safe_label` helper; `run()` computes
  the non-leaking label before the read and uses it for the `io-error`
  finding and all `check_*` calls; `io-error` message uses `exc.strerror`
  (path-free) with a constant fallback. Removed the absolute-path
  `except ValueError` fallback.
- `tools/lint-skills/tests/test_check.py` — `import os`; add
  `test_io_error_finding_does_not_leak_absolute_path` asserting an unreadable
  SKILL.md yields a root-relative `io-error` finding with no absolute path and
  no `[Errno` prefix in stdout (root-skip via `pytest.skip` when euid 0).
