# `workflows/` — Dynamic Workflow scripts

This directory holds the deterministic **Workflow scripts** the toolkit's
workflow engine runs (the `adlc-sprint` engine and its supporting modules). A
Workflow script owns control flow — sequence, fan-out, loops, merge ordering —
and dispatches agents as leaves; it carries no business prose. See REQ-474
(`/sprint` two-engine re-platform) and the spec's ADR-2 / ADR-7.

## Contents

| File | Role |
|------|------|
| `adlc-sprint.workflow.js` | The `adlc-sprint` engine — control flow only (sequence, fan-out, loops, merge ordering); dispatches `agent()` leaves for all I/O. Runs only inside the Workflow runtime. |
| `schemas.js` | The JSON-Schema literals (`REPOS`, `VERDICT`, `TASKS`, `FINDINGS`, `CANDIDATES`, `PRS`, `TERMINAL`) every `agent({ schema })` call validates against. Imported by the workflow script and its tests. |
| `helpers.js` | The **pure, deterministic** helpers (`validateCitations`, `dedupeAndRank`, `selectEligible`, `orderByTier`, `groupCrossRepoReqs`, the `blocked`/`failed` terminal constructors, …), extracted from the engine so they are `node:test`-importable. No runtime globals, no clock/randomness/fs. Imported by `adlc-sprint.workflow.js` and by the tests. |
| `tests/` | `node:test` unit tests for `helpers.js` (the LESSON-008 citation boundary, the BR-7 consolidation gate, the BR-12 max-5 bound). Run: `node --test 'workflows/tests/*.test.js'`. See [`tests/README.md`](tests/README.md). |

## How `workflows/` is reached (no install change)

`~/.claude/skills` is an **absolute-path symlink to this toolkit repo**, so a
workflow script — and anything it imports — resolves through the existing skills
symlink with no new install step:

```
~/.claude/skills/workflows/schemas.js   →   <toolkit>/workflows/schemas.js
```

This mirrors how `templates/` and `partials/` are reached. Nothing in the
symlink install needs to change to add `workflows/`.

## Two-level path-resolution convention

Like every other shared toolkit asset (`partials/*.sh`, `templates/*.md`,
`.adlc/context/*.md`), workflow modules are resolved with a **two-level
fallback**: prefer the consumer project's vendored copy under `.adlc/`, then
fall back to the global toolkit via the skills symlink.

```
.adlc/workflows/<file>            # consumer-project copy (vendored by /init)
  ↓ if absent
~/.claude/skills/workflows/<file> # canonical toolkit copy (via skills symlink)
```

Why the local copy? Claude Code's sandbox blocks `Read` from paths outside the
current working directory. When the engine runs inside a git worktree (e.g.
`.worktrees/REQ-xxx/`), `~/.claude/skills/workflows/*` is unreadable by
subagents and any mid-skill `Read`. `/init` therefore vendors `workflows/` into
the consumer's `.adlc/workflows/` (alongside `templates/` and `partials/`) so
the engine works identically in a main checkout and in a worktree.

The prefer-local-then-global order means a consumer project that has not re-run
`/init` since `workflows/` shipped still resolves the module from the global
toolkit — the engine degrades gracefully rather than breaking.

## Keeping vendored copies fresh

The canonical source of truth is this `workflows/` directory in the toolkit
repo. Consumer projects get a copy at `/init` time. To refresh a stale local
copy, re-run `/init` (it overwrites the vendored `.adlc/workflows/` from the
canonical toolkit copy).
