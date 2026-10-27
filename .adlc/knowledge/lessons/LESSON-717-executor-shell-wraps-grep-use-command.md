---
id: LESSON-717
title: "The executor shell can replace a coreutil with a function whose exit codes differ — a partial that branches on grep's status must call command grep, and the dogfood must run in that shell"
component: "adlc/partials"
domain: "adlc"
stack: ["sh", "zsh", "claude-code"]
concerns: ["correctness", "portability", "silent-failure", "testing"]
tags: ["executor-shell", "grep", "shell-function", "command", "exit-status", "lesson-check", "dogfood", "REQ-646"]
req: REQ-646
created: 2026-10-27
updated: 2026-10-27
kind: "domain"
evidence: "First real /wrapup run of REQ-646 (PR #189 at 0310579): adlc_lesson_check rejected the template default supersedes: [] with rc 1 under the Claude Code Bash tool, while zsh -c, bash -c and sh -c sourcing the same partial returned 0; the tool's shell snapshot defines grep as a function routed to its own matcher, whose -vq returns 0 on empty input where grep returns 1; fixed by command grep in partials/lesson-check.sh and pinned by partials/tests/lesson-check.test.sh executor_grep_wrapper_keeps_accept"
confidence: "high"
enforcement: "test:partials/tests/lesson-check.test.sh"
generalizes: [LESSON-329, LESSON-405]
supersedes: []
---

## What Happened

`adlc_lesson_check` passed 197 harness cases under bash, zsh, `/bin/sh` and dash,
then failed on the very first lesson a real `/wrapup` wrote: `supersedes: []` —
the template's own default — came back `every entry must be a LESSON-nnn id`.
`_alc_ids_ok` decides "all entries valid" by piping the entries through
`grep -v '^$' | grep -vqE '^LESSON-[0-9]{3,6}$'` and reading the exit status: real
grep exits 1 when no line is selected, so an empty list passes. In the Claude
Code Bash tool, `grep` is not `/usr/bin/grep`: the session's shell snapshot
defines `grep()` as a function that routes most invocations to the CLI's own
matcher, and that matcher exits 0 on empty input. The pipeline's status flipped,
and every template-based lesson would have been rejected in production while the
harness — run under non-interactive shells that resolve the real binary — stayed
green. `whence -f grep` in the executor shell showed the function; `zsh -c`,
`bash -c` and `sh -c` sourcing the identical partial returned 0 for `[]`.

The fix is one word at sixteen sites: `LC_ALL=C command grep …`. `command`
bypasses functions and aliases in sh, bash, zsh and dash, and the toolkit already
uses it for `$ADLC_READ_BIN` for the same reason. A harness case now defines an
always-0 `grep` wrapper around the call and asserts both verdicts are unchanged.

## Lesson

1. **Treat every coreutil name as a variable the executor may rebind.** A shell
   function or alias with the same name wins over `$PATH`, and a wrapper that
   preserves output can still change exit status, option parsing or stdin
   handling. In a partial that *branches on a tool's exit code* — `grep -q`,
   `grep -c`, `diff`, `cmp` — call it as `command <tool>`.
2. **Run the dogfood in the shell that will run the fence, not only in the
   matrix.** LESSON-329 and LESSON-405 put the harness under bash/zsh/sh/dash;
   that matrix cannot see a function the *interactive* executor injects from a
   profile or snapshot. One real invocation from the tool caught what four
   shells could not. REQ-646's AC-9 (a `/wrapup` through the new fence) was the
   right acceptance test, and deferring it to the REQ's own wrap-up was still
   early enough.
3. **Pin the wrapper, not the shell.** The regression test defines the
   misbehaving function in a subshell around the call; it needs no particular
   executor to reproduce the failure and will fail the moment a `command` prefix
   is dropped.

## Why It Matters

The guard existed precisely so a lesson could not be committed unchecked. An
exit-status flip inverted it into a guard that rejects every valid lesson, which
the repair loop would have turned into `NO_ENTRY` after two wasted retries — a
silent loss of every lesson, with a green harness. The same class waits in any
partial that pipes through `grep -q` under the executor: audit them.

## Applies When

- Writing or reviewing a `partials/*.sh` that reads a coreutil's exit status
  (`grep -q`, `grep -c`, `cmp -s`, `diff -q`, `test`-like wrappers).
- A harness is green under every shell in `run.sh` but a skill fence fails in
  the Claude Code Bash tool — check `whence -f <tool>` / `type <tool>` there.
- Adding a tool to a fence that must behave identically under an unknown
  profile: prefer `command <tool>` and an absolute `LC_ALL=C`.
