---
id: BUG-267
title: "`adlc harness probe claude` has never measured an allow: its allows go in the probe repo's `.claude/settings.json`, which an untrusted workspace ignores"
status: resolved
severity: medium
created: 2026-11-10
updated: 2026-11-10
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness"]
tags: ["harness-probe", "claude-code", "trust", "allowlist", "settings", "live-run", "fake-harness"]
introduced_by: ["REQ-664"]
attribution: derived
---

## Description

On 2026-11-10 the first live run of REQ-707's `runner-prefix` variant
(`adlc harness probe claude --only fence-vs-allowlist`, claude 2.1.316) ran all
16 launches and measured nothing. Every launch printed:

> Ignoring 43 permissions.allow entries from .claude/settings.json: this workspace has not been trusted.

The probe's claude profile says `trust="none"` and writes each launch's allow and
deny rules into the throwaway repo's `.claude/settings.json`. Claude 2.1.316 drops a
project's `permissions.allow` until the folder is trusted, so no allow was in force:
even the exactly-allowed `touch <witness>` every launch runs first was refused.

- The 13 `runner-prefix` launches read `unknown` (mostly
  `precondition-unmet: config witness absent`). REQ-707's witness rule worked, and no
  `pass` came out of a run that measured nothing.
- `routine-only`, `broad-sh` and `broad-first-token` read `fail`. REQ-664's rule for
  them has no witness, so "nothing allowed" looks like "the allow refused the fence".
- Every other probe that relies on a project allow on claude (`git-write-main`,
  `git-write-worktree`, `ask-tier-deny`, `shell-timeout`, `stdin-prompt`,
  `arg-substitution`) is affected the same way.

The gate is not new. The committed `.adlc/research/harness-probes/claude.json`
(2.1.258, `fbbc1ce`) carries the same "has not been trusted" message on every
allow-dependent probe, and all of them read `unknown`. `tools/adlc/README.md` records
this as "the finding, not a probe fault", because the one workaround it weighed was
writing `~/.claude.json`, which a run may not edit. So no claude allow has ever been
measured by the probe. The 2026-11-10 result file was discarded unrecorded: it would
have replaced those 2.1.258 results with another run that measured nothing.

## Reproduction Steps

1. `adlc harness probe claude --only fence-vs-allowlist` on claude 2.1.316.
2. Every launch's stderr carries the "Ignoring … permissions.allow" line, and every
   `oracle_checked` line reports `witness: absent`.

Minimal form, in an untrusted scratch git repo, one launch with
`--setting-sources project,local --settings <file outside the repo>`:

| rule placed in | kind | outcome |
|---|---|---|
| project `.claude/settings.json` | allow `Bash(touch …/proj-allow)` | **refused** (in `permission_denials`) |
| project `.claude/settings.json` | SessionStart hook | ran |
| `--settings` file | allow `Bash(touch …/flag-allow)` | ran |
| `--settings` file | SessionStart hook | ran |

`~/.claude.json` held 322 project entries before and after, with no entry for the
scratch repo.

## Expected Behavior

Each launch's allow and deny rules are in force, so the probe measures the matcher
and not the trust dialog.

## Actual Behavior

No allow is in force on any launch, so every probe that needs one reads `fail` or
`unknown` for a reason unrelated to its question.

## Environment

- claude 2.1.316 (Claude Code), macOS, toolkit `main` at `db027ee`.

## Root Cause

Prior lessons consulted:
- LESSON-768 — A probe's fail names an outcome, not its cause: read what the launch actually ran before reading the verdict
- LESSON-844 — A tool rule with no path in it admits every path
- LESSON-847 — A probe reads `refused` only with proof the command was submitted

`Runner._write_config` (`tools/adlc/harness_probe.py`) writes claude's permissions
into `<repo>/.claude/settings.json` for every launch, and `_argv` launches claude with
`--setting-sources project,local` and no `--settings`. The profile's `trust="none"`
assumes no trust step, but claude (2.1.258 and 2.1.316 alike) gates a project's
allows on trust. Hooks are not gated, so `hooks-loaded` and `session-start-context`
were unaffected. A `--settings` file is not gated either, which REQ-664 did not
consider: it removes the need to edit `~/.claude.json` at all.

LESSON-768 describes this exactly: the three older `fence-vs-allowlist` variants'
`fail` named an outcome (sentinel absent), and the cause was in each launch's stderr.

The fix routes claude's permissions through a per-launch `--settings` file in the
run's captures directory, outside the repo, the way the antigravity profile already
does and the way `/sprint --exec` launches claude. One launch keeps the project file:
`trust-then-headless`'s `allowlist-loaded` asks whether a project-only allow loads
headlessly, so its allow stays project-local and now records the 2.1.316 answer
(`fail`) instead of being worked around. The profile's `trust` stays `none`: trusting
the probe repo would mean editing `~/.claude.json`, which open sessions write
concurrently, so a byte-for-byte restore could erase their writes.

Attribution: REQ-664, derived from blame of the claude config writer and launch argv
(`fbbc1ce`), which placed claude's allows in the one location the trust gate switches off.

## Resolution

Claude's permissions now travel in a per-launch `--settings` file in
`<run_dir>/captures/`, outside the probe repo, for every launch but
`trust-then-headless`. Hooks stay in the project's `.claude/settings.json`, which
loads untrusted. `trust-then-headless` keeps its project-file allow, because
`allowlist-loaded` asks whether a project-only allow loads, and on claude it now
records the real answer, `fail`. The profile's `trust` stays `none`, and no run edits
`~/.claude.json`.

Live rerun on 2026-11-10 (claude 2.1.316, `--only fence-vs-allowlist`, from this
branch): the witness was present on all 13 runner launches. `runner-positive` was
admitted, and the baseline and all 11 refusal controls were refused with the command
on record, so `runner-prefix` reads `pass`, reproducing REQ-682's rows 11 to 13. The
three older variants read `fail` with the allows in force: no allow admits the
sourcing fence on 2.1.316 (ASSUME-030). `~/.claude.json` held 322 project entries
before and after. The result file was not committed: it carries `main`'s commit as
`probe_tool_version`, and recording live results is its own change (REQ-707 BR-11).

## Files Changed

- `tools/adlc/harness_probe.py`: `_write_config` writes claude's permissions to
  `captures/<launch>.settings.json` and returns `--settings <path>`, except for
  `trust-then-headless`; `_argv` passes that to claude.
- `tools/adlc/tests/fake_harness/fake_harness_impl.py`: claude takes `--settings`, and
  a new `untrusted-project-allow` flag drops a project's allows the way 2.1.316 does.
- `tools/adlc/tests/test_harness_probe_e2e.py`:
  `test_claude_allows_survive_an_untrusted_project`.
- `tools/adlc/README.md` ("What a run touches"), `CHANGELOG.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

A failing-first test was still written:
`tools/adlc/tests/test_harness_probe_e2e.py::test_claude_allows_survive_an_untrusted_project`.
Without the fix it fails on `{'broad-first-token': 'fail'} != {'broad-first-token': 'pass'}`,
and with the fix it passes.

## Deployment

Merged as `89024ea` ([#261](https://github.com/atelier-fashion/adlc-toolkit/pull/261)) on
2026-11-10. Nothing to deploy, since this is toolkit code. The committed claude probe
result still holds the 2.1.258 run; a full run on the merged commit records 2.1.316.

## Lessons

- LESSON-854: a harness's trust gate can drop a project's allows while still loading
  its hooks.
