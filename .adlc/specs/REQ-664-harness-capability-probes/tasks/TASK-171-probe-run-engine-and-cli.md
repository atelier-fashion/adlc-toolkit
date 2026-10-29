---
id: TASK-171
title: "Probe run engine, user-file contract, launcher and CLI"
status: draft
parent: REQ-664
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-170]
repo: adlc-toolkit
---

## Description

Add the side-effecting half of `harness_probe.py` and wire it into
`adlc harness probe`: the ProbeRun (validated `mkdtemp`, repo, bare `origin`,
linked `wt`, cleanup, `--keep`), the user-file contract (backup, recovery marker,
atomic edit, checksum-verified restore, surgical restore, `--recover`), codex's
`allow_required_path` (ADR-4), the per-launch state reset and absent-before
assertion (ADR-9), the launcher (cap, own session, process-group kill, stdin from
a file), each probe's set-up writer and oracle, the result file (atomic write,
redaction, `~` rewrite, capped tails, `--only` merge, stderr `result_written`
line), events on stderr, signal handling, and exit codes. `harness.py` gains the
`probe` verb and builds `Deps`.

## Files to Create/Modify

- `tools/adlc/harness_probe.py` — engine, probes, oracles, CLI `main(argv, deps)`
- `tools/adlc/harness.py` — `probe` verb dispatch, `Deps` construction
- `tools/adlc/adlc.py` — `harness` help string names `probe`

## Acceptance Criteria

- [ ] `--list`, `--dry-run` and `--recover` launch nothing; `--dry-run` and `--list` work outside a git repo and write nothing
- [ ] an unknown name, an unknown `--only` id, a cap under 180 s with `shell-timeout` selected, and an absent binary exit 2 before anything is created
- [ ] the run directory is validated before removal and removed on success and failure
- [ ] a user file is backed up and the marker written before the edit; restore is verified by checksum; a changed file is restored surgically with exit 1
- [ ] a marker present at start refuses with exit 1 naming `--recover`
- [ ] a launch past its cap records `unknown / timeout` and leaves no child alive
- [ ] the result file carries every ResultFile field and is written atomically

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_harness_probe_cli.py::test_usage_errors_create_nothing` | yes |
| BR-3 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_cleanup_leaves_home_and_temp_unchanged` | no |
| BR-4 | test-case | `tools/adlc/tests/test_harness_probe_recovery.py::test_trust_file_backup_and_restore` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_hang_times_out_without_children` | no |
| BR-9 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_redaction_and_home_rewrite` | no |
| BR-10 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_transcript_fixture_redacted` | no |
| BR-11 | test-case | `tools/adlc/tests/test_harness_probe_recovery.py::test_marker_refuses_then_recover` | yes |
| BR-12 | test-case | `tools/adlc/tests/test_harness_probe_cli.py::test_launch_count_precedes_first_launch` | no |
| BR-16 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_fresh_state_per_launch` | yes |

## Technical Notes

Every recursive removal goes through one guard function next to the deletion
(LESSON-619): realpath, non-empty, absolute, under the expected root, basename
with the probe's prefix. Captures are written to files, not pipes, so a harness
never blocks on output. Signals SIGINT/SIGTERM/SIGHUP raise `_Interrupted`, whose
`finally` path restores. The claude profile passes `--setting-sources
project,local` (ADR-7). Lines naming `~/.claude/projects` carry
`# adlc-home: claude-code`.
