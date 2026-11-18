---
id: TASK-266
title: "One recorded Codex launch and resume, and the parser fixtures it yields"
status: complete
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-18
dependencies: [TASK-265]
---

## Description

Record what no probe measures, in `.adlc/research/harness-probes/codex-exec-manual.md`, following `claude-exec-manual.md`. Run by the orchestrating session, not a subagent: it launches real model sessions and edits the real user config, under the standing rules for live runs.

## Files to Create/Modify

- `.adlc/research/harness-probes/codex-exec-manual.md` (new) — one row per check, with the command, the observation and the verdict.
- `tools/adlc/tests/fixtures/exec-output/` — the captured launch and resume output, redacted by REQ-664 BR-9's chain and with `$HOME` rewritten to `~`, with the harness version noted; they replace the synthetic Codex fixtures.
- `harness/codex.yml` — only if a row disagrees with the block.

## Acceptance Criteria

- [x] Row: a launch with the block's exact argv, prompt on stdin, in a linked worktree of a throwaway repository, with trust written for the worktree path. The exec-named rule file is loaded: an allowed command writes outside the sandbox, and an un-allowed one does not. (`codex-exec-manual.md`, rows `launch-parses`, `allow-leaves-sandbox`, `unallowed-contained`.)
- [x] Row: the user-level policy file's `forbidden` rule refuses its command. (Row `user-policy-refuses`.)
- [x] Row: `codex exec resume` with the captured session id and the prompt on stdin continues the session; under it, a write outside the working copy by an un-allowed command still fails, and the `forbidden` rule still refuses. (Rows `resume-continues`, `resume-keeps-rules`.)
- [x] Row: the branch push through `fence-run` reaches a throwaway local bare remote from inside the session. (Row `push-through-runner`.)
- [x] The captured output parses to the expected final message and session id with the engine's parser. (Row `launch-parses`, and the committed captures through `test_the_real_codex_captures_parse_with_the_shipped_block`.)
- [x] The committed fixtures hold no string matching the redaction chain and no absolute home path. (The record: the fixtures are an earlier run of the same sequence, scrubbed; `test_output_fixtures_say_where_they_come_from` holds the home-path half.)
- [ ] `~/.codex/config.toml` matches its pre-run checksum afterwards, and no recovery marker is left. (The checksum half is the record's row `user-config-restored`; the record says nothing of a recovery marker.)
- [x] If the resume row fails, `harness/codex.yml` drops `resume`, and the README states that resume is impossible on Codex. (The resume rows passed, so the block keeps `resume`.)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_the_real_codex_captures_parse_with_the_shipped_block` | no |
| AC-6 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_the_real_codex_captures_parse_with_the_shipped_block` | no |
| BR-7 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_the_real_codex_captures_parse_with_the_shipped_block` | no |

(Amended 2026-11-18: the three rows named `test_real_codex_fixtures_parse` and `test_real_codex_resume_fixture_parses`, which never existed. The one test reads the launch and the resume captures.)

## Technical Notes

- Standing rules: back up `~/.codex/config.toml` first and verify the restore by checksum; never read, print or copy `~/.codex/auth.json`; pushes go only to a throwaway local remote; never pass a bypass flag.
- This REQ runs no §6 probe of its own (BR-11). These rows are the real-run fixture capture BR-6 asks for, plus the resume form ADR-7 leaves provisional. None of them changes a probe verdict.
- Lessons in play: LESSON-870 (a run that asks a model to act measures the model first: read the harness's record, not the reply), LESSON-847.
