---
id: LESSON-002
title: "Cross-repo REQ support: 'primary' is per-REQ (wherever /proceed runs), configs are symmetric mirrors"
component: "adlc/proceed"
domain: "adlc"
stack: ["claude-code", "bash", "gh-cli", "git-worktree"]
concerns: ["architecture", "developer-experience"]
tags: ["cross-repo", "config", "worktrees", "multi-repo"]
req: ""
created: 2026-04-23
updated: 2026-04-23
---

## What Happened

Several features in the Atelier Fashion product span multiple repos at once — e.g., admin-controlled iOS features require coordinated changes to `atelier-fashion` (iOS + fashion-api), `admin-api`, and sometimes `atelier-web`. The original `/proceed` pipeline handled one repo per REQ, forcing any cross-repo feature to be split into 3+ disjoint REQs that had to be manually sequenced. Single-repo bugs were easy, but anything coordinated became a workflow black hole.

The first design attempt picked a single "primary repo" (`admin-app`) that would host every cross-repo REQ's spec and state. That broke the requirement that **each repo also needed to originate its own independent REQs** (iOS-only work, API-only work). A fixed primary would have required either duplicating every repo-local REQ into the primary, or giving up repo-local REQs entirely.

## Lesson

For a toolkit that coordinates multi-repo work, **make "primary" a per-REQ role, not a repo designation**. The primary for a given REQ is simply the repo `/proceed` was invoked from — that's where the spec, tasks, and `pipeline-state.json` live for that REQ. A different REQ invoked from a different repo makes that repo primary. Every repo that can originate REQs gets its own `.adlc/` structure (from `/init`) and its own `.adlc/config.yml`. The configs across participating repos end up being **mirror images**: each repo marks itself `primary: true` and lists the others as siblings. This is symmetric by design and correct — the configs describe the world from each repo's own perspective.

Concrete manifestations in the toolkit:

1. **`pipeline-state.json` is the per-REQ runtime registry**. Not a global cross-repo database. It lives in the primary's spec directory and carries a `repos` block (worktree path, branch, PR URL, merge state per touched repo). Every phase reads worktree paths from this file — never from cwd inference. This lets a mid-pipeline context compression resume exactly where it left off, including the current repo and task.

2. **Worktrees are keyed by REQ number in every touched repo** (`<repo-path>/.worktrees/REQ-xxx`), same branch name across repos. Concurrent cross-repo REQs can't collide on the same sibling because REQ numbers are globally unique. `/sprint` confirms this up front in its pre-flight.

3. **Task routing by `repo:` frontmatter**. Tasks declare which repo they target; `/proceed` Phase 4 cd's into that repo's worktree before implementing. Files stay in their declared repo — `/validate` enforces this. This keeps per-repo CI pipelines independent and makes per-repo code review tractable (one reviewer pair per repo's PR).

4. **Service config lives in primary's `.adlc/config.yml` under `services:`, keyed by repo id**. Removed the hardcoded service table in `/canary`. Repos that deploy differently (iOS → TestFlight, infra → Terraform) omit entries and are handled in `/wrapup` Step 6.

5. **Consumer skills got shallow cross-repo awareness**. `/status` scans sibling state files to show inbound cross-repo work. `/sprint` delegates cross-repo mechanics to each `/proceed` it launches. `/bugfix` supports `repo:` / `touched_repos:` for fix routing. None of these tried to own cross-repo orchestration themselves — that's `/proceed`'s job.

## Counter-pattern to avoid

Don't pick a fixed "coordination repo" to host every cross-repo REQ. The appeal is centralization, but it creates a second-class repo experience for features that happen to span two of the non-coordination repos, and it forces every repo-local REQ into a decision tree ("do I put this here or in the coordination repo?"). Per-REQ primary keeps the mental model simple: REQs live where you start them.

## Counter-pattern #2: flat paths in configs

An early sketch used absolute paths in `config.yml` for sibling repos. This broke as soon as a teammate cloned the repos to a different parent directory. Use **relative paths from each repo's root** (`path: ../admin-api`) and let the skill resolve them at runtime. Absolute paths should be computed and stored in `pipeline-state.json` when the pipeline starts, not baked into the config.

## Related

- PR [adlc-toolkit#18](https://github.com/atelier-fashion/adlc-toolkit/pull/18) — initial cross-repo support in `/proceed`, `/architect`, `/validate`, `/wrapup`, `/canary`, `/init`, templates
- Per-repo adoption PRs: admin-api#82, infrastructure#50, atelier-fashion#497, atelier-web#68
