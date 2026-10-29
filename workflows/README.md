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
   the per-REQ Phase 0–8 chain) using `agent()` / `parallel()` / `pipeline()`,
   followed by three post-pipeline passes: the ADR-12 cross-repo merge barrier,
   the REQ-485 unblock pass, and the **BUG-249 Step-8b close-out pass** — every
   `merged` REQ gets `/wrapup --close-out` in a dedicated
   `<repoRoot>/.worktrees/<id>-close-out` worktree (spec status, the five-field
   terminal record, knowledge capture from the run evidence the engine keeps in
   memory, a squash-merged `chore(<id>): close-out` PR, worktree teardown),
   serially per repo. The terminal stays `state:"merged"` and carries
   `closeOut: ok|failed|skipped` beside it.

The toolkit forbids a build step, so the pure logic stays **inline** and is
unit-tested via a shared `vm` loader (`tests/_load-pure.js`) that evaluates just
the sentinel-delimited section with the runtime globals absent.

## Contents

| File | Role |
|------|------|
| `adlc-sprint.workflow.js` | The `adlc-sprint` engine — ONE self-contained file: `meta` first, the inlined PURE block (schemas + helpers behind the sentinels), then the control-flow orchestration that dispatches `agent()` leaves for all I/O. Runs only inside the Workflow runtime. |
| `tests/_load-pure.js` | Reusable `vm` loader: reads the `// ==== BEGIN/END PURE ====` section of a self-contained workflow script and evaluates it with the runtime globals absent, returning its `module.exports` so `node:test` can cover the pure logic with no build step. |
| `tests/helpers.test.js` | `node:test` unit tests for the inlined pure helpers (the LESSON-008 citation boundary, the BR-7 consolidation gate, the BR-12 max-5 bound, cross-REQ merge grouping), loaded via `_load-pure.js`. Run: `node --test 'workflows/tests/*.test.js'`. See [`tests/README.md`](tests/README.md). |

## How `workflows/` is reached on both install routes (REQ-669)

The toolkit installs one of two ways, and `workflows/` is reached the same way
on both, through **ToolkitRoot** (`$ADLC_TOOLKIT_ROOT`, resolved by the canonical
root line in conventions.md 'Bash in skills'):

| Route | ToolkitRoot | The engine is at |
|---|---|---|
| symlink | the clone that `install.sh` links into the skills directory | `<clone>/workflows/adlc-sprint.workflow.js` |
| plugin | the plugin's own copy, from the substituted `${CLAUDE_PLUGIN_ROOT}` | `<plugin cache copy>/workflows/adlc-sprint.workflow.js` |

This mirrors how `templates/` and `partials/` are reached, so neither install
needs a step of its own for `workflows/`.

## Two-level path-resolution convention

Like every other shared toolkit asset (`partials/*.sh`, `templates/*.md`,
`.adlc/context/*.md`), workflow modules are resolved with a **two-level
fallback**: prefer the consumer project's vendored copy under `.adlc/`, then
fall back to the toolkit copy under ToolkitRoot.

```
.adlc/workflows/<file>                 # consumer-project copy (vendored by /init)
  ↓ if absent
$ADLC_TOOLKIT_ROOT/workflows/<file>    # canonical toolkit copy, on either route
```

`/sprint` Step 0 does this in one fence: the root line, then `[ -f ]` on each
candidate in that order, printing `SCRIPT_PATH=<path>` or `SCRIPT_PATH=missing`
(missing falls back to the legacy engine).

Why the local copy? Claude Code's sandbox blocks `Read` from paths outside the
current working directory. When the engine runs inside a git worktree (e.g.
`.worktrees/REQ-xxx/`), `$ADLC_TOOLKIT_ROOT/workflows/*` is outside it on either
route, so it is unreadable by subagents and any mid-skill `Read`. `/init` therefore vendors the **runtime
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

The prefer-local-then-toolkit order means a consumer project that has not re-run
`/init` since `workflows/` shipped still resolves the module from the toolkit
copy — the engine degrades gracefully rather than breaking.

## The agent namespace (`args.agentNamespace`)

The engine names its specialist agents in code (`feature-tracer`, the six panel
members, `task-implementer`, `delegate-pre-pass`). Claude Code registers the
toolkit's agents by bare name on the symlink route and as `adlc:<name>` on the
plugin route (REQ-669 `verification.md` row 7). A wrong spelling does not fail
loudly: on the fork path an unresolved name silently became a generic agent with
no checklist. The runtime has no filesystem, so the script cannot tell the
routes apart. That the Workflow tool's `agentType` takes the `adlc:<name>`
spelling is inferred from the agent registry (row 7) and is not yet probed
(row 8 needs a model turn and was not run).

So `/sprint` decides, and passes it in:

- **`args.agentNamespace`** (string, default `""`): `"adlc:"` when `/sprint`
  runs from the plugin install, `""` on the symlink install. `/sprint` reads it
  off its own text: Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` in a plugin
  skill before the fence runs, so a non-empty value means plugin. Keep it
  identical on every `resumeFromRunId` relaunch, like `reqs` and
  `integrationBranch`.
- The script reads it **once**, at the top of the orchestration, through the
  pure `normalizeAgentNamespace`. Only the frozen `AGENT_NAMESPACES` values, `""`
  (or an absent value) and `"adlc:"`, are accepted. Anything else, a well-shaped
  `"other:"` or a non-string included, is logged
  (by type, never by value: it is untrusted input, LESSON-008) and replaced by
  `""`, so a bad value degrades to bare names.
- Every `agentType` goes through the pure `agentTypeFor(name, ns)`, which
  normalizes again: `agentTypeFor('reflector', 'adlc:')` is `adlc:reflector`,
  and an invalid `ns` yields the bare name. `tests/helpers.test.js` pins both,
  and also reads this file's source to check that every `agentType:` is
  `agentTypeFor(<name>, AGENT_NS)` and that `args.agentNamespace` has one read
  site.

## Keeping vendored copies fresh

The canonical source of truth is this `workflows/` directory in the toolkit
repo. Consumer projects get a copy at `/init` time. To refresh a stale local
copy, re-run `/init` (`/adlc:init` on the plugin install), which overwrites the
vendored `.adlc/workflows/` from the canonical toolkit copy.
