---
parent: proceed
phase: 0
---

# /proceed — Step 0: resolve repos, create worktrees, preflight, load shared context

Companion to `proceed/SKILL.md` (REQ-661). Its Step 0 sends you here first, before any phase. Follow every item below in order, then return to `proceed/SKILL.md` at Phase 1, or at the phase `pipeline-state.json` says to resume from.

### Step 0: Resolve Repos + Create Worktrees + Preflight + Load Shared Context (ALWAYS FIRST)

**Before doing anything else**, resolve the repository set, isolate each touched repo in a git worktree, and prime the shared context so subskills don't re-read the same files:

1. **Preflight** — verify all prerequisite files exist in the **primary** repo (stop with a clear message if any are missing):
   - `.adlc/context/project-overview.md` — run `/init` (`/adlc:init` on the plugin install) if missing
   - `.adlc/context/architecture.md` — run `/init` (`/adlc:init` on the plugin install) if missing
   - `.adlc/context/conventions.md` — run `/init` (`/adlc:init` on the plugin install) if missing
   - `.adlc/specs/REQ-xxx-*/requirement.md` — run `/spec` if missing
2. **Resolve repo registry**:
   - Read `.adlc/config.yml` if it exists. If absent or has no `repos` block, use single-repo mode: the registry is `{ <cwd-repo-id>: { primary: true, path: <cwd>, touched: true } }` where the repo id is the basename of the cwd.
   - In cross-repo mode: the primary entry's `path` is cwd. Resolve each sibling's `path` to an absolute path (relative paths are relative to the primary repo root). Verify each path exists and is a git repo (`git -C <path> rev-parse --git-dir`). If any sibling is missing, stop with a clear error listing the missing repos.
3. **Determine touched repos** (best-effort at Step 0; confirmed after Phase 2):
   - If tasks already exist under `.adlc/specs/REQ-xxx-*/tasks/`, read each task's `repo:` field to compute the touched set.
   - If tasks don't exist yet (fresh pipeline), assume every configured repo is potentially touched and create worktrees in all of them. Post-Phase-2, untouched repos will be marked `touched: false` and their worktrees removed.
   - The primary is always touched (even if no primary tasks — it hosts the spec and state file).
4. **Determine the integration branch, then fetch it in each touched repo.** The base for feature branches is NOT always `main` (LESSON-036 — sprinted runners that hardcoded `main` in a staging-first repo paid a mid-pipeline rebase + PR-retarget every time). Resolve `<integration-branch>` in this order — the first rule that applies wins, and every other skill that needs the integration branch (`/sprint`, `/bugfix`, `/wrapup`, `/template-drift`, the `pipeline-runner` agent) uses this same rule rather than inventing a second one:
   1. **The config names it.** Read `.adlc/config.yml`. If it declares `branches.integration`, that value (a branch name such as `dev`, `staging` or `main`) is `<integration-branch>` outright — do **not** consult the signals in rule 2. This is how a repo whose model the signals cannot express tells the pipeline where feature work integrates: a `dev` → `staging` → `main` promotion pipeline declares a `gcp.staging_project` like any staging-first repo, but its PRs must target `dev`, and its head-ref check will refuse a PR into `staging`. In cross-repo mode read each touched repo's own `.adlc/config.yml`; a sibling with no config or no key falls through to rule 2 for that repo alone.
   2. **Otherwise detect the branch model from signals**; **any one** signal is sufficient:
      - `.adlc/config.yml` declares a `gcp.staging_project` (or otherwise indicates a staging-first deploy), OR
      - a `.github/workflows/*` enforces a `verify-head-ref` / branch-protection head-ref check, OR
      - `CLAUDE.md` describes a "two-branch" / "staging-first" / "staging → main promotion" pipeline.

      If any signal is present, `<integration-branch>` is the project's integration branch (`staging` unless the project names another); otherwise `<integration-branch>` is `main`.

   **Always fetch before reasoning about any ref or spec presence** (never trust a stale local ref — LESSON-036):
   ```bash
   git -C <repo-path> fetch origin
   ```
   Do NOT `git checkout <integration-branch>` in `<repo-path>` — it may be checked out in another worktree and fail. The worktree (step 5) is created directly from `origin/<integration-branch>`. Feature branches and the Phase 6 PR base MUST use `<integration-branch>`, never a hardcoded `main`.

   **Step 4 advisory — in-flight manifest (non-blocking, REQ-482).** With `origin` now fetched and **before** the worktree is created, surface what else is in flight across sessions so you can spot overlaps before starting. **In subagent mode (`/sprint` pipeline-runner): SKIP this** — `/sprint` already built the manifest once for the batch in its pre-flight. Otherwise invoke `/manifest`, prefixing the same shell call with the hand-off vars so it reuses this fetch and marks the current REQ as self: `MANIFEST_SELF="REQ-xxx" MANIFEST_SKIP_FETCH=1` (substitute the concrete REQ id). Display the in-flight table and any coarse `component`/`domain` overlap involving the current REQ. This is **purely advisory**: it MUST NOT block, halt, reorder, or gate the pipeline; it is NOT one of the four legitimate halt points; a manifest-build failure is ignored with a one-line note and the pipeline continues (BR-7, BR-8, BR-9). The worktree-collision gate (step 4b) is unchanged.

   **Step 4 pre-push REQ-id recheck (REQ-545 — closes the REQ-518 BR-4 gap for the REQ kind).** With `origin` now fetched and **before** any worktree, branch, or push is created, re-verify this REQ's id against the remote. The id was allocated by `/spec`; between allocation and this branch push, a colleague on another machine may have pushed the same `feat/REQ-xxx` — catching it here is far cheaper than at PR/merge time. **Unlike the manifest advisory above, this runs identically in solo `/proceed` and in `/sprint` pipeline-runner subagent mode (BR-5) — do NOT skip it in subagent mode.** A collision halts with the partial's renumber instruction; this is classified alongside the worktree-collision gate (step 4b) — a **pre-flight precondition halt, NOT one of the four legitimate mid-pipeline halt points**. Source `partials/id-recheck.sh` (the guarded spelling from conventions.md "Bash in skills") and call `adlc_recheck_id` **in the same fenced block** (LESSON-329 — a function sourced in one fence is undefined in the next). See `partials/id-recheck.sh` for the exact-id probe + degraded short-circuit contract:
   ```bash
   # WHY (REQ-518 BR-4): re-verify an allocated id against the remote at every point it is
   # about to become a remote footprint. `/proceed` creating feat/REQ-xxx is exactly such a
   # point; this call site closes the gap left when REQ-518 TASK-004 wired only the /bugfix +
   # /wrapup call sites. Derivation + renumber message live in partials/id-recheck.sh.
   #
   # BRANCH is the feat/REQ-xxx-<slug> this run will create — the SAME slug step 4b derives
   # (no new slug logic). Self-exemption (BR-3): if the remote already carries this EXACT full
   # branch name, the footprint is ours — a resume whose Step-8a draft push already ran, or a
   # crashed prior session of this same work item (id+slug identity => same work item). Skip
   # the recheck and reuse. A hit with the same id but a DIFFERENT slug, or a merged-artifact
   # hit for another work item, is NOT exempted here and still halts below. <repo-path> is the
   # primary repo path (item 4's `git -C <repo-path> fetch origin`).
   BRANCH="feat/REQ-xxx-<slug>"
   if [ -n "$(git -C <repo-path> ls-remote --heads origin "refs/heads/$BRANCH" 2>/dev/null)" ]; then
     echo "id recheck: remote already carries this pipeline's own '$BRANCH' (resume / crash-recovery) — skipping self-collision halt (REQ-545 BR-3)." >&2
   else
     ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
     if [ -f .adlc/partials/id-recheck.sh ]; then . .adlc/partials/id-recheck.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-recheck.sh"; fi
     # OWN_SPEC_DIR is this REQ's own spec dir basename (REQ-xxx-<dirslug>) from the
     # invoking repo — passed so the recheck recognizes the REQ's OWN merged spec as
     # self (specs merge BEFORE /proceed in the normal flow; without this the
     # merged-artifact probe false-halts on the work item itself — BUG-145). find,
     # not a bare glob: zsh aborts on an unmatched glob (LESSON-335).
     OWN_SPEC_DIR=$(find <repo-path>/.adlc/specs -maxdepth 1 -name 'REQ-xxx-*' -type d 2>/dev/null | head -1 | awk -F/ '{print $NF}')
     if ! adlc_recheck_id req "REQ-xxx" "$OWN_SPEC_DIR"; then
       echo "Halting: REQ-xxx already exists on the remote — renumber before creating the feat/REQ-xxx branch (see message above)." >&2
       exit 1
     fi
   fi
   ```
   A degraded/unreachable remote is handled inside the partial (it warns `DEGRADED — proceeding WITHOUT remote verification` and returns success — BR-4); the recheck can only fail to FIND a collision, never invent one, so a degraded derivation never blocks.
4a. **Parse the declared worktree path (primary repo only)** — scan the launch prompt for the dispatch-line contract. The format is normative in `REQ-263 architecture.md` ("The dispatch-line contract" section); do not change the regex or format here without updating that document.
   - Regex: `^WORKTREE PATH \(mandatory\): (.+)$` (entire line, capture group is the absolute path).
   - If multiple lines match the regex, use the **first** match and ignore the rest. (This makes parser behavior deterministic if a future change accidentally embeds free-text content that matches.)
   - If present, use the captured path **verbatim** as the primary repo's worktree path. Do not modify, normalize, or append to it. Compute `<primary-worktree-path>` = the captured value.
   - If absent (e.g., a direct `/proceed REQ-xxx` invocation by a user), fall back to deriving `<primary-worktree-path>` = `<primary-repo-path>/.worktrees/REQ-xxx` (where REQ-xxx is the concrete REQ id, not a literal placeholder). This preserves existing behavior for direct invocations.
   - Sibling repo worktree paths are always derived: for each sibling repo `s`, `<sibling-worktree-path[s]>` = `<sibling-repo-path[s]>/.worktrees/REQ-xxx` from `.adlc/config.yml` — the dispatch line declares only the primary path.
4b. **Validate against `git worktree list` before adding** — for **each** touched repo (primary and every sibling), run:
   ```bash
   git -C <repo-path> worktree list --porcelain
   ```
   Parse the line-oriented output: blocks separated by blank lines. Each block contains `worktree <abs-path>`, `HEAD <sha>`, and either `branch <ref>` or `detached`. Locked or prunable worktrees may add extra lines (`locked [<reason>]`, `prunable <reason>`) — ignore those; the only fields that matter for collision detection are `worktree` and `branch`. The first block is always the repo's primary working tree (the repo root) — it will not match any `<repo-path>/.worktrees/REQ-xxx` target path, so it is harmlessly skipped. Continue scanning every subsequent block.

   Compute `<expected-branch-ref>` = `refs/heads/feat/REQ-xxx-<slug>` where `<slug>` is the same slug `/proceed` would derive for this REQ (the value that becomes `repos[<id>].branch` in state). For a fresh run, derive the slug from the REQ title per the project's branch-naming convention; for a resume, read it from `repos[<id>].branch`. Then for each per-repo target path (`<primary-worktree-path>` for primary, `<sibling-worktree-path[s]>` for each sibling), classify the registration state:
   - **No match** (target path not registered in any block): proceed to step 5 (`git worktree add` as normal).
   - **Match on `<expected-branch-ref>`** (same path, same branch): treat as resume per ADR-2 — record the path in state and **skip** the `git worktree add` for this repo. No halt, no re-add.
   - **Match on a different branch ref** (or a `detached` block at the target path): halt the pipeline immediately with a clear error naming the repo, the target path, the conflicting ref (or `detached HEAD`), and the cleanup commands the user must run. **Quote the substituted `<branch>` and `<path>` values with single quotes** in the surfaced commands so a user copy-paste cannot execute injected shell from a hostile branch name:
     ```
     Worktree collision in <repo-id>: '<path>' is already registered to '<other-branch>'
     (or detached HEAD), but REQ-xxx requires '<expected-branch-ref>'. Resolve with:

       git -C '<repo-path>' worktree remove '<path>'                # add --force if the worktree has uncommitted work you intend to discard
       git -C '<repo-path>' branch -D '<other-branch>'              # -D already forces deletion regardless of merge status; verify with `git log main..'<other-branch>'` first if you may have unmerged work to keep

     Then retry.
     ```
     This is a fail-loud halt and is a **precondition error** — it does **NOT** count toward the four legitimate halt points listed in the Autonomous Execution Contract. The four-halt quota begins counting only once the pipeline is past Step 0. The same error format applies whether the colliding repo is primary or sibling.
5. Create a worktree in each touched repo on the same branch name (skip any repo where step 4b classified the registration as a same-branch resume):
   ```bash
   git -C <repo-path> worktree add -b <branch-name> <worktree-path> origin/<integration-branch>
   ```
   - The new feature branch is cut from `origin/<integration-branch>` (the ref resolved in step 4 — `branches.integration` from `.adlc/config.yml` when declared, else `staging` in two-branch repos, else `main`), NOT from local `main`/`HEAD` (LESSON-036). The `-b` creates the branch; the explicit `origin/<integration-branch>` start-point makes the base deterministic regardless of what is checked out in the repo path.
   - `<worktree-path>` is the **absolute** path resolved in 4a (`<primary-worktree-path>` for primary, `<sibling-worktree-path[s]>` for each sibling) — do **NOT** substitute a relative `.worktrees/REQ-xxx` here, even though the convention happens to produce an equivalent location. The whole point of the contract is that the orchestrator-declared absolute path is honored verbatim.
   - `<branch-name>` is `<expected-branch-ref>` from 4b with the `refs/heads/` prefix stripped — i.e., literally `feat/REQ-xxx-<slug>`. Pass the bare branch name (not the full ref) to `git worktree add -b`. (On a same-branch resume, step 4b already skipped this add — the existing worktree/branch is reused as-is.)

   Record each repo's absolute `worktree` path and `branch` in the state file's `repos` block. The recorded path is **immutable** for the rest of the run — Phases 1–8 read it from `repos[<id>].worktree`, never re-derive from cwd.
6. Change your working directory to the **primary repo's worktree** — orchestration (state file reads/writes, spec edits, PR coordination) happens there. Task implementation in Phase 4 will `cd` into the target repo's worktree per task.
7. **Load shared context ONCE from the primary** — use the Read tool to load these into conversation context so every subskill can reference them without re-reading:
   - `.adlc/context/architecture.md`
   - `.adlc/context/conventions.md`
   - `.adlc/context/project-overview.md`
   - `.adlc/specs/REQ-xxx-*/requirement.md`
   - `.adlc/config.yml` (if present)

   **Then compute the Step-0 LessonSet (REQ-647 BR-1).** The spec's `## Retrieved Context` was frozen when the spec was written; this set is the REQ-vintage background the orchestrator carries, scored by the `/spec` Step 1.6 rule over `.adlc/knowledge/lessons/` with the REQ's own frontmatter as the query, top 10. It is not the per-surface set (that is Phase 4's, BR-1a). Decide fresh or resume from the progress record, not from whether a `lessons` key exists (LESSON-719): a run whose worktree `pipeline-state.json` existed before this invocation is a resume and passes `--reuse`, which keeps a recorded `lessons.step0` instead of recomputing it; any other run passes `--fresh`, which clears a previous run's `lessons` first. `<state>` is the primary-path copy named in `proceed/phases-state.md` (`lessons`):

   ```sh
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/lessons.sh ]; then . .adlc/partials/lessons.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lessons.sh"; fi
   # <worktree> = the primary worktree; <spec> = its .adlc/specs/REQ-xxx-*/requirement.md;
   # <state> = <repos[primary].path>/.adlc/specs/REQ-xxx-*/pipeline-state.json; <mode> = --fresh | --reuse
   adlc_lessons select --set step0 --root "<worktree>" --spec "<spec>" --state-out "<state>" <mode>
   ```

   The first stdout line is the Step 0 log line (`Lessons loaded (step0): …`, BR-10); emit it, then keep the loaded text below it as background context for the run. A return of 2 prints one `lessons: unavailable — <reason>` line: emit that instead and continue — retrieval never halts the pipeline.
8. **Initialize `pipeline-state.json`** in the primary's spec directory with `currentPhase: 0, completedPhases: [], completed: false, startedAt: <now>, integrationBranch: <integration-branch>, repos: {...resolved registry with absolute paths, worktrees, branches, touched flags...}, mergeOrder: [...from config.yml or declared order, filtered to touched repos...], phase4: { currentTask: null, completedTasks: [], failedTasks: [] }`. `integrationBranch` is the value resolved in step 4 — Phase 6 (PR base) and Phase 8 (merge target) MUST read it from state, never re-derive or assume `main`. If the file already exists, read it and resume from `currentPhase` (and from `phase4.currentTask` if mid-Phase-4) — do NOT recreate worktrees that already exist.

   **Then read the lane (REQ-652), before item 8a.** Run `proceed/phases-lite.md` "Step 0 additions": read `lane` from the spec in the primary worktree (absent ⇒ `full`), record the `lane` object in state when the spec has the key (on a resume, the existing object's `lane.current` wins over the spec), handle `--full`, and, while `lane.current` is `lite` and `3` is not yet in `completedPhases` (a fresh run, or a resume of an interrupted Step 0), write `status: approved`, commit it, and record Phases 1–3 as skipped. A lite REQ skips both normal writers of `approved` (Phase 1 and `/architect`), and one left `draft` is invisible to `/spec` retrieval (BR-18):

   <!-- retrieval-status: lifecycle-write -->
   - `approved` — written here on a lite REQ
   <!-- /retrieval-status -->

   Declared for `tools/lint-skills`'s `retrieval-status-parity` check (BUG-194). That commit is also the lite branch's first, which is what lets item 8a's draft PR open (LESSON-390).

   **Then stamp the harness (REQ-648 BR-10)**: run **Run-outcome telemetry** R1 (`proceed/phases-telemetry.md`), before item 8a pushes anything, so the stamp names the toolkit that ran this pipeline even when `/wrapup` or `/sprint` later pulls the toolkit clone itself.
8a. **Open a draft PR early (REQ-483, BR-1).** After state is initialized, for each touched repo push the feature branch and open a **draft** PR through the forge adapter (so the step works on GitHub or Azure DevOps — REQ-520), making this REQ's intent — and, after `/architect`, its footprint — visible on the shared remote from the start (the precondition that makes cross-session ordering possible):
   ```bash
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
   git -C <worktree> push -u origin <branch-name>
   adlc_forge_pr_create -R <owner/repo> --draft --base <integration-branch> --head <branch-name> --title "[WIP] REQ-xxx: <short title>" --body "Draft opened at Step 0 by /proceed; body filled in at Phase 6."
   ```
   Then record `repos[<id>].prUrl`, `prNumber`, and `prCreatedAt` (from `adlc_forge_pr_view <n> --json number,url,createdAt`) into `pipeline-state.json`. The base is `<integration-branch>` from step 4 — never hardcode `main` (LESSON-036). **Resume-safe**: if `repos[<id>].prNumber` is already set, reuse it — never open a second PR. In subagent mode (`/sprint` pipeline-runner) this still runs per REQ. The PR is `--draft` (not review-ready); Phase 6 flips it to ready. (If GitHub rejects the draft because the branch has no commits yet, defer to the Phase 6 fallback once commits land — LESSON-004.)
9. When the pipeline completes (all PRs merged in Phase 8), clean up every worktree using the absolute path recorded in state — read `repos[<id>].worktree` for each touched repo and pass that value to `git worktree remove`. Do NOT use the relative `.worktrees/REQ-xxx` form here — the contract requires the recorded absolute path:
   ```bash
   git -C <repo-path> worktree remove <repos[<id>].worktree>
   ```

**Preflight verified** — when you invoke subskills in later phases, they may skip their own prerequisite checks (already validated here) AND they may skip re-reading `architecture.md` / `conventions.md` / `project-overview.md` (already in context). Treat the Step 0 loads as authoritative for the rest of the pipeline.

**After completing Step 0**: Update `pipeline-state.json` — add `0` to `completedPhases`, add Step 0 to `phaseHistory`, set `currentPhase` to `1`. **On a lite run** the lane read in item 8 has already done this update and gone further: `completedPhases` is `[0, 1, 2, 3]` and `currentPhase` is `4`. Do not reset it to `1`.
