---
id: TASK-005
title: "tests for adlc dispatch, doctor runner, checks, --checks filter, exit codes"
status: draft
parent: REQ-519
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-003]
repo: adlc-toolkit
---

## Description

Offline pytest suite for `tools/adlc/`, mirroring the `tools/kimi/tests`
discipline (path-injecting conftest, `tmp_path` fixtures, no real network/
machine mutation). Covers BR-1/4/6/8 logic that lives in Python.

## Files to Create/Modify

- `tools/adlc/tests/conftest.py` — repo-root path injection (mirror
  `tools/kimi/tests/conftest.py`: `sys.path.insert` to `tools/adlc`, a
  `repo_root` fixture via `git rev-parse --show-toplevel` that SKIPs cleanly if
  git is absent).
- `tools/adlc/tests/test_dispatch.py` — `adlc --version`, no-subcommand usage,
  unknown subcommand error, dispatch table is data-driven.
- `tools/adlc/tests/test_doctor.py` — runner iterates registry in order;
  `--checks` subset; unknown id rejected with non-zero; verdict/exit-code (SKIP
  never fails); report format (PASS/FAIL/SKIP lines, remediation on FAIL).
- `tools/adlc/tests/test_checks.py` — per-check pass/fail/skip via fixtures:
  fake `~/.claude` tree under `tmp_path` (symlink present/absent/dangling),
  fake counters (numeric/non-numeric/absent), stale `.lock.d`, monkeypatched
  PATH for `path-shims`/`gh-present`, `applies_to` gating launchctl off on a
  simulated Linux profile, `delegate-gate` mapping for rc 0/1/2.

## Acceptance Criteria

- [ ] Tests are fully offline: no network, no mutation of the real `~/.claude`
      or real counters (use `tmp_path` + monkeypatch).
- [ ] `--checks` filter and unknown-id rejection are tested.
- [ ] Exit-code derivation tested: a FAIL → non-zero; all-PASS/SKIP → zero;
      SKIP-only → zero.
- [ ] launchctl SKIP-on-Linux tested via an injected `Profile(os="Linux")`.
- [ ] `delegate-gate` rc→Result mapping tested for all three rc values
      (mock the partial invocation; don't require a real delegate).
- [ ] `pytest tools/adlc/tests` passes from the repo root.

## Technical Notes

- Mirror `tools/kimi/tests/conftest.py` exactly for path injection so
  `import adlc`, `import doctor`, `import checks` resolve.
- Inject the machine `Profile` rather than reading the real machine, so the
  same test runs identically on macOS and Linux CI.
- For `delegate-gate`, monkeypatch the subprocess call that sources the partial
  to return canned `(rc, reason)` triples — the check's mapping logic is the
  unit under test, not the partial itself (the partial is REQ-515's, already
  tested under `tools/kimi/tests/test_partials.py`).
- Do NOT add a CI workflow file (the repo has none and runs tests via
  dogfooding); just ensure `pytest tools/adlc/tests` is green locally.
