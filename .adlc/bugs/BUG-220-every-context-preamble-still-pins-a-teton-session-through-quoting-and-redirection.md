---
id: BUG-220
title: "Every skill's context preambles still pin a Teton Code session, because quoting, redirection and globs are outside the classifier's grammar"
status: resolved
severity: medium
created: 2026-09-09
updated: 2026-09-09
resolved: 2026-09-09
component: "adlc/skills"
domain: "skills"
stack: ["markdown", "sh"]
concerns: ["developer-experience", "privacy"]
tags: ["preamble", "provenance", "teton-code", "req-614", "req-619", "bug-218", "quoting", "redirection"]
introduced_by: ["REQ-416"]
attribution: manual
---

## Description

BUG-218 took the interpreter out of the ethos line. The line still pinned the
session — and so did every other `## Context` preamble in every skill — because
Teton Code's shell grammar (REQ-614, applied to preambles by REQ-619) rejects a
command **before it looks at the verb** when the command contains any of
`' " ` $ \ > < { } ! * ? [`. `|| echo "No ethos found — …"` has quotes;
`cat X 2>/dev/null` has a redirect; `.adlc/specs/*/requirement.md` has a glob;
`--format="…"` has both and an `=`. `test` becoming a name-only verb
(teton-code #308) never got a chance to apply.

Seen 2026-09-09 typing `/analyze` in teton-code: `session pinned … cause:
unknown_shell` on all three of the skill's preambles, then two more failures
underneath it (teton-code BUG-219: the local tier had been disabled by a failed
benchmark with no step-down, so the pinned session had nowhere to run).

## Reproduction Steps

1. Teton Code 0.1.32 with a remote provider routed for `build`.
2. Type `/analyze` (or any skill with a `## Context` block).
3. `privacy — this session is pinned to the local tier … cause: unknown_shell`,
   and `skill_invoked` reports every preamble's `reach` as `unknown` with the
   reason "the command uses shell syntax this classifier does not model".

## Expected Behavior

A preamble that reads a vendored file inside the project is provably in reach
and pins nothing.

## Actual Behavior

The verb is never examined; the quoting rejects the line whole.

## Environment

- Teton Code 0.1.32; any consumer project.

## Root Cause

The preambles were written for a host that runs them and reads their output.
Teton Code classifies them statically, and its grammar is deliberately a
non-lexer: quoting, redirection, substitution and expansion are rejected rather
than modelled, so a matcher never has to guess what `sh` will do. The idioms
that are second nature in a shell — `2>/dev/null`, a quoted message, a glob, a
`| head` — are exactly the ones that grammar refuses. Two further rules bit
independently: a `~/…` fallback in *any* segment makes the whole line
unprovable even when it never runs, and a content-reading verb with no file
argument (`| head -20`, `| grep -c .`) is scored as a read of the whole root,
a scan bounded by entry count that a Rust `target/` exhausts.

## Resolution

Every preamble in the seventeen skills is rewritten inside the grammar: no
quotes (`echo` takes its message bare — em dashes and slashes are fine, `(`,
`)` and `;` are not), no `2>/dev/null` (the host does not inline stderr), no
globs, no `~/` fallbacks (the template fallbacks to `~/.claude/skills/templates`
go the way the ethos one did — `/init` vendors `.adlc/templates`), and no pipes
into `head`/`tail`/`grep`. Specifically:

- `grep -rl 'a\|b' .adlc/specs/*/requirement.md | head -20` becomes
  `grep -rl -e status:.draft -e … --include requirement.md .adlc/specs`
  (`--include` with a space keeps `=` out; the dot matches the space; the scan
  is scoped to `.adlc/specs`).
- `git diff main --stat` (`diff` reads content, so it is not name-only) becomes
  `git diff-tree --stat -r main HEAD` plus a `git status --short` line for the
  uncommitted half.
- `git branch -r --list 'origin/feat/REQ-*' | grep -c .` becomes
  `git for-each-ref refs/remotes/origin/feat` (a prefix match, listed rather
  than counted); `command -v gh >/dev/null 2>&1` becomes `which gh`.
- sprint's `find … | while read …; do cat "$f"; done` becomes a bare
  `find .adlc/specs -name pipeline-state.json` and the skill reads each file.
- Teton Code learns `git worktree` and `git for-each-ref` as name-only verbs in
  the same change set (teton-code BUG-219's PR).

Two known exceptions remain and are documented in `conventions.md`:
`/canary`'s `gcloud` lines (an unrecognised verb, and a `--format` that cannot
be spelled inside the grammar) and `/template-drift`'s
`ls ~/.claude/skills/templates/` (its purpose is to read outside the root).
Those two skills pin a Teton session by design; `/shell allow` lifts it.

## Deployment

- Merged as 87312d1 (PR #170), 2026-09-09. LESSON-657. Consumers pick it up on their next toolkit sync; `~/.claude/skills` is a symlink to the toolkit checkout, so a local install sees it at once. The two new git verbs need teton-code ≥ the release carrying its BUG-219.

## Files Changed

- `*/SKILL.md` (17) — every `!`…`` preamble
- `.adlc/context/conventions.md` — the grammar every preamble stays inside
