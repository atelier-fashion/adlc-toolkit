# Partials

This directory holds shared shell snippets that are referenced from multiple
SKILL.md files. Each partial is a small, self-contained POSIX shell script
(`#!/bin/sh`, no bashisms). Keeping these snippets in one place ensures that
updates land everywhere consistently and that each SKILL.md stays focused on
its own instructions rather than re-implementing shared boilerplate.

## Two invocation models

Partials come in two flavors. **Don't mix them up** — the calling convention
differs and so does what kind of partial you should add.

### 1. Executable partial (emits text to stdout)

The partial is a script Claude Code's `!`...`` macro runs and substitutes its
stdout into the skill prompt. Example: `ethos-include.sh` reads `ETHOS.md` and
prints it. Skills invoke it like:

```
!`sh .adlc/partials/<name>.sh 2>/dev/null || sh ~/.claude/skills/partials/<name>.sh`
```

The consumer-project-first fallback works whether or not `/init` has been run
in the consumer repo.

### 2. Sourceable partial (defines a function)

The partial defines a shell function and is sourced (with `.`, the POSIX
equivalent of `source`) into the calling skill's bash block. The function is
then called and its return code or exported variables drive the skill's
behavior. Example: `kimi-gate.sh` defines `adlc_kimi_gate_check` returning
0/1/2. Skills invoke it like:

```bash
. .adlc/partials/<name>.sh 2>/dev/null || . ~/.claude/skills/partials/<name>.sh
adlc_<name>_function; result=$?
```

Capture `$?` immediately — every subsequent command clobbers it.

## When does a partial need a companion `.md`?

Add a `<name>.md` alongside the `<name>.sh` when the partial has a public
contract that callers must honor (a return-code registry, an exported-variable
schema, an emit-format spec, or any "must do this when calling me" rule). Pure
text-emitting partials like `ethos-include.sh` don't need one — `cat ETHOS.md`
is its own contract. Function-exporting partials almost always need one,
because the call-site protocol is non-obvious. `kimi-gate.md` is the canonical
example.

## Adding a new partial

- Keep partials POSIX-only (no bashisms, no GNU-specific flags).
- Add new partials sparingly — each one is a shared dependency that touches
  multiple skills. Avoid an aggregator file (`lib.sh`) until there are more
  than five partials; that's YAGNI today.
- Update `/init` if the partial needs to be copied into consumer projects'
  `.adlc/partials/` (the existing `partials/*.sh` copy step covers that).
- Update `/template-drift` if the partial is one consumer projects might
  customize and you want drift detection (TODO: as of REQ-416, drift detection
  for `partials/` is a known follow-up — not yet implemented).
