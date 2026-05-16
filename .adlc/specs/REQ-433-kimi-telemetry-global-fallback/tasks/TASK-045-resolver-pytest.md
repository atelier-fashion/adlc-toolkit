---
id: TASK-045
title: "Add pytest coverage for the kimi-tools-path resolver"
status: complete
parent: REQ-433
created: 2026-05-16
updated: 2026-05-16
dependencies: [TASK-043]
repo: adlc-toolkit
---

## Description

Add an offline pytest module that exercises the resolver partial's three
resolution paths and its non-fatal contract, mirroring the structure of the
existing `tools/kimi/tests/test_partials.py`.

## Files to Create/Modify

- `tools/kimi/tests/test_kimi_tools_path.py` — **new** pytest module.

## Acceptance Criteria

- [ ] Test: with a fake CWD containing `tools/kimi/emit-telemetry.sh` (executable), sourcing the partial sets `KIMI_TOOLS=tools/kimi`.
- [ ] Test: with no local `tools/kimi` but a fake `$HOME/.claude/skills/tools/kimi/emit-telemetry.sh`, `KIMI_TOOLS` resolves to that `$HOME/...` path.
- [ ] Test: with neither present, the partial still exports `KIMI_TOOLS` (== `tools/kimi`, ADR-2 degrade) and exits 0 (non-fatal).
- [ ] Test: sourcing the partial inside a `sh -eu` caller does NOT abort the caller (run `sh -eu -c '. partial; echo OK'`, assert `OK` and rc 0).
- [ ] Test: the partial emits nothing to stdout or stderr on any path.
- [ ] `pytest tools/kimi/tests/ -q` passes fully (new + all pre-existing tests, AC-4).
- [ ] New tests are offline — no network, no real `~/.claude` mutation (use `tmp_path` + `env` overrides for `HOME`).

## Technical Notes

- Mirror `test_partials.py`: it almost certainly shells out via `subprocess`
  with `sh -c '. <partial>; printf %s "$VAR"'` and a controlled `cwd`/`env`.
  Read it first and follow its harness conventions (fixtures, helper to run a
  partial, `HOME` override pattern).
- Drive resolution by constructing temp dirs: create
  `tmp/tools/kimi/emit-telemetry.sh` (chmod +x) for the local case; set
  `env HOME=tmp_home` and create `tmp_home/.claude/skills/tools/kimi/emit-telemetry.sh`
  for the global case; empty dirs for the degrade case.
- Assert on `KIMI_TOOLS` value printed by the sourcing subshell, plus return
  code, plus captured stdout/stderr emptiness.
- POSIX `sh` only in the harness invocation (`sh`, not `bash`) to match the
  execution environment skills run under (LESSON-013).
- This task is independent of TASK-044 (parallelizable) — it depends only on the
  partial contract from TASK-043.
