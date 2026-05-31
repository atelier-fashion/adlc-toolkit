# `workflows/` — Dynamic Workflow scripts

This directory holds the deterministic **Workflow scripts** the toolkit's
workflow engine runs (the `adlc-sprint` engine). A Workflow script owns control
flow — sequence, fan-out, loops, merge ordering — and dispatches agents as
leaves; it carries no business prose. See REQ-474 (`/sprint` two-engine
re-platform) and the spec's ADR-2 / ADR-7.

## Single self-contained file (no `require`, `meta` first)

Dogfooding the real Dynamic-Workflows runtime proved it has **no `require` /
`import` / `fs`** and requires `export const meta` to be the **first statement**.
So the engine is **ONE self-contained file** — there are no sibling `schemas.js`
/ `helpers.js` modules to import. Inside `adlc-sprint.workflow.js`:

1. `export const meta = { … }` is the **first statement** (the runtime reads it
   statically to render the phase timeline).
2. A **PURE block** immediately follows, delimited by exact sentinel comments:

   ```js
   // ==== BEGIN PURE ====
   <the 7 JSON-Schema literals + REVIEWER_DIMENSIONS, inlined>
   <every pure helper: validateCitations, dedupeAndRank, selectEligible,
    orderByTier, groupCrossRepoReqs, blocked/failed, …>
   if (typeof module !== 'undefined') module.exports = { /* every name above */ };
   // ==== END PURE ====
   ```

   The `if (typeof module !== 'undefined')` guard is **load-bearing**: in the
   Workflow runtime `module` is undefined so the line is skipped (a bare
   `module.exports = …` would throw); under the test loader `module` is defined
   so the exports populate. The inlined consts/functions are in normal file
   scope, so the orchestration below the sentinels references them directly (no
   import).
3. Everything below `// ==== END PURE ====` is the orchestration (Preflight +
   the per-REQ Phase 0–8 chain) using `agent()` / `parallel()` / `pipeline()`.

The toolkit forbids a build step, so the pure logic stays **inline** and is
unit-tested via a shared `vm` loader (`tests/_load-pure.js`) that evaluates just
the sentinel-delimited section with the runtime globals absent.

## Contents

| File | Role |
|------|------|
| `adlc-sprint.workflow.js` | The `adlc-sprint` engine — ONE self-contained file: `meta` first, the inlined PURE block (schemas + helpers behind the sentinels), then the control-flow orchestration that dispatches `agent()` leaves for all I/O. Runs only inside the Workflow runtime. |
| `tests/_load-pure.js` | Reusable `vm` loader: reads the `// ==== BEGIN/END PURE ====` section of a self-contained workflow script and evaluates it with the runtime globals absent, returning its `module.exports` so `node:test` can cover the pure logic with no build step. |
| `tests/helpers.test.js` | `node:test` unit tests for the inlined pure helpers (the LESSON-008 citation boundary, the BR-7 consolidation gate, the BR-12 max-5 bound, cross-REQ merge grouping), loaded via `_load-pure.js`. Run: `node --test 'workflows/tests/*.test.js'`. See [`tests/README.md`](tests/README.md). |

## How `workflows/` is reached (no install change)

`~/.claude/skills` is an **absolute-path symlink to this toolkit repo**, so a
workflow script — and anything it imports — resolves through the existing skills
symlink with no new install step:

```
~/.claude/skills/workflows/adlc-sprint.workflow.js   →   <toolkit>/workflows/adlc-sprint.workflow.js
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
subagents and any mid-skill `Read`. `/init` therefore vendors the **runtime
files only** — `adlc-sprint.workflow.js` and this `README.md` — into the
consumer's `.adlc/workflows/` (alongside `templates/` and `partials/`) so the
engine works identically in a main checkout and in a worktree.

**`tests/` is NOT vendored — by design.** The `tests/` directory holds
toolkit-internal `node:test` unit tests (CommonJS `require('node:test')`) for the
inlined pure helpers; they have no purpose in a consumer repo. Worse, shipping a
`*.test.js` under `.adlc/` is a Jest landmine: in any `"type":"module"` repo, the
default Jest `testMatch` discovers `.adlc/workflows/tests/helpers.test.js`, runs
it as ESM, and fails it with `ReferenceError: require is not defined` — reddening
`npm test` and any CI gate. So `/init` copies `*.workflow.js` + `README.md`
explicitly and never `tests/` (and `rm -rf`s a stale `tests/` from an older
`/init`). `/template-drift` flags the stale directory if it lingers.

The prefer-local-then-global order means a consumer project that has not re-run
`/init` since `workflows/` shipped still resolves the module from the global
toolkit — the engine degrades gracefully rather than breaking.

## Keeping vendored copies fresh

The canonical source of truth is this `workflows/` directory in the toolkit
repo. Consumer projects get a copy at `/init` time. To refresh a stale local
copy, re-run `/init` (it overwrites the vendored `.adlc/workflows/` from the
canonical toolkit copy).
