---
id: BUG-260
title: "`/sprint --exec` let the model push main and force-push: the branch push allow was a prefix rule"
status: resolved
severity: high
created: 2026-11-02
updated: 2026-11-02
component: "adlc/tools/adlc/exec-adapter"
domain: "adlc"
stack: ["python", "yaml"]
concerns: ["security", "correctness"]
tags: ["exec-engine", "allowlist", "prefix-rule", "shared-base", "git-push", "approve-gate", "live-run"]
introduced_by: ["REQ-659"]
attribution: derived
---

## Description

The claude adapter's exec block allowed `Bash(git push -u origin <branch>:*)` and
`Bash(git push origin <branch>:*)`. Claude Code's `:*` admits any text after the prefix, so
those rules admitted `git push -u origin <branch> main`, which updates the integration branch,
and `git push -u origin <branch> --force`. The deny `Bash(git push --force:*)` is a prefix too,
so it never sees a flag after the refspec. `exec_adapter.vet_extra` refused an extra only when
it literally matched a deny form, so it passed these, and `git branch --list` and
`git worktree list` next to `git branch -D` and `git worktree remove`.

## Reproduction Steps

1. Run `tools/adlc/tests/e2e/claude-exec-live.sh force-own-branch extra-refspec-main` with a
   logged-in `claude` (2.1.258).
2. Each row launches `claude -p` with the engine's own argv and asks for the push.

## Expected Behavior

Both pushes are denied, and the throwaway origin's `main` and branch do not move.

## Actual Behavior

Both ran on 2026-11-02: the origin's `main` and the REQ branch moved, with no permission
denial. On an unprotected repo, which `--allow-unprotected` permits, that updates `main`
without `/sprint approve`.

## Environment

macOS, `claude` 2.1.258 logged in through claude.ai, the symlink install, main at `332e176`.

## Root Cause

Prior lessons consulted:
- LESSON-796 — An engine's allowlist is not the harness's policy: the harness merges every settings source it reads, so narrowing the engine's flags alone narrows nothing (score 16)
- LESSON-614 — A governance config needs a recognizer, not a reader — and a differential oracle, not one author's corpus (score 8)
- LESSON-779 — A rule that withholds an allow can withhold a step the pipeline cannot run without: compare the render with the calls the pipeline makes (score 7)
- LESSON-760 — A transcript parser must allow record types, not sniff for message shape: Claude Code's api-request-blob records looked like Human turns (score 7)
- LESSON-744 — Credential redaction chains match inside ordinary identifiers — validate identifier fields by format instead of redacting them (score 7)

Two causes, found one after the other.

1. `harness/claude.yml` listed the pipeline's own push, branch and worktree calls in
   `exec.allow_extra`, which spells prefix rules. `exec_adapter.vet_extra` refused an extra only
   when it literally matched a deny form, so it never asked whether a deny's flags could follow
   the allow. LESSON-716 describes this: a validator must evaluate the way the real reader does,
   and Claude's `:*` admits anything after it.
2. Every launch except the close-out passed no settings isolation, and the close-out's isolation
   kept user settings (`--setting-sources user`). So `claude -p` merged the engine's flags with the
   operator's `~/.claude/settings.json` and the project's `.claude/settings.json`, both of which
   allow `Bash(git push:*)`. After cause 1 was fixed, a rerun still pushed `main`.

## Resolution

- The push, `git branch` and `git worktree` entries moved to `exec.allow_extra_exact`, which now
  substitutes `{branch}`.
- `vet_extra` refuses a prefix extra that shares a command base with a deny. That covers an
  operator's `sprint.exec.allow_extra` too.
- `config_isolation` is `--setting-sources "" --settings <runDir>/settings.json
  --strict-mcp-config`, and every launch passes it, not only the close-out. The loader accepts the
  empty value.
- Preflight refuses when `<binary> --help` lacks the isolation flags.
- REQ-659's BR-25 and AC-37 are amended. ASSUME-020, 021 and 023 are validated, ASSUME-022 is
  invalidated.

Tests: `test_prefix_extra_sharing_a_deny_base_is_refused` and the exact-push assertions failed
before the fix and pass after. `test_launch_refused_without_config_isolation` is new, and the
launch test checks the isolation flags and the settings file. Live:
`tools/adlc/tests/e2e/claude-exec-live.sh` pushed `main` and force-pushed before, and after the
fix denied both with the origin unchanged.

## Files Changed

- `harness/claude.yml`, `tools/adlc/exec_adapter.py`, `tools/adlc/harness_adapter.py`,
  `tools/adlc/sprint_exec.py`: the fix.
- `tools/adlc/tests/test_exec_adapter.py`, `test_exec_launch.py`, `test_exec_approve.py`: tests.
- `tools/adlc/tests/e2e/claude-exec-live.sh`: the logged-in rows, new.
- `.adlc/research/harness-probes/claude-exec-manual.md`: the results.
- `.adlc/specs/REQ-659-sprint-exec-engine/requirement.md`, ASSUME-020 to ASSUME-023, LESSON-796.
- `README.md`, `tools/adlc/README.md`, `CHANGELOG.md`.

## Deployment

None: the toolkit has no deploy targets.
