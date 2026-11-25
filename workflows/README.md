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
4. **Lessons (REQ-647).** Three retrieval leaves run `adlc_lessons select`
   (`partials/lessons.sh`) and return a schema-validated `LESSONS` value: the
   Step-0 set after Phase 0, every task's set in one `TASK_LESSONS` call before
   Phase 4, and the Phase-5 set before the panel fans out. Each leaf also writes
   the set, without its loaded text, to `lessons.<set>` in the primary-path
   `pipeline-state.json`. `architectPrompt`, `implementPrompt` and
   `reviewPrompt` (all six members; the reflector is told the set was
   pre-computed) carry the loaded text. Before consolidation,
   `escalateByLessons` raises a finding one severity level only when its
   `lessonId` is an id in the Phase-5 set (an id outside it is dropped), honoring
   the `confidence: low` and superseded exemptions, and `dedupeAndRank` unions
   lesson ids across duplicates. The leaf prompts never read `args.answers`, so
   a resume replays them from the journal and every prompt built from them stays
   byte-identical. Retrieval never halts a REQ: an unavailable set is logged and
   the prompts carry no lessons block.
5. **Run-outcome telemetry (REQ-648).** Every panel member's `FINDINGS` entry
   carries a required `class` matching `FINDING_CLASS_PATTERN` (a kebab-case
   defect pattern, a lesson id, or a `title-slug:`; the same regex as
   `tools/delegate/run_outcome.py` `CLASS_RE`, held equal by a test). After the
   first consolidation, and again after the re-verify when the fix loop ran, a
   state-write leaf records `verify` in the primary-path `pipeline-state.json`
   through `emit-run-outcome.sh record-verify`; `markWorkflowFixed` marks a
   finding fixed only when it was blocking and is absent from the re-verify.
   Each validate attempt records `validateAttempts.phase<1|3>` with the gate's
   loop counter (absolute and monotone, so a replay never double-counts). After
   the close-out pass, `emitRunOutcomes` runs one leaf per REQ, whatever its
   terminal, passing `TERMINAL.state` verbatim and the raw reason
   (`runOutcomeArgs`), which the Python normalises onto its closed enum. None of
   these leaves can halt a REQ or change `{results}`, and none reads
   `args.answers`.
6. **The cross-family reviewer (REQ-722).** Beside the pre-pass, `verify` runs
   `runCrossFamily`: one `cross-family-reviewer` leaf per touched repo, once per
   run. The leaf is a pass-through. It sources `partials/cross-family-review.sh`,
   runs `adlc_cross_family_review` (another model family's review, post-validated
   in `tools/delegate/cross_family.py`, which also writes the repo's
   `crossFamilyReview` record), and returns a `CROSS_FAMILY` value. It is not a
   panel member: `panelMembers()` stays six and `REVIEWER_DIMENSIONS` has no entry
   for it, so `fixedPairs` never schedules it for the Step D re-verify (BR-1).

   - **`FINDINGS`** items gain three optional fields: `source`, a non-empty list
     of `FINDING_SOURCES` (`panel`, `cross-family`); `disposition`, one of
     `fixed`, `deferred`, `declined`; and `declineReason`. A panel finding omits
     `source`, and an absent `source` means `panel`. The engine owns all three:
     `joinCrossFamily` drops whatever a review leaf wrote, and sets `source:
     ["cross-family"]` on the cross-family findings itself.
   - **`CROSS_FAMILY`** is closed: `status` (`ran` | `skipped`), `reason` (one of
     `CROSS_FAMILY_SKIP_REASONS`, exactly when skipped), `implementerFamily` and
     `reviewerFamily` (`MODEL_FAMILIES`), `findings` (the `FINDINGS` item schema),
     `dropped`, `findingCount` (the record's count, read back by the leaf), and an
     optional `ruleMarks` (`met`, `partial`, `unmet`). Each
     vocabulary is a copy of its Python owner (`cross_family.py`,
     `model_family.py`, `run_outcome.py`), held equal by a test. The skip reasons
     are REQ-722's eight, not the pre-pass `CANDIDATES.gateReason` enum.
   - **The leaf's copy is not trusted.** The leaf is a model relaying another
     model's output, so `crossFamilyOutcome` re-validates every finding it relays
     (`crossFamilyFinding`): `file` passes `isSafePath`, `validateCitations`' own
     path rule; `severity` is in the enum; `class` matches
     `FINDING_CLASS_PATTERN`; the title is cut to `[A-Za-z0-9 .,:/_-]` and 200
     characters; `source` is forced to `["cross-family"]`; and no other free-text
     field survives. A finding that fails is dropped and counted into `dropped`.
     A `ran` result whose `findingCount` is missing or differs from the number of
     findings it relays is `invalid-output`: the leaf added or removed one.
     `joinCrossFamily` applies the same rule again.
   - **Consolidation.** `joinCrossFamily` adds a repo's findings as one extra set
     with no `dimension`, so they get `dimensions: []`. No panel prompt ever
     carries them (BR-7). `dedupeAndRank` deduplicates them against the panel's
     under the unchanged key, unions `source` on merge (sorted, so a finding
     both raised is `["cross-family", "panel"]`), and blocks on a Critical or
     `mustFix` one exactly as on a panel finding. A consolidation with no
     cross-family finding carries no `source`, as before. `mergeReverified` keeps
     the dimension-less set, so Step D neither re-runs nor drops it, and
     `verifyEntry` carries `source` into the recorded `verify` findings.
   - **Step D confirms its blocking findings (BR-1).** `confirmersOf` names the
     reviewer dimensions that confirm a blocking finding: each of its panel
     dimensions for a merged one, `CROSS_FAMILY_CONFIRMER` (`correctness`) for a
     cross-family-only one. `confirmLists` hands each re-check its findings
     (`file`, `line`, `title`, `class`, sanitized) in the eighth `reviewPrompt`
     argument, with the instruction to report again any that is still present.
     Only the re-check prompt carries it; the first pass never does, because BR-7
     forbids a panel member seeing these findings before consolidation.
     `retireConfirmedCrossFamily` then drops a blocking finding's cross-family copy
     only when every dimension handed it re-ran (`reranDimensions`: a null result,
     or one filed under another dimension, re-ran nothing). A re-raised finding
     blocks again.
   - **Dispositions (BR-8).** The engine never declines, so `verifyEntry` records
     a cross-family finding `fixed` when fixed, `deferred` when it is neither
     Critical nor `mustFix`, and nothing when it is blocking and unfixed, with
     `mustFix: true` and `line` when it has them.
   - **Phase 6 checks first (BR-8, BR-5).** The Phase-6 leaf runs
     `cross_family.py check-dispositions` from the primary worktree against the
     primary-path state before it pushes anything. On any non-zero exit it opens
     nothing and returns PRS `dispositionCheck: "refused"` with the lines the check
     printed; `dispositionHold` turns that, or a missing `dispositionCheck`, into a
     `blocked` terminal (`cross-family-dispositions`) before CI or merge. On a pass
     it puts `cross_family.py pr-section`'s output, verbatim, into every PR body.
   - **A result the engine cannot use is recorded, never omitted (BR-12).**
     `crossFamilyOutcome` turns `null` (a leaf that threw, returned nothing or
     failed the schema) and a value that breaks "reason exactly when skipped" into
     `skipped` / `invalid-output` with both families `unknown`. A state-write
     leaf then records it through `emit-run-outcome.sh record-cross-family`,
     spelling the repo id only when it matches `REPO_ID_PATTERN`
     (`^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$`, the partial's and the fence census's
     `repo-id`, held equal by a test). Every repo gets one log line naming its
     status or skip reason.

   A consumer's vendored `.adlc/workflows/adlc-sprint.workflow.js` that predates
   REQ-722 is preferred over this copy (see the two-level convention below), so
   it dispatches no cross-family leaf and writes no `crossFamilyReview` record
   until `/init` refreshes it. `/template-drift` reports the copy as stale.

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
members, `task-implementer`, `delegate-pre-pass`, `cross-family-reviewer`). Claude Code registers the
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
