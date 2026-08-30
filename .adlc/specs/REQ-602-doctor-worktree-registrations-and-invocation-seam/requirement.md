---
id: REQ-602
title: "Doctor: worktree-registration check, and an invocation seam that runs doctor before someone suspects a problem"
status: draft
deployable: false
created: 2026-08-30
updated: 2026-08-30
component: "adlc/doctor"
domain: "adlc"
stack: ["python", "bash", "git"]
concerns: ["reliability", "silent-failure", "developer-experience", "structural-enforcement", "observability"]
tags: ["doctor", "worktree", "git-worktree", "prunable", "worktree-repair", "symlink", "session-start-hook", "launchagent", "remediation", "health-check", "preflight"]
---

## Description

On 2026-08-29/30 this machine's `~/Documents` stopped being a symlink into iCloud
Documents and became an empty local directory; everything moved to
`~/GitHub/`. Four things broke at once, all silently:

1. `~/.claude/skills` and `~/.claude/agents` became dangling symlinks. Every
   partial resolved through the two-level fallback
   `. .adlc/partials/<x>.sh 2>/dev/null || . ~/.claude/skills/partials/<x>.sh`
   hit a dead path, in every Claude Code session on the machine.
2. 18 agent types disappeared from sessions, signalled only by an ambient
   "these agent types are no longer available" notice with no cause.
3. 10 git worktree registrations across `adlc-toolkit` and a consumer repo went
   `prunable` while every worktree directory was alive at the new path. The
   registrations were wrong **only in their path prefix**; `git worktree repair`
   fixed all of them with no loss.
4. `~/bin/adlc` (and, still unfixed as of this writing, `~/bin/adlc-read`) kept
   pointing at the dead path, so the CLI itself was broken.

**`adlc doctor` was already capable of detecting items 1 and 4.** When it was
finally run, it caught the symlink and shim failures correctly, with runnable
remediation strings. The checks were right. This REQ does not rebuild them.

Two gaps remain, and they are the ones that actually cost a day of silent
breakage:

**Gap 1 — nothing checks worktree registrations.** No entry in
`tools/adlc/checks.py` `REGISTRY` notices that `git worktree list` reports
entries marked `prunable`. Worse, the two cases that need *opposite* remedies are
not distinguishable from git's own output: a worktree whose directory moved
(remedy `git worktree repair <path>` — non-destructive, keeps the work) and one
whose directory is genuinely gone (remedy `git worktree prune` — destructive)
produce a byte-identical reason string. Verified on git 2.50.1, both cases:

```
prunable gitdir file points to non-existent location
```

Getting this backwards is not a cosmetic error. Verified empirically: running
`git worktree prune` against the moved case deletes the admin record, after which
`git worktree repair` fails outright (`.git file does not reference a
repository`), the entry vanishes from `git worktree list`, and `git status`
inside the surviving directory is fatal — `not a git repository`. Uncommitted
files remain on disk as plain files with no branch, no index, and no path back.
`git worktree prune --dry-run -v` lists the moved and the gone worktree
identically, so an operator who pastes prune first destroys live checkouts
without warning. A check that emits the wrong remediation here is worse than no
check.

**Gap 2 — doctor is manual-only, so it ran a day late.** Nothing invokes it: no
hook, no skill preflight, no session-start seam. `install.sh` calls it once at
install time and never again. This is the LESSON-574 shape — that lesson was
written about a hard CI gate on an unrequired schedule trigger that stayed red
for five weekly runs because no human was forced to see it, and its first
sentence generalizes exactly: *"A gate whose failure nobody is forced to see is
not a gate."* A diagnostic that only runs when someone already suspects a problem
is the same object viewed from the other side: it cannot shorten the interval
between breakage and discovery, because discovery is its trigger.

This REQ adds the missing check, extends shim coverage to the shim this session
found still broken, fixes a false-positive that would poison any automatic seam,
and specifies the seam itself with the options weighed. Doctor stays read-only
throughout.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| WorktreeEntry | registered_path | string | absolute path as recorded in the admin record / reported by `git worktree list --porcelain` |
| WorktreeEntry | admin_name | string | basename of `<git-common-dir>/worktrees/<name>`; the identity key |
| WorktreeEntry | prunable_reason | string | git's own reason string, or "" when git did not mark it prunable |
| WorktreeEntry | locked | boolean | true when the porcelain entry carries a `locked` line |
| WorktreeEntry | classification | enum | `healthy` / `moved` / `unlocated` — never a confident `gone` (BR-4) |
| WorktreeEntry | located_path | string | required when classification is `moved`; the proven current path. Empty otherwise |
| RepoScope | git_common_dir | string | absolute; the dedupe key across the cwd repo and the toolkit repo |
| SessionPreflight | check_subset | list | the declared cheap/local/no-network check ids the seam runs (BR-9) |
| SessionPreflight | budget_ms | number | hard wall-clock ceiling; exceeded ⇒ abandon quietly (BR-11) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| worktree-registrations outcome | `adlc doctor` (manual, or via the seam) | per-repo counts by classification, the located paths for `moved`, and the ordered remediation |
| session preflight | Claude Code session start | nothing on all-pass; on failure, the failing check ids and their remediation lines |

### Permissions

Not applicable — doctor is a local read-only diagnostic with no actors or roles.

## Business Rules

### Gap 1 — the `worktree-registrations` check

- [ ] BR-1: A new check registered in `tools/adlc/checks.py` `REGISTRY` as id
      `worktree-registrations`, following the existing `Check` / `Result` /
      `CheckOutcome` shape in `doctor.py`. It performs no network I/O and no
      mutation of any kind — it MUST NOT invoke `git worktree repair`,
      `git worktree prune`, or any other mutating git subcommand, including with
      `--dry-run`. It reports; the operator acts. (informed by REQ-519 BR-4)

- [ ] BR-2: An entry is **suspect** when EITHER git marked it `prunable` in
      `git worktree list --porcelain`, OR its registered path does not exist on
      disk. The second disjunct is load-bearing, not redundant: verified on git
      2.50.1, a worktree that is `locked` **and** moved reports `locked` with no
      `prunable` line at all, and `git worktree prune` skips it — so a
      prunable-only trigger silently misses every locked worktree, which is
      precisely the class an operator deliberately marked as worth keeping.

- [ ] BR-3: An entry is classified `moved` **only** on positive evidence: a
      candidate directory was located whose `.git` is a **regular file** (a `.git`
      *directory* means an independent clone, not a linked worktree) containing a
      `gitdir:` pointer whose final two path components are
      `worktrees/<admin_name>` for this entry's `admin_name`.

- [ ] BR-4: Identity matching in BR-3 MUST compare the trailing
      `worktrees/<admin_name>` components, and MUST NOT require full-path or
      realpath equality of the `gitdir:` pointer. Verified: when the repository
      itself moves, the moved worktree's own `.git` file still names the **old**
      repo path, so a realpath comparison classifies every moved worktree as
      not-moved and hands the operator the destructive remedy. This rule is the
      single most important correctness constraint in the check.

- [ ] BR-5: Candidate location is a **bounded** search — no filesystem-wide walk.
      In order: (a) the registered path itself; (b) suffix-rebase against the
      repository's live root — for registered path `P` and live root `M`, try
      `M/<suffix>` for suffixes of `P` from longest to shortest, capped at a small
      fixed component depth. (b) is what resolves the incident case: the
      registrations were wrong only in their prefix, and the toolkit's own
      convention places worktrees at `<repo>/.claude/worktrees/<name>`.

- [ ] BR-6: An entry that is suspect but not proven `moved` is classified
      `unlocated`, **never** `gone`. The check has no cheap positive evidence for
      absence — "not found in a bounded search" does not establish "deleted" — and
      the reassuring-sounding class here is the one whose remedy is destructive.
      The fall-through must say "I could not locate this", not assert deletion.
      (informed by LESSON-581)

- [ ] BR-7: Remediation strings are copy-pasteable commands in the existing
      `checks.py` idiom, and name the correct command for the classification
      (informed by LESSON-572, REQ-519 BR-5):
      - `moved` → `git -C '<repo>' worktree repair '<path1>' '<path2>' …`, with
        the located paths substituted literally. No placeholders: a remediation
        containing an unfilled `<path>` is a fix-shaped comment, not a fix.
      - `unlocated` → `git -C '<repo>' worktree prune --dry-run -v   # review, then re-run without --dry-run`,
        mirroring the review-first idiom already used by `check_toolkit_clean`.

- [ ] BR-8: When both classifications are present in one repo, the remediation
      MUST order `repair` before `prune`, and the detail MUST state that pruning
      first destroys the moved entries too. `git worktree prune` cannot
      distinguish the cases any better than the reason string can — verified, its
      `--dry-run -v` output lists both — so the ordering is the only thing
      protecting the live checkouts.

- [ ] BR-9: `moved` entries FAIL the check. `unlocated`-only entries PASS, with
      the count and the `--dry-run` command carried in the **detail** string
      (`format_report` prints `remediation` only on FAIL). Rationale: `moved` is
      real breakage with a safe fix, while leftover registrations are ordinary
      cruft — and a check that goes red on cruft becomes a permanently-red gate
      that signals nothing once it is wired into the seam. (informed by
      LESSON-574)

- [ ] BR-10: Scope is the current working directory's repository **and**
      `profile.repo_root`, deduped by absolute git common dir (inside a worktree
      these differ as paths but share a common dir). SKIP-with-reason when
      neither is a git repository, following `check_forge`'s in-body SKIP pattern
      rather than `applies_to` — the relevant condition is cwd, which is not on
      `Profile`.

### Gap 2 — the invocation seam

- [ ] BR-11: A Claude Code `SessionStart` hook runs
      `adlc doctor --checks <declared-subset>`, reusing the `--checks` contract
      that already exists (REQ-519 BR-8) rather than adding a new doctor surface.
      The hook MUST NOT block or fail a session: it exits 0 unconditionally
      regardless of doctor's verdict, is bounded by an explicit wall-clock
      ceiling, and abandons quietly if exceeded.

- [ ] BR-12: The declared subset contains only checks that are **local and
      network-free**. Measured on this machine: the full registry takes **3.83 s**
      — dominated by `reservations`, which pushes a real probe ref to origin — while
      a local subset takes **0.063 s**. The network checks are categorically
      excluded from the seam, not merely deprioritized.

- [ ] BR-13: The subset is declared in exactly one place and consumed from there
      by the hook, the installer, and the docs. It MUST NOT be duplicated as a
      literal check-id list in more than one file. (informed by LESSON-019,
      LESSON-020)

- [ ] BR-14: **Zero false FAILs in the default session context** is a shipping
      precondition for BR-11, not a nice-to-have. Today `agents-symlink` FAILs in
      **every** worktree session: `doctor._detect_repo_root()` resolves to the
      worktree root, so the check demands `~/.claude/agents → <worktree>/agents`
      while the correct target is the main checkout's `agents/`. Verified in this
      very worktree. Wiring the current registry into a session hook without
      fixing this ships a gate that is red on day one — the exact failure
      LESSON-574 describes. The seam MUST NOT be enabled until the subset runs
      clean on a healthy machine from both a main checkout and a worktree.

- [ ] BR-15: The hook is silent on all-pass. It emits only when a check fails,
      and emits the failing check ids with their remediation lines verbatim — the
      remediation must reach an operator who can execute it. (informed by
      LESSON-572)

- [ ] BR-16: Any mutation of `~/.claude/settings.json` to install the hook is
      performed by `install.sh` under the existing fail-loud atomic contract
      (backup, temp-write, rename; malformed existing content produces an
      actionable message, never a traceback or silent overwrite), and is
      idempotent — a second run reports zero actions. (informed by REQ-519 BR-1,
      BR-2)

### Adjacent coverage gaps found while specifying this

- [ ] BR-17: `check_path_shims` is extended to probe **every** installed shim,
      not just `adlc`. Evidence: during this session's own retrieval step,
      `adlc-read` failed with
      `can't open file '/Users/brettluelling/Documents/GitHub/adlc-toolkit/tools/delegate/adlc-read'`
      — the same dead path, still live, and invisible to doctor because
      `check_path_shims` probes only `adlc`. The shim roster is derived from what
      the installer actually installs, not hardcoded a second time (BR-13's
      single-declaration rule). Delegation shims are SKIPped when delegation is
      not opted in, per the existing `delegate-gate` pattern.

- [ ] BR-18: A `partial-resolution` check verifies that the two-level partial
      fallback actually resolves for the known partial set — i.e. that for each
      partial, either `.adlc/partials/<name>.sh` or
      `~/.claude/skills/partials/<name>.sh` exists and is readable. This is the
      cheap capture of the "fail loudly in the fallback" idea without editing
      every call site (see Assumptions for why the call-site variant was not
      taken). It is a pure existence probe: it MUST NOT source any partial.

## Acceptance Criteria

- [ ] AC-1: With a real temp git repo, a real worktree created via
      `git worktree add`, and the worktree directory **actually moved** on disk
      (not mocked), `worktree-registrations` returns FAIL, classifies the entry
      `moved`, and emits a remediation containing
      `worktree repair` and the literal new path. Executing that remediation
      verbatim returns the check to PASS. No mock may stand in for the moved
      directory — the classification logic is the thing under test.
- [ ] AC-2: With the same fixture but the worktree directory **deleted**, the
      check classifies the entry `unlocated`, returns PASS (BR-9), and its detail
      names `prune --dry-run`. It MUST NOT emit a bare `git worktree prune` as
      the leading remediation.
- [ ] AC-3: A repo containing **both** a moved and a deleted worktree yields a
      remediation whose `repair` command precedes any `prune` command, and a
      detail that states pruning first would destroy the moved entry (BR-8).
- [ ] AC-4: The whole-repository-moved case is covered: a repo whose own root
      moved, carrying its `.claude/worktrees/*` children with it, is classified
      `moved` for every child. This is the incident's actual topology and the case
      BR-4 exists for — a realpath-equality implementation passes AC-1 and fails
      this one.
- [ ] AC-5: A worktree that is `locked` and moved is detected as suspect (BR-2),
      despite git emitting no `prunable` line for it.
- [ ] AC-6: A healthy repo with several live worktrees returns PASS with no
      suspect entries, and a non-git cwd with a non-git `repo_root` returns
      SKIP-with-reason — never FAIL.
- [ ] AC-7: The check adds no measurable time to a doctor run: on a repo with ~10
      worktrees it completes in well under 100 ms, and issues zero network calls
      (verifiable by running it with no network route).
- [ ] AC-8: `adlc doctor --checks worktree-registrations` runs only that check
      (the REQ-519 BR-8 preflight contract still holds for the new id).
- [ ] AC-9: `agents-symlink` passes from inside a git worktree on a healthy
      machine (BR-14). Verified by running doctor from both
      `<repo>` and `<repo>/.claude/worktrees/<name>` and getting the same verdict.
- [ ] AC-10: `path-shims` FAILs when `adlc-read` is present on PATH but points at
      a nonexistent target, with a remediation that returns it to PASS when
      executed (BR-17). Reproduces today's live breakage as a regression test.
- [ ] AC-11: `partial-resolution` FAILs when `~/.claude/skills` is a dangling
      symlink and no `.adlc/partials/` exists — the incident's exact
      configuration — and names the dead path in its detail (BR-18).
- [ ] AC-12: The seam's declared subset runs clean (all PASS or SKIP, zero FAIL)
      on a healthy machine from a main checkout **and** from a worktree, and
      completes within the BR-11 budget. This is the BR-14 gate; it is checked
      before the hook is enabled, not after.
- [ ] AC-13: With the hook installed, a session whose doctor subset FAILs still
      starts normally, and a session whose subset PASSes produces no output at
      all (BR-11, BR-15).
- [ ] AC-14: A second `install.sh` run after the hook is installed reports zero
      actions taken, and a pre-existing hand-edited `~/.claude/settings.json` with
      unrelated keys is preserved intact (BR-16).
- [ ] AC-15: All new tests live in `tools/adlc/tests/test_checks.py` and pass
      under `python3 -m pytest tools/adlc/tests`; `sh partials/tests/run.sh`
      continues to pass. This repo has no CI — these two suites are the only
      gates and are run as part of the change, not assumed. (informed by
      LESSON-582)

## External Dependencies

- None new. `git worktree list --porcelain`, `repair`, and `prune` are all in the
  git the toolkit already requires. No network, no new Python packages —
  `checks.py` stays pure standard library so doctor runs before/without the
  delegation venv.

## Assumptions

- **git version floor.** `prunable <reason>` in `git worktree list --porcelain`
  was verified on git 2.50.1 (Apple Git-155). The check should degrade to
  path-existence detection (BR-2's second disjunct) rather than crash on a git
  too old to emit it. The exact floor is an open question below.
- **The `.claude/worktrees/<name>` convention holds** for BR-5's suffix-rebase.
  Worktrees created outside the repo tree are located only if they happen to sit
  under the rebased root; they otherwise fall to `unlocated`, whose remediation
  is non-destructive by construction — the failure direction is safe.
- **The full call-site variant of the partial preflight was considered and not
  taken.** Making the fallback itself fail loudly means adding a third arm at
  every call site (~39 by LESSON-019's count) and updating
  `tools/lint-skills`'s canonical-literal set in the same change or the guard
  rots (LESSON-019 #1, LESSON-020 #2). Given a session-start seam that fires
  constantly, its marginal value is catching a break *mid-session* — a narrow
  window for a wide, regression-prone edit. BR-18 takes the cheap capture
  instead. If mid-session breakage proves real, the call-site version is a
  follow-up.
- **The periodic LaunchAgent option was considered and deferred.** Its only
  advantage over the session hook is affording the network checks, and it has no
  delivery channel of its own — a LaunchAgent writing a log nobody reads
  reproduces LESSON-574's failure exactly, and giving it a channel means building
  the session seam anyway. It is also macOS-only, while REQ-519 committed to
  Linux parity. If the network checks turn out to matter, it becomes a small
  follow-up reusing the seam's delivery path.
- **Doing nothing was considered.** The incident's repair cost was ~2 minutes
  once found; the cost was the day of silence, not the fix. That bounds how much
  machinery is justified — and is why this REQ specifies one cheap hook rather
  than a monitoring subsystem.
- Id REQ-602 was allocated with remote verification (`ADLC_ALLOC_DEGRADED=0`).

## Open Questions

- [ ] **Is `unlocated` → PASS (BR-9) the right call?** It keeps the gate credible
      once wired into the seam, but it means ordinary worktree cruft never turns
      doctor red and may accumulate unnoticed. The alternative — FAIL on both —
      is louder but risks the permanently-red gate LESSON-574 warns about.
      Proposed: PASS-with-detail as specified; reviewable.
- [ ] **What is the minimum git version** that emits `prunable` in
      `--porcelain`, and should the check warn when running under an older git
      rather than silently relying on BR-2's path-existence fallback?
- [ ] **Should BR-10's scope be widened** to all repos known to the machine (the
      incident spanned two), or does cwd + toolkit root cover the realistic
      invocation pattern? Proposed: cwd + toolkit root; widening needs a repo
      registry that does not currently exist.
- [ ] **Is `SessionStart` the right hook event**, and does it fire per Claude Code
      session in the way BR-11 assumes on this version? This needs confirming
      against the installed Claude Code before BR-16 writes anything to
      `~/.claude/settings.json`.
- [ ] **Should `~/.claude/settings.json` (user-level, affects every project) be
      the install target**, or should the hook be project-level via `/init`?
      User-level matches the incident's machine-wide blast radius; project-level
      is less invasive. Proposed: user-level, installed by `install.sh` with
      explicit opt-out.

## Out of Scope

- Rebuilding or redesigning any existing check. `skills-symlink`,
  `agents-symlink`, `path-shims`, `toolkit-clean` and the rest already work;
  this REQ adds `worktree-registrations` and `partial-resolution`, extends
  `path-shims` coverage (BR-17), and fixes one false positive (BR-14).
- Making doctor mutate anything. Auto-repair — even for the provably-safe
  `moved` case — is explicitly excluded; doctor reports and the operator acts.
- The periodic LaunchAgent / systemd timer (deferred, see Assumptions).
- The full call-site partial-fallback rewrite (deferred, see Assumptions).
- Recovering work from worktrees already destroyed by a mis-ordered prune. This
  REQ prevents the mistake; it does not undo it.
- Windows.

## Retrieved Context

- LESSON-572 (lesson, score 13): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 12): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion
- LESSON-581 (lesson, score 7): A classifier's fall-through default is a claim about every input it has never seen
- LESSON-582 (lesson, score 7): bash 3.2 cannot parse a `case` statement inside `$( )`
- LESSON-571 (lesson, score 7): A retrieval filter is half of a read/write contract
- BUG-194 (bug, score 7): /spec Step 1.6 spec-corpus status filter admits no status the pipeline writes
- LESSON-019 (lesson, score 7): A literal-presence guard silently rots when the thing it guards moves behind indirection
- REQ-263 (spec, score 7): Enforce per-REQ unique worktree paths in /sprint dispatch and /proceed Phase 0
- LESSON-575 (lesson, score 6): Squash is not a neutral merge style
- LESSON-437 (lesson, score 6): Network operations inside a lock must be forced non-interactive
- LESSON-438 (lesson, score 6): git push outcomes classify by literal stderr markers
- REQ-519 (spec, score 6): One-Command Installer and `adlc doctor` Health Check
- LESSON-020 (lesson, score 6): A shell function shared across SKILL.md steps must be a sourced partial
- REQ-381 (spec, score 6): Drop /bugfix Phase 6 (canary) and fix dangling Phase 7.5 cross-references
- REQ-425 (spec, score 6): Pre-merge detection of corrupted shell constructs in SKILL.md files

_Note: the delegated body-read failed (`adlc-read` is broken with the same dead
path as `~/bin/adlc` — see BR-17) and the fallback direct read was used, per
`/spec` Step 1.6's documented fallback path._
