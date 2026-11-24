---
id: TASK-282
title: "Demo recording script and recording checks"
status: complete
parent: REQ-672
created: 2026-11-23
updated: 2026-11-23
dependencies: [TASK-281]
repo: adlc-toolkit
---

## Description

Write the script that regenerates the demo recording from a real quickstart run, and the
checks every recording must pass before it is committed (architecture ADR-6). No
recording is made by this task: a real one spends the maintainer's plan. The checks are
proven on fixture casts, and the script's refusal paths are proven without a model.

## Files to Create/Modify

- `tools/launch/recording_check.py` — length, size and content checks over a cast and an optional GIF, with a CLI
- `tools/launch/record_demo.py` — the regeneration script: tool and option preflight, `asciinema rec` of the e2e driver in `--demo` mode, cast post-processing, the checks, `agg`
- `tools/launch/tests/test_recording_check.py` — the checks over fixture casts built in the test
- `tools/launch/tests/test_record_demo.py` — post-processing and the refusal paths, with fake `asciinema` and `agg`

## Acceptance Criteria

- [x] A fixture cast inside every limit passes; a cast longer than 60 seconds fails; a GIF over 5 MB fails; a cast holding a `/Users/<name>/` path fails; a cast holding a name from `tools/dataset/denylist.json` fails; a cast holding a credential shape fails; a cast holding a `--forbid` string fails
- [x] The content checks read the cast's output events joined, so a path split across two events is still found
- [x] The check reports the cast's duration, its event count and the GIF's size, and fails on a cast with no output events
- [x] Post-processing caps idle gaps, scales the timestamps so the total is 60 seconds or less, keeps the events in order and replaces the given owner with `your-github-user`; a test shows a 400-second cast come out at or under 60 seconds with the same output text apart from that substitution
- [x] Without `asciinema` or `agg` on `PATH`, without `--with-model`, or without `--throwaway-repo`, the script records nothing, prints the reason and exits 2
- [x] With fake `asciinema` and `agg`, the script writes `docs/demo.cast` and `docs/demo.gif` only after the checks pass, and writes neither when a check fails; in tests the output directory is a temp directory
- [x] The GitHub login the script passes as `--forbid` is never printed
- [x] A test runs the checks over `docs/demo.cast` and `docs/demo.gif` when both exist, fails when only one exists, and passes with a notice when neither does

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-4 | test-case | `tools/launch/tests/test_record_demo.py::test_a_refusal_records_nothing` | yes |
| AC-5 | test-case | `tools/launch/tests/test_recording_check.py::test_limits_and_content_checks_on_fixture_casts` | yes |

Lessons: LESSON-581, LESSON-019, LESSON-899

## Technical Notes

- An asciinema v2 cast is a JSON header line (`version`, `width`, `height`, optional `duration`) followed by `[time, "o", data]` event lines. Take the duration from the last event's time, not from the header.
- Load the DenyList through `tools/dataset/denylist.py` and reuse `tools/adlc/credential_redact.find` for credential shapes; reach both by `sys.path` from this file's location. Match DenyList names case-insensitively as whole words, as the dataset's residue pass does.
- The home-path check covers `/Users/<name>/` and `/home/<name>/`. The sandbox the driver uses is under the system temp directory, so a correct recording has neither.
- `record_demo.py` passes `--with-model`, `--throwaway-repo` and `--demo` through to `tools/launch/quickstart_e2e.py`, and refuses the same way that driver does. It reads the login with `gh api user -q .login` only to forbid it, and holds it in memory only.
- Write the outputs through a temp file and `os.replace`, both or neither.
- No fixture cast is a file in the repository: build each in the test. Python 3.9, stdlib only.
- **No real binary may answer a test.** Every test that runs a script or driver builds `PATH` from the fake-binary directory plus `/usr/bin:/bin` only (`tools/adlc/tests/exec_helpers.py` `offline_path` is the precedent), and asserts from the fake's own log that the fake was what ran. A test must never reach a real `claude`, `gh`, `asciinema` or `agg`, nor the network.
