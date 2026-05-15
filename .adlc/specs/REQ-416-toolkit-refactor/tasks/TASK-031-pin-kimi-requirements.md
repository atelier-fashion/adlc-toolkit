---
id: TASK-031
title: "Pin tools/kimi/requirements.txt and update install.sh"
status: draft
parent: REQ-416
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Resolve REQ-416 BR-6 and BR-7 (ADR-5). Replace the `pip install --upgrade openai pytest`
inline package list in `tools/kimi/install.sh` with a pinned
`tools/kimi/requirements.txt`, so reproducing the venv produces a deterministic
environment and an upstream `openai` SDK break never silently lands.

## Files to Create/Modify

- `tools/kimi/requirements.txt` — NEW. Two lines: `openai==<VERSION>` and
  `pytest==<VERSION>`. Versions are read from `~/.claude/kimi-venv/bin/pip freeze`
  on a known-good machine before the task starts (typically the developer's
  workstation). At time of architecture: openai 2.36.0 was observed in
  TASK-021 logs — use the actual current version, not this stale reference.
- `tools/kimi/install.sh` — replace line `"$VENV_DIR/bin/pip" install --upgrade openai pytest`
  with `"$VENV_DIR/bin/pip" install -r "$REPO_ROOT/tools/kimi/requirements.txt"`.
  The `--upgrade` flag is dropped intentionally — `pip install -r` will install
  exactly the pinned versions on a fresh venv and will upgrade/downgrade to
  match pins on subsequent runs (BR-7).
- `tools/kimi/README.md` — add a short "Updating dependencies" section
  documenting that bumps go through a hotfix REQ when the pinned API changes.

## Acceptance Criteria

- [ ] `tools/kimi/requirements.txt` exists with pinned versions for `openai`
      and `pytest` (exact `==` pins, no `~=` or `>=`).
- [ ] `tools/kimi/install.sh` references `requirements.txt` and no longer
      hardcodes `openai pytest` as a positional argument.
- [ ] Running `tools/kimi/install.sh` from a clean state (delete `~/.claude/kimi-venv`)
      produces a venv where `pip freeze | grep -E '^(openai|pytest)=='` matches
      the pinned versions exactly.
- [ ] Bumping a version in `requirements.txt` and re-running `install.sh`
      updates the venv to the new pin (BR-7 verified).
- [ ] `tools/kimi/README.md` documents the bump workflow.
- [ ] `tools/kimi/tests/` pytest suite passes after the install (REQ-413
      29-test suite — BR-8).

## Technical Notes

- Pin to the versions currently installed in the developer's venv. Run
  `~/.claude/kimi-venv/bin/pip freeze | grep -E '^(openai|pytest)=='` and
  copy the output verbatim.
- `install.sh` already has `set -eu` — no need to add error handling around
  the `pip install` line; a missing requirements.txt will fail loud.
- Do NOT add `--require-hashes` — that's a supply-chain hardening step
  beyond REQ-416 scope. Logged here for a future REQ.
