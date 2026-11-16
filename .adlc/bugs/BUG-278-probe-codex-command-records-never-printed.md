---
id: BUG-278
title: "`adlc harness probe codex` can never record a refusal: it launches codex without `--json`, so the `command_execution` records the runner-prefix oracle reads are never printed"
status: open
severity: medium
created: 2026-11-16
updated: 2026-11-16
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness"]
tags: ["harness-probe", "codex", "runner-prefix", "fake-harness", "live-run", "json"]
introduced_by: ["REQ-707"]
attribution: derived
---

## Description

On 2026-11-16 the first full codex probe since REQ-707 (`adlc harness probe codex`,
codex-cli 0.166.0, `main` at `7e13e98`) ran all 31 launches. All 13 `runner-prefix`
launches read `unknown`, so the variant was `unknown`.

REQ-707 counts a control as `refused` only when the asked line is in a `command` field of
the harness's own JSON tool-call or denial records (LESSON-847). For codex those are the
`command_execution` items of `codex exec --json`. The probe launches
`codex exec --sandbox workspace-write -C <repo> -o <lastmsg> <prompt>` with no `--json`, so
stdout is the final message in plain text (9 bytes on the witness-present launches) and the
transcript on stderr is plain text too. No `command_execution` record ever reaches
`record_commands`, so every codex launch reports `asked line on record: no`.

The result was discarded unrecorded and saved outside the repo for reference.

## Reproduction Steps

1. `adlc harness probe codex --only fence-vs-allowlist` on codex-cli 0.166.0.
2. Every `runner-*` `oracle_checked` line ends `asked line on record: no`, including the five
   launches whose witness ran (`runner-sibling`, `-backtick`, `-redirect`, `-pipe`,
   `-newline`), and each one's `evidence.command` has no `--json`.

## Expected Behavior

A codex launch prints the records the oracle reads, so a refused control can read
`refused` and `runner-prefix` can be decided on codex.

## Actual Behavior

No codex control can read `refused`: the best a codex launch can reach is `unknown`, so
`runner-prefix` can only be `unknown` or `fail` there.

## Environment

- codex-cli 0.166.0, macOS, toolkit `main` at `7e13e98`.

## Root Cause

Prior lessons consulted:
- LESSON-854 — A harness's trust gate can drop a project's allows while still loading its hooks
- LESSON-782 — Do not commit a test that says a file is unchanged against origin/main
- LESSON-868 — Measure a deny rule's spelling against the harness, and model a deny only where it was seen to refuse
- LESSON-844 — A tool rule with no path in it admits every path
- LESSON-847 — A probe reads `refused` only with proof the command was submitted, taken from the harness's tool-record fields and never from model text

`Runner._observe_runner` (`tools/adlc/harness_probe.py`) reads
`record_commands(res.stdout) + record_commands(res.stderr)`, and the README names codex's
record shape as `command_execution` items. `Runner._argv` builds codex's command line
without `--json`, which is the only mode in which codex prints those items. REQ-664 built
that line when nothing read codex's stdout (the final message comes from `-o`), and
REQ-707 started reading records from stdout without adding the flag.

The suite could not see it: the fake codex printed JSONL `command_execution` events whatever
its flags, so on the fake every codex refusal was on record. LESSON-847 is the rule this
breaks in practice: the proof of submission must come from the harness's record fields, and
here the harness was never asked to print them.

Attribution: REQ-707, derived from blame of the record reader in `_observe_runner`. The codex
command line itself blames to a commit with no REQ trailer.

A second, separate cause, not fixed here: in 7 of the 13 launches the model (codex's default,
with reasoning effort `none`) declined to run the commands at all, saying they wrote outside
the workspace, although the run's allow rules would have admitted them. The probe reads those
as `unknown / not-attempted` or `precondition-unmet: config witness absent`, which is correct.
They may keep the variant `unknown` after this fix.

## Resolution

Codex now launches as `codex exec --json --sandbox workspace-write -C <repo> -o <lastmsg>`.
Its `command_execution` records reach `record_commands` on stdout, and the final message is
still read from `-o`, so no other oracle changes. The fake codex now prints JSONL only under
`--json` and plain text otherwise, as codex-cli 0.166.0 does.

## Files Changed

- `tools/adlc/harness_probe.py`: `_argv` passes `--json` to codex.
- `tools/adlc/tests/fake_harness/fake_harness_impl.py`: the fake codex accepts `--json`, and
  prints its JSONL events only under it.
- `tools/adlc/tests/test_harness_probe_e2e.py`: `test_codex_command_records_reach_the_probe`.
- `tools/adlc/README.md` (the record-shape paragraph), `CHANGELOG.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

A failing-first test was still written:
`tools/adlc/tests/test_harness_probe_e2e.py::test_codex_command_records_reach_the_probe`.
With the corrected fake and without the fix it fails (`runner-prefix` reads `unknown`, and
the launch has no `--json`), as does the existing
`test_runner_prefix_per_statement_passes[codex]`; with the fix both pass.
