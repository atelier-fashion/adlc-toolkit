# `workflows/tests/` — unit tests for the deterministic workflow helpers

These are the **unit tests** for the pure, deterministic helpers of the
`adlc-sprint` Dynamic Workflows engine — its security-critical and consolidation
logic. The Workflow runtime has no `require`/`import`/`fs`, so the engine is ONE
self-contained file ([`adlc-sprint.workflow.js`](../adlc-sprint.workflow.js)) and
those helpers are **inlined** behind the `// ==== BEGIN/END PURE ====` sentinels.
The shared loader [`_load-pure.js`](./_load-pure.js) reads just that section and
evaluates it with the runtime globals absent, so `node:test` can cover the logic
with **no build step**. (REQ-474, TASK-063, ADR-2, ADR-10)

The orchestration itself (the control-flow below the sentinels) is **dogfooded**
by running `/sprint --workflow` on a real REQ — it only runs inside the Workflow
runtime. The *pure* helpers, however, are exactly the code that must never
silently regress (the LESSON-008 citation boundary, the BR-7 review-consolidation
gate, the BR-12 max-5 bound), so they get real, deterministic unit coverage here.

## What is covered

| Helper | Why it's tested |
|--------|-----------------|
| `validateCitations` | The **LESSON-008** security boundary. Rejects `..` traversal, paths absent from `changedFiles`, charset violations (`^[A-Za-z0-9_./-]+$`: spaces, shell metachars, NUL/tab), and reflector/unknown dimensions; **sanitizes** untrusted descriptions; accepts a valid in-diff candidate. |
| `sanitizeDescription`, `candidatesByDimension` | The sanitizer and per-dimension bucketing that feed reviewer prompts. |
| `dedupeAndRank` | The **BR-7** consolidation gate: within-repo dedupe (unioning dimensions, keeping the most severe), cross-repo tagging, severity ranking, and the `Critical OR mustFix ⇒ blocks` merge predicate. Includes a determinism check. |
| `selectEligible` | The **BR-12** Preflight selection + max-5 truncation (the dropped tail is surfaced, never silently lost). |
| `orderByTier` | The Phase-4 stable ascending tier sort. |
| `groupCrossRepoReqs` | The **ADR-12** cross-REQ merge grouping (union-find over "shares a touched repo"). |
| `blocked` / `failed` | The TERMINAL constructors — `state` discriminant, string→`{detail}` normalization, undefined-key omission (closed-schema safe). |

## Running the tests

The toolkit has **no JS package manager and no JS CI** — these tests use Node's
**built-in** `node:test` + `node:assert` runner, so there are **zero new
dependencies**. Run from the **toolkit repo root** (the directory that contains
`workflows/`):

```sh
node --test 'workflows/tests/*.test.js'
```

Expected: all tests pass (`ℹ pass 44  ℹ fail 0`).

> **Note on Node versions.** The glob form above is the portable invocation. On
> recent Node (≥ 22) you can also let the runner discover tests by walking the
> current directory:
>
> ```sh
> node --test
> ```
>
> Passing a *directory* path (`node --test workflows/tests/`) is **not** a
> portable discovery form — on Node 25 a directory argument is treated as a
> module entry point, not a discovery root — so prefer the glob (or bare
> `node --test`) above.

## Manual gate (no CI)

Because the toolkit ships no `.github/workflows` JS pipeline, this suite is a
**manual gate**: run it after any change to the inlined PURE section of
`workflows/adlc-sprint.workflow.js` (or to a helper's behavior). It is fast
(< 100 ms) and fully deterministic — no clock, no
randomness, no filesystem or network — so a green run on one machine is a green
run everywhere.
