---
id: BUG-228
title: "The delegation steps pin a Teton Code session and time out its shell call, killing the turn"
status: in-review
severity: high
created: 2026-09-26
updated: 2026-09-26
component: "adlc/delegation"
domain: "skills"
stack: ["markdown", "sh"]
concerns: ["privacy", "developer-experience"]
tags: ["teton-code", "delegation", "adlc-read", "shell-provenance", "session-pinned", "timeout", "analyze", "req-614"]
introduced_by: []
attribution: none
---

## Description

In Teton Code, `/analyze` Step 1.5 (the optional `adlc-read` project-shape
pre-read) kills the whole turn in two ways at once.

1. **Timeout.** The model ran the step as one `shell` call: it sourced
   `delegate-tools-path.sh` and `delegate-gate.sh`, ran `skill-flag.sh`
   create/mark, then called
   `command "$ADLC_READ_BIN" --no-warn --paths README.md .adlc/context/*.md Cargo.toml --question …`.
   Teton's `shell` tool has a 30 s default timeout
   (`crates/tetond/src/harness/tools/shell.rs` `DEFAULT_TIMEOUT_MS`; it accepts
   `timeout_ms` up to 120000). The delegate call took longer, and the result
   was `ERROR: command timed out after 30000ms and was killed`.
2. **Pin.** The same command classified `unknown_shell` ("the command uses a
   quoted string this classifier does not model"). That pinned the session to
   the local tier (21,162-token budget) mid-turn, the loaded `/analyze` context
   no longer fit, and the turn was refused. Teton's BUG-227 fixed only the
   refusal's wording.

The same gate pattern appears in `/analyze` Step 1.6, `/proceed` Phase 5's
verify pre-pass, `/spec` (intake source-read and retrieval body-read) and
`/wrapup` (lesson drafting).

## Reproduction Steps

1. In a Teton Code session rooted at a project with delegation enabled
   (`adlc-read --version` reports enabled), run `/analyze`.
2. The model runs Step 1.5's blocks through `shell`.

## Expected Behavior

The pre-read either runs or falls back to reading the shape files directly,
and the turn stays on the remote route.

## Actual Behavior

The `shell` call times out at 30 s, a `session_pinned` event
(`cause: unknown_shell`) follows, and the turn is refused on the local tier.

## Environment

- Platform: macOS, Teton Code v0.1.36 (teton-code `main` at `4aede48`)
- Session: `sess-9vzd1rrt83hysatbr473chkwbg`, 2026-09-25, transcript
  `~/Library/Application Support/teton/transcripts/20260925T123118Z-sess-9vzd1rrt83hysatbr473chkwbg.jsonl`
  (records 172–178)

## Root Cause

**Pin: no spelling of these blocks can pass Teton's classifier, so rewording
them cannot fix it.** `shell_provenance.rs` is an allowlist grammar (ADR-614-1):
a command is `Rooted` only when every segment's verb is on `READS_NOTHING`,
`NAME_ONLY`, `READS_CONTENT` or `GIT_NAME_ONLY`, and everything else falls
through to `Unknown`. Every block in a delegating step fails at least one of
these rules, and most fail several:

- `adlc-read` (by name or through `$ADLC_READ_BIN`) is not a recognised verb:
  "the command's verb is not one this classifier recognises".
- `.adlc/partials/<x>.sh` or `"$DELEGATE_TOOLS"/skill-flag.sh` run by path:
  "the command names its program by path". REQ-619 H2 made this `Unknown` on
  purpose, because a repo-local executable's reach is whatever its unread
  contents do. So the "move the sequence into one vendored in-root script"
  option pins exactly the same way.
- `sh <script>` and `.`/`source` are in `OPAQUE` (or unrecognised).
- `$`, quotes, `{`, `*` are all in `UNMODELLED` and refuse the whole command
  before any verb is looked at.
- `ADLC_DELEGATE_ENABLED=1 …` style assignments: "the command sets an
  environment variable".

That is the correct answer, not a gap. `adlc-read` reads files and sends their
bytes to a third-party endpoint, and the classifier's only question is whether
a command could have read a file the session must not send remotely. Teton also
exposes no marker to shell children: `child_env.rs` composes an allowlisted
environment (`PATH`, `HOME`, `TMPDIR`, locale, …), every `TETON_*` name is a
test seam, and reading a variable would need `$` anyway. The same allowlist
withholds `ADLC_DELEGATE_*` and the delegate's API-key variable from the child,
so even a pinned, unbounded call would be running without the environment
`adlc-read` normally resolves from. On a provenance-classifying harness, the
only pin-free outcome is to not run the step's shell blocks, which means taking
the fallback path, which reads through the harness's own provenance-aware file
tool.

The skills gave the model no such instruction. Each step read as
harness-agnostic, and the model (reasonably) collapsed gate, telemetry and
invocation into one `shell` call.

**Timeout: the invocation carried no timeout guidance.** Claude Code's Bash
tool defaults to 120 s, which is why this never showed there. A harness with a
shorter default kills the delegate mid-flight. On Teton the skip above removes
the call entirely, but any other harness with a short default still needs to
be told.

Blame over the gate blocks returns REQ-414, 416, 417, 424, 515, 522 and 610.
None of them introduced this: the failure is an interaction with Teton's later
REQ-614/619 classifier, so no `introduced_by` is recorded.

## Resolution

Every delegating step now carries one line, word for word the same,
immediately before its "Before the gate check" block:
`**Provenance-classifying harness (BUG-228):**`. On a harness whose shell tool
classifies reach and pins on `Unknown` (Teton Code), it tells the model to run
none of the step's shell blocks (telemetry, gate, `adlc-read`). The model takes
the fallback path with the harness's own file-read tool, which is
provenance-aware, and reports the skip in its reply rather than on stderr. The
line is at `/analyze` Steps 1.5 and 1.6, `/proceed` Phase 5's verify pre-pass,
`/spec`'s intake source-read and retrieval body-read, and `/wrapup`'s lesson
drafting.

Options weighed and rejected:

- **A vendored in-root wrapper script run with plain args.** It is still a
  program named by path, which REQ-619 H2 made `Unknown` on purpose, so it pins
  the same way.
- **Detecting Teton from a script.** Shell children get an allowlisted
  environment, so there is no marker to read, and `$` is unmodelled anyway.
- **Asking Teton to recognise `adlc-read`.** It reads files and sends them to a
  third party, which is exactly what the classifier exists to refuse.

The timeout disappears on Teton because the call no longer runs there. For any
other harness, `partials/delegate-gate.md` and `conventions.md` now say to give
the `adlc-read` call a shell timeout of at least 120 s.

Telemetry: on Claude Code and every other unclassified harness the
REQ-424/REQ-522 flag-file contract is unchanged. On a provenance-classifying
harness the skipped step writes no telemetry record, because every
`skill-flag.sh`/`emit-step-telemetry.sh` call is a by-path program and would
pin. The cross-fence-fn structure is untouched: no fence was merged or split.

A new `lint-skills` check, `harness-skip`, enforces the line. Every fence that
calls `adlc_delegate_gate_check` needs it on a prose line within the 30 lines
above. A copy inside a fence doesn't count, and a commented-out call is not a
call. The check was shown to fail by deleting the line from `/analyze`:
exactly one finding, at `analyze/SKILL.md:54`.

`agents/delegate-pre-pass.md` is left alone. It is dispatched only by
`/sprint --workflow` through Claude Code's Workflow runtime, which Teton does
not host.

## Files Changed

- `analyze/SKILL.md`, `proceed/SKILL.md`, `spec/SKILL.md`, `wrapup/SKILL.md`: the harness-skip line at each of the six delegating steps
- `partials/delegate-gate.md`: new "Provenance-classifying harnesses (BUG-228)" section, covering why no spelling passes, the skip rule, the telemetry consequence and the timeout guidance
- `.adlc/context/conventions.md`: the rule, stated in the Delegation pattern section
- `tools/lint-skills/check.py`: `check_harness_skip` (`harness-skip`)
- `tools/lint-skills/README.md`: check 10
- `tools/lint-skills/tests/test_check.py` and `tests/fixtures/harness-skip-{ok,missing,in-fence,too-far}.md`: a clean case plus three cases that must fire
- `tools/lint-skills/tests/fixtures/{canonical-via-partial-skill,delegate-gate-ok,missing-resolver-source}.md`: the line added so these fixtures keep testing only what they were written for
