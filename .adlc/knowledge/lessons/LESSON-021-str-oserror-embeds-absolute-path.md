---
id: LESSON-021
title: "str(OSError) embeds the absolute path — use exc.strerror for log/CI-visible output"
component: "tools/lint-skills"
domain: "tooling"
stack: ["python"]
concerns: ["security"]
tags: ["info-disclosure", "oserror", "exception-stringification", "ci-logs", "linter"]
req: BUG-054
created: 2026-05-16
updated: 2026-05-16
---

## What Happened

`tools/lint-skills/check.py` carefully reduced every finding label to a
root-relative path — except its `except OSError` branch, which emitted
`Finding(str(skill_path), 1, "io-error", f"could not read: {exc}")`. Both
halves leaked the absolute filesystem path into stdout (→ CI logs):
`str(skill_path)` directly, and `f"...{exc}"` because the string form of an
`OSError` raised by `open()`/`read_text()` is
`[Errno 13] Permission denied: '/abs/path/.../SKILL.md'` — CPython
concatenates `exc.filename` into the message. The `f"...{exc}"` *reads* as
innocuous, so it survived review and shipped as a (deferred) security finding.

## Lesson

`str(exc)` / `f"{exc}"` on an `OSError` (and subclasses `PermissionError`,
`FileNotFoundError`, `IsADirectoryError`, …) embeds the offending **absolute
filename**. When surfacing such an exception into any output that is printed,
logged, serialized, returned to a user, or written to CI, use
**`exc.strerror`** — the path-free POSIX reason — never `str(exc)`. Provide a
**constant** fallback (`exc.strerror or "I/O error"`), never `str(exc)`/`exc`,
because `strerror` is `None` for hand-constructed instances and a `… or exc`
fallback silently re-leaks. The path, if needed, lives separately in
`exc.filename` and must be reduced to a safe label by the same rule used
everywhere else (here: root-relative, basename fallback).

This is the specific *mechanism* behind LESSON-007's discipline ("basename
hardening must be applied at **every** leak point, not just the main one"):
the io-error branch is exactly the kind of secondary leak point LESSON-007
predicts, and `f"...{exc}"` is *why* it hides in plain sight.

## Why It Matters

An information-disclosure vulnerability ships silently: the leaking line looks
safe, so neither author nor reviewer connects "interpolating an exception" to
"re-introducing the absolute path we scrubbed everywhere else." Cost here: a
security-auditor Low finding deferred out of REQ-435, then a full standalone
bugfix cycle (BUG-054). Anywhere exception text reaches a log aggregator or
public CI, it discloses the runner's home dir / checkout layout / worktree
slug.

## Applies When

Surfacing an `OSError`/`IOError` (or subclass) into output that is logged,
printed, returned to a caller, or written to CI — especially in linters,
validators, installers, and any tool whose findings/diagnostics are
CI-visible. Trigger phrase to grep for in review: `{exc}` / `{e}` / `str(e)`
inside an `except OSError` (or bare `except Exception`) that feeds a
user/log/CI sink.
