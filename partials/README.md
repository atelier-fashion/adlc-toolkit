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
behavior. Examples:

- `delegate-gate.sh` — defines `adlc_delegate_gate_check` returning 0/1/2.
  Companion `delegate-gate.md` documents the return-code registry.
- `forge.sh` — the forge-neutral PR-operation adapter (REQ-520). Defines
  `adlc_forge_pr_{create,ready,edit,view,list,merge,comment}` plus
  `adlc_forge_provider` (GitHub/Azure DevOps, `auto` origin-URL detection). The
  single home of `gh`/`az` PR commands; skills never call `gh pr` ops directly
  (lint-enforced). Companion `forge.md` documents the op contract, the normalized
  result/error vocabulary, and the ADO REST-via-PAT fallback.
- `emit-step-telemetry.sh` — defines `_adlc_emit_step_telemetry` (the
  `/analyze` per-step telemetry resolve-and-emit). Companion
  `emit-step-telemetry.md` documents the caller-env contract and the
  call-site protocol: the source line and the `_adlc_emit_step_telemetry`
  call MUST live in the **same fenced block** (SKILL.md fenced blocks do not
  share shell state across steps), which is non-obvious enough to need the
  `.md` (the `delegate-gate.md` precedent). It **self-sources**
  `delegate-tools-path.sh`, so call sites do NOT separately source the
  `$DELEGATE_TOOLS` resolver — sourcing this one partial both resolves
  `$DELEGATE_TOOLS` and defines the function.
- `id-alloc.sh` — collision-safe id allocation with the **remote** as source of
  truth (REQ-518). Defines `adlc_alloc_id <kind>` (prints `max(local,remote)+1`
  and fast-forwards the local counter — which is a cache, not an authority),
  `adlc_remote_high <kind>` (the remote high-water, 0 if none/unreachable), and
  the kind mappers `adlc_id_kind_{counter,lockdir,prefix,scan}` /
  `adlc_id_list_max`. One helper parameterized by `kind` (req|bug|lesson)
  replaces the near-identical inline blocks in `/spec`, `/bugfix`, `/wrapup`.
  Allocation runs inside the existing `mkdir`-lock with its symlink/TOCTOU
  guards intact. The contract (same-fenced-block source-then-call, the
  subshell-`exit` guard) lives in the partial's header comment rather than a
  separate `.md`.
- `id-recheck.sh` — pre-push / PR-time id collision recheck (REQ-518 BR-4/BR-8).
  Defines `adlc_recheck_id <kind> <ID>` returning 0 (no collision on any
  reachable remote, OR degraded-unreachable — never invents a collision from
  absence of data), 1 (collision — prints the exact `adlc renumber` halt to
  stderr), or 2 (usage error). It is a separate partial from `id-alloc.sh` so
  recheck call sites don't load the full allocation machinery, but it sources
  `id-alloc.sh` for the kind mappers + `adlc_remote_high` (one derivation
  surface). Never blocks on the network. Contract in the header comment.

Skills invoke a model-2 partial like:

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
because the call-site protocol is non-obvious. `delegate-gate.md` is the
canonical example.

## Adding a new partial

- Keep partials POSIX-only (no bashisms, no GNU-specific flags).
- Add new partials sparingly — each one is a shared dependency that touches
  multiple skills. Avoid an aggregator file (`lib.sh`) until there are more
  than five partials; that's YAGNI today.
- Update `/init` if the partial needs to be copied into consumer projects'
  `.adlc/partials/` (the existing `partials/*.sh` copy step covers that).
- Update `/template-drift` if the partial is one consumer projects might
  customize and you want drift detection. Partial drift detection IS
  implemented: `/template-drift` Step 3 ("Detect Partial Drift") diffs each
  `~/.claude/skills/partials/*.sh` against the consumer's `.adlc/partials/`
  copy and classifies it `synced` / `stale` / `missing` (no
  intentional-customization escape hatch — any partial drift is reported as
  `stale` by design, since a modified gate/ethos partial is the threat model
  the check exists to catch).
