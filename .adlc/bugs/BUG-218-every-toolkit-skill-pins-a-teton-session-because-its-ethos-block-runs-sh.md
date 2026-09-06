---
id: BUG-218
title: "Every toolkit skill pins a Teton Code session to the local tier, because its ethos block runs the partial under sh"
status: resolved
severity: medium
created: 2026-09-06
updated: 2026-09-06
resolved: 2026-09-06
component: "adlc/skills"
domain: "skills"
stack: ["markdown", "sh"]
concerns: ["developer-experience", "privacy"]
tags: ["ethos", "preamble", "sh", "provenance", "teton-code", "req-614", "req-619", "bug-214"]
introduced_by: ["REQ-416"]
attribution: manual
---

## Description

Every skill's `## Ethos` block is the preamble
`` !`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh` ``.
Teton Code classifies what a skill preamble could have read before it runs it
(REQ-614's shell grammar, applied to preambles by REQ-619), and `sh <file>` is
opaque **by verb**: the daemon cannot know what a script reads without running
it, so the expansion is recorded as unknown provenance and the session is pinned
to the local tier. Before teton-code's BUG-214 that pin was permanent and silent;
since REQ-619 it is announced and liftable with `/shell allow` — but it still
happens on every typed toolkit skill, and it was the 2026-09-04 "weird boundary
error" a user hit typing `/analyze` with transcription on.

## Reproduction Steps

1. Teton Code with a remote provider routed for `build`, any project.
2. Type any toolkit skill, e.g. `/analyze`.
3. The session prints `session pinned … unknown_shell` and every later turn runs
   locally until `/shell allow`.

## Expected Behavior

Reading the project's vendored `ETHOS.md` is provably in reach and pins nothing.

## Actual Behavior

The read is wrapped in an interpreter, and an interpreter's reach is the whole
machine.

## Environment

- Teton Code 0.1.31+; any consumer project.

## Root Cause

REQ-416 factored the ethos text into an executable partial and standardised the
`sh <local> || sh <canonical>` macro form for invoking partials (REQ-610's lint
even pins that form as benign). The partial only `cat`s a file with an
empty-file guard; the interpreter was there for the guard, not for anything a
classifier would need to run.

## Resolution

The block becomes
`` !`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo "No ethos found — run /init …"` ``
in all seventeen skills: the REQ-416 H1 fallthrough on an empty project copy
kept, no interpreter, and no path outside the session root — a first draft kept
`cat ~/.claude/skills/ETHOS.md` as the fallback and Teton Code's classifier
refused it as unprovable, which is the correct answer for a file the daemon
cannot see. `/init` vendors `.adlc/ETHOS.md` and `/template-drift` keeps it
current, so the toolkit-copy fallback only ever served an uninitialised project. `partials/ethos-include.sh` and its tests stay for
vendored skill copies that predate the line. `conventions.md` and
`partials/README.md` record why a text-only partial should be `cat`'d at the
call site. Teton Code's classifier learns `test` as a name-only verb in the same
change set (teton-code side).

## Deployment

- Merged as 31cd83f (PR #168), 2026-09-06. Consumers pick it up on their next toolkit sync; the daemon side (`test` as a name-only verb) is teton-code PR #308.

## Files Changed

- `*/SKILL.md` (17) — the ethos block
- `.adlc/context/conventions.md`, `partials/README.md`, `CHANGELOG.md` — the rule and why
