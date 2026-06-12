---
id: TASK-004
title: "adlc doctor forge check — extends REGISTRY, supersedes gh-auth (BR-7)"
status: complete
parent: REQ-520
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001, TASK-002]
---

## Description

Add a `forge` check to the REQ-519 doctor REGISTRY that reports resolved provider,
backend CLI presence, auth validity, and a read-only API probe — with copy-pasteable
remediation per failure. It supersedes/wraps the existing `gh-auth` check (one auth
mechanism, not a parallel one). `skip`-with-reason when the repo has no remote.

## Files to Create/Modify

- `tools/adlc/checks.py` — add `check_forge(profile)`, register it in `REGISTRY`;
  REMOVE `check_gh_auth` from `REGISTRY` (its `gh auth status` probe folded into
  `check_forge` on the github branch). Keep `check_gh_present` (relevant when provider
  resolves to github).
- `tools/adlc/tests/test_checks.py` — extend: forge check PASS/FAIL/SKIP on
  github+gh-authed, ado+PAT-set, ado+no-PAT, no-remote.

## Acceptance Criteria

- [ ] `check_forge` resolves the provider by sourcing `partials/forge.sh` under bash
      (mirrors `_gate_verdict` sourcing `delegate-gate.sh`); no remote → `SKIP` with
      reason.
- [ ] Reports: resolved provider, backend CLI present (`gh`/`az`), auth valid
      (`gh auth status` / `az account show` or PAT-var set), read-only API probe
      (`pr_list` via mock or a bounded call). Each FAIL has copy-pasteable remediation.
- [ ] `check_gh_auth` removed from REGISTRY; no duplicate/parallel gh-auth mechanism.
- [ ] Doctor verdict honest: SKIP (no remote, or provider-irrelevant CLI) never fails
      the run; only genuine auth/CLI/probe failures FAIL (REQ-519 BR-4/BR-6).
- [ ] Test matrix asserts PASS/FAIL/SKIP across github+authed, ado+PAT, ado+no-PAT,
      no-remote.

## Technical Notes

Reuse the `_partial_path`, `_gate_verdict`-style bash-source probe, and Profile/Result
patterns already in `checks.py`. The ADO auth probe must not require `az` to be present
(absent `az` on an ADO repo → FAIL with `brew`/extension remediation, not a crash). Use
the mock (`ADLC_FORGE_MOCK=1`) for the API probe in tests so it stays offline.
