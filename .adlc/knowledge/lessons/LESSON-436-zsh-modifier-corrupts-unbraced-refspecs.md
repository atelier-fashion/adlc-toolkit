---
id: LESSON-436
title: "zsh history-modifier parsing corrupts unbraced git refspecs — $obj:refs/... silently mangles; always brace ${obj}:refs/..."
component: "adlc/skills"
domain: "adlc"
stack: ["zsh", "bash", "git"]
concerns: ["portability", "correctness", "silent-degradation"]
tags: ["refspec", "zsh-modifier", "shell-portability", "git-push", "lesson-335-class"]
req: REQ-546
created: 2026-07-23
updated: 2026-07-23
---

## What Happened

REQ-546's reservation push builds a refspec `<object>:refs/adlc/ids/<kind>/<n>`.
Written as a bare `$obj:refs/...`, zsh interprets the `:r` after the parameter
as its **history/parameter modifier** ("remove extension") rather than a
literal colon-r — the expansion silently mangled the refspec (the SHA got
concatenated with `efs/...`) and the push targeted garbage. sh and bash parse
the same text literally, so the bug was invisible under `bash -c` and lint,
and surfaced only when the fenced block was dogfooded under `zsh -c` (the real
executor shell). The fix is purely syntactic: brace the expansion —
`"${obj}:refs/adlc/ids/${kind}/${num}"`.

## Lesson

In zsh, `$var:` followed by a modifier letter (`:r`, `:h`, `:t`, `:e`, ...)
is an operator on the expansion, not a literal suffix. Any construct that
concatenates a variable directly with a colon — git refspecs (`src:dst`),
`scp`/rsync remotes, PATH-style joins, URL userinfo — must brace the
variable: `"${var}:..."`. This is a new member of the LESSON-335 hazard
class (zsh-executor divergences that pass lint and bash): the corruption
happens at expansion time, so no runtime test under the wrong shell can
catch it. Dogfooding under `zsh -c` (LESSON-329) remains the only reliable
detector; write the brace habit into any skill shell that builds refspecs.

## Why It Matters

A mangled refspec in the reservation push would have silently defeated the
collision-safety mechanism REQ-546 exists to provide — the push fails or
targets a wrong ref, allocation degrades or double-allocates, and nothing
looks wrong under bash-based review. Silent-under-review, broken-under-
executor is the most expensive portability shape.

## Applies When

- Writing or reviewing any skill/partial shell that constructs `src:dst`
  refspecs or any `$var:`-adjacent string.
- Extending the LESSON-335 lint/hazard list: bare `$var:` + modifier letter
  is grep-detectable (`\$[A-Za-z_][A-Za-z0-9_]*:[rhte]`).
