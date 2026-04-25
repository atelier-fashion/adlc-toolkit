# Architecture — REQ-263 Sprint Worktree Isolation

## Approach

Three-file documentation/skill change. No new code, no schema migration, no service. The fix is a tighter dispatch contract between `/sprint` (orchestrator) and `/proceed` (per-REQ pipeline), enforced by `git worktree list` validation, with a corresponding tightening of the `pipeline-runner` agent's worktree-isolation contract.

Three independent edit surfaces, three tasks. They can be implemented in parallel because they edit three different files, share no code, and the contract between them is fixed by this architecture document (not by edit order).

## The dispatch-line contract

The single piece of inter-task coordination is the **dispatch-line format** — `/sprint` Step 3 emits it, `/proceed` Step 0 parses it. To prevent drift between producer and consumer when both tasks run in parallel, the contract is fixed here:

**Format** (a single line in the agent's launch prompt):

```
WORKTREE PATH (mandatory): <absolute-path>
```

**Rules**:
- Exactly one space after `WORKTREE PATH`, exactly one space after `(mandatory):`.
- `<absolute-path>` is a POSIX absolute path, no quoting, no trailing whitespace, no trailing slash.
- Line stands alone (its own line in the prompt — not embedded in a sentence).
- Parser regex (informative): `^WORKTREE PATH \(mandatory\): (.+)$`. Matches the entire line; capture group is the path.
- Producer in `/sprint` Step 3 MUST emit this line for every dispatched `pipeline-runner`. Consumer in `/proceed` Step 0 MUST scan for it and use the captured path verbatim. Absence of the line triggers fallback derivation per BR-2.

This is the only contract between TASK-007 and TASK-008. Architecture-reviewer in Phase 5 will verify both files match the format declared here.

## Per-task surface map

| Task | File | Section(s) edited | BRs covered |
|---|---|---|---|
| TASK-007 | `proceed/SKILL.md` | Step 0 (insert path-parse step + validation gate before `git worktree add`); Pipeline State Tracking section (clarify `repos[<id>].worktree` is immutable post-Step-0) | BR-2, BR-3, BR-4, BR-8, BR-9, BR-10 |
| TASK-008 | `sprint/SKILL.md` | Step 2 (add collision pre-flight row + check); Step 3 (extend dispatch prompt template with the contract line) | BR-1, BR-5, BR-7, BR-9 |
| TASK-009 | `agents/pipeline-runner.md` | Insert "Worktree Isolation" section between "CRITICAL: Subagent Mode" and "Pipeline Phases" | BR-6 |

All three files live in the toolkit primary repo. Single-repo mode. No cross-repo dependencies.

## Decisions

### ADR-1: Validation gate lives in `/proceed`, not in a shared helper

**Decision**: The `git worktree list --porcelain` validation gate is implemented inline in `/proceed` Step 0, not extracted into a shared helper invoked by both `/proceed` and `/sprint`.

**Rationale**: The toolkit has no helper layer — skills are self-contained markdown. Extracting a helper would require either (a) a new skill that's never invoked directly, or (b) duplicating the validation prose in both `/sprint` Step 2 and `/proceed` Step 0. Inline-in-`/proceed` keeps the validation close to the one operation that needs it (`git worktree add`); the `/sprint` pre-flight is a different check (collision against the candidate set, before any agent dispatches) that doesn't share logic. Two checks, two locations, both small.

### ADR-2: Skip the worktree-add when the contract path already matches a registered worktree on the target branch

**Decision**: If `git worktree list --porcelain` reveals the target path is already registered AND on the expected `feat/REQ-xxx-...` branch, `/proceed` Step 0 treats it as a resume scenario — record the path in state, skip the `git worktree add`, continue. Only different-branch ownership triggers the fail-loud halt.

**Rationale**: `/proceed` already supports resume from interruption (Pipeline State Tracking section, rule 5). Treating "same path, same branch, no state file yet" as a soft resume is consistent — the worktree exists, the branch is correct, the only thing missing is the state file (which Step 0 is about to create anyway). Alternative behavior (fail on any pre-existing worktree) would force users to manually remove a stale-but-correct worktree before retrying a crashed `/proceed`, which is friction without safety benefit.

### ADR-3: Fallback derivation stays — direct `/proceed` invocations don't need the contract line

**Decision**: `/proceed` Step 0 looks for the contract line first; if absent, falls back to deriving `<repo>/.worktrees/REQ-xxx`. The contract line is required from `/sprint` (orchestrator) but optional when a user invokes `/proceed REQ-xxx` directly.

**Rationale**: BR-2 and BR-10 explicitly require this. Users running `/proceed` for a single REQ on a clean repo must see no behavior change. The contract exists to coordinate parallel invocations — a single invocation has nothing to coordinate against.

### ADR-4: No locking primitives

**Decision**: We do not introduce `.adlc/locks/REQ-xxx.lock` files or any other locking mechanism. The combination of orchestrator-declared paths + Phase 0 validation + Step 2 pre-flight is sufficient.

**Rationale**: Locks introduce a recovery problem — stale locks after crashes — without removing a real risk in the current threat model. The actual race is "two sibling pipelines try to use the same worktree path." Declaring the path up front and validating before `git worktree add` closes the window. A lock would close the same window with more failure modes.

## Cross-repo behavior (BR-8)

For cross-repo REQs (when invoking `/proceed` from a primary with sibling repos), `/sprint` declares the **primary repo's** worktree path in the dispatch line. Sibling worktree paths are still resolved by `/proceed` Step 0 from `.adlc/config.yml` and validated against each sibling's `git worktree list --porcelain`. This keeps the dispatch line short and avoids encoding the full repo registry in a prompt — the registry is the config file's job.

The validation gate (BR-3) applies to **every** `git worktree add` Step 0 performs, primary or sibling. A sibling collision halts with the same error format as a primary collision.

## Lessons applied

- **LESSON-002** — `pipeline-state.json` is the per-REQ runtime registry. This REQ extends that principle: the registry must be **orchestrator-populated** (or, for direct `/proceed`, derived once and frozen), not re-derived by agents mid-run.
- **LESSON-003** — sprint dispatch must declare each pipeline-runner's worktree path. This REQ codifies the lesson; the lesson and REQ ship together.

## What this architecture does NOT change

- The `.worktrees/REQ-xxx` path convention itself.
- The `pipeline-state.json` schema (the `repos[<id>].worktree` field already holds the absolute path).
- The 8-phase `/proceed` pipeline structure.
- Any user-facing CLI or argument shape.
- Any test infrastructure (the toolkit has none — dogfooding is the test mechanism).
