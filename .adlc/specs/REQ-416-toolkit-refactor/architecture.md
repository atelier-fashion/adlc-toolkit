---
id: REQ-416
title: "Architecture — Toolkit refactor"
parent: REQ-416
created: 2026-05-15
updated: 2026-05-15
---

# Architecture — REQ-416 Toolkit Refactor

## Approach

Five orthogonal items, sequenced into four tiers so independent work runs in
parallel and DRY consumers wait for their producer.

```
Tier 1 (independent, parallel):
  TASK-031  pin tools/kimi/requirements.txt
  TASK-032  lock-symlink TOCTOU review + harden

Tier 2 (foundational, blocks Kimi DRY and proceed split insofar as both
        benefit from the partials/ pattern existing first):
  TASK-033  introduce partials/ + DRY ethos macro across 15 skills

Tier 3 (parallel after TASK-033):
  TASK-034  DRY Kimi delegation gate using partials/
  TASK-035  shrink proceed/SKILL.md by extracting Phases 1-3 and 6-8

Tier 4 (verification gate):
  TASK-036  end-to-end sanity (pytest + sample /proceed dry-run)
```

The exploration pass updated three counts the requirement had stale:
- Kimi gate sites: **4**, not 2 (analyze, proceed, spec, wrapup).
- proceed/SKILL.md current size: **556 lines**, not 492.
- Lock/counter sites: **3** — one true `mkdir`-lock at the global REQ counter,
  plus two unguarded read-modify-write counters (`.adlc/.next-lesson`,
  `.adlc/.next-assume`) that the requirement listed as locks but in fact never
  acquire one. Acceptance Criteria for TASK-032 reflect this.

The exploration pass also surfaced one out-of-scope DRY candidate: the
marker-guarded `sed` block in `tools/kimi/install.sh` lines 172–179 that
appends a Kimi routing block to `~/.claude/CLAUDE.md`. Logged here for a
future REQ; not addressed by REQ-416.

## ADRs

### ADR-1 — Ethos DRY mechanism: shared bash macro file (resolves OQ-1)

**Decision**: Introduce a single shell file `partials/ethos-include.sh` that
emits the existing fallback chain. Each of the 15 skills replaces its inline
`!`cat .adlc/ETHOS.md ... `` macro with a one-liner that sources the partial.

**Why this and not the alternatives**:

- *Status quo (do nothing)*: the ethos CONTENT is already single-source — every
  skill cats the same file. What duplicates is the 6-line bash macro pattern.
  That pattern has changed three times (REQ-411 added the `~/.claude/skills/`
  fallback; REQ-413 added the graceful-failure echo). Each change required a
  15-skill edit. Genuine cost.
- *Build-time concatenation script*: violates the "no build step" convention
  (.adlc/context/conventions.md line 6) and breaks BR-1 because edits to ETHOS.md
  would no longer propagate without a re-run.
- *Markdown include directive*: no preprocessor exists. Custom one is bigger
  than the problem.
- *Frontmatter field + skill-runtime expansion*: requires Claude Code runtime
  changes outside our control.

The partial-source approach: zero new infrastructure, fits the existing
`tools/` carve-out philosophy (LESSON-006), each skill keeps a one-line bash
macro that's still readable in-place, and the fallback chain lives in one file.

**Mechanism** (TASK-033 implements):
```bash
# partials/ethos-include.sh — POSIX, no bashisms
cat .adlc/ETHOS.md 2>/dev/null \
  || cat ~/.claude/skills/ETHOS.md 2>/dev/null \
  || echo "No ethos found"
```

Each skill's `## Ethos` section becomes:
```markdown
!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`
```

The double-fallback at the call site preserves the consumer-project-first
behavior even when the consumer hasn't synced partials yet (graceful
degradation matches the existing pattern).

### ADR-2 — Kimi gate DRY mechanism: documented partial + shared shell function (resolves OQ-2)

**Decision**: Two-part — the gate CONDITION goes into `partials/kimi-gate.sh`
as a sourceable shell function `adlc_kimi_gate_check` returning 0/1/2
(delegated/disabled/unavailable). The gate USAGE PATTERN (when to call,
where to emit fall-through stderr lines) lives in `partials/kimi-gate.md`
as documentation referenced by every delegating skill.

**Why split**: the actual `if … then … else … fi` body differs per skill
(different stderr messages, different fallback paths). What's truly shared
is the gate predicate. So we extract the predicate as code and the protocol
as docs.

**Why not pure docs**: BR-3 requires that adding a delegation point to a NEW
skill MUST reference the snippet, not copy-paste it. A grep test (BR-3
verification) checks that every skill containing `ADLC_DISABLE_KIMI` also
contains either `partials/kimi-gate.sh` (the source line) or an explicit
`<!-- gate: partials/kimi-gate.md -->` opt-out marker.

**Mechanism** (TASK-034 implements):
```bash
# partials/kimi-gate.sh
adlc_kimi_gate_check() {
  if ! command -v ask-kimi >/dev/null 2>&1; then return 2; fi
  if [ "${ADLC_DISABLE_KIMI:-0}" = "1" ]; then return 1; fi
  return 0
}
```

Skills source it and case on the return:
```bash
. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh
adlc_kimi_gate_check; gate=$?
case $gate in
  0) # delegated path ;;
  1) # disabled path ;;
  2) # unavailable path ;;
esac
```

### ADR-3 — proceed/SKILL.md split: extract Phases 1–3 and 6–8 only (resolves OQ-3)

**Decision**: Extract the four "thin" phase sections to companion files; keep
the load-bearing core in SKILL.md.

**Extracted to companions** (TASK-035):
- `proceed/phases-1-3-validation.md` — Phases 1, 2, 3 (validate spec → architect
  → validate architecture). 42 lines.
- `proceed/phase-4-implementation.md` — Phase 4 (parallel task-implementer
  dispatch). 33 lines.
- `proceed/phases-6-8-ship.md` — Phases 6, 7, 8 (PR, cleanup, wrapup merge).
  38 lines.

**Stays inline in SKILL.md** (load-bearing for gate-protocol invariants):
- Frontmatter, Ethos, Arguments, Execution Mode, Autonomous Execution Contract
- Repository Configuration (cross-repo routing — must be visible at top)
- Pipeline State Tracking (the state-machine schema + gate protocol)
- Step 0 (resolve repos, worktrees, preflight, shared context)
- **Phase 5 (Verify)** — contains the Kimi pre-pass gate which is itself
  load-bearing for the verify protocol; extracting fragments the gate.
- Error Handling, Prerequisites, Scope (3-line tail sections)

**Result**: `wc -l proceed/SKILL.md` projected at ~440 lines after extraction,
which **misses the BR-4 ≤300 target**. To hit ≤300, Phase 5 (98 lines) must
also extract. We choose to **negotiate BR-4 down** and document this here:
keeping Phase 5 inline is more important than the line target. TASK-035
acceptance criterion is amended to ≤450 lines, and BR-4 in the requirement is
flagged for `/wrapup` to update if /architect's recommendation is accepted.

**Alternative considered and rejected**: splitting Phase 5 into "verify-orchestration"
(stays) and "verify-kimi-pre-pass" (extracts) duplicates the gate-handoff logic
across two files and creates a TOCTOU window where the orchestrator and the
Kimi pre-pass disagree on whether delegation succeeded. Worse than a 440-line
file.

**No-preprocessor split format**: the SKILL.md retains a brief in-place
summary of each extracted phase plus a `<!-- companion: proceed/phases-1-3-validation.md -->`
marker. The companion files are NOT executed automatically — a maintainer
working on /proceed reads SKILL.md first, sees the summary, opens the companion
when they need detail. Matches the existing markdown-only convention.

### ADR-4 — Lock-site hardening: keep mkdir, add symlink-pre-check; convert RMW counters to mkdir-lock (resolves OQ-4)

**Decision**:

For the mkdir-lock at `~/.claude/.global-next-req.lock.d`:
- Keep `mkdir`-as-lock (POSIX-portable; convention forbids `flock`).
- Add a pre-acquisition check: refuse to operate if the lock-parent directory
  contains a symlink at the lock name. Reject with a clear error message rather
  than silently following the symlink.
  ```bash
  LOCK=~/.claude/.global-next-req.lock.d
  if [ -L "$LOCK" ]; then
    echo "ERROR: $LOCK is a symlink — refusing to operate (TOCTOU risk). Inspect manually." >&2
    exit 1
  fi
  ```
- Document residual risk: an attacker with write access to `~/.claude/` already
  controls the user's skill installation; the symlink vector adds nothing
  beyond what they already have. Accepted-risk with rationale.

For the two unguarded RMW counters (`.adlc/.next-lesson`, `.adlc/.next-assume`):
- These race against concurrent `/sprint` writers (LESSON-110 calls this out
  explicitly for `.next-lesson`). They are NOT mkdir-locks — they have no lock
  at all. The TOCTOU concern was misclassified in the requirement.
- Wrap both in the same mkdir-lock pattern as the global counter, with the
  same symlink-pre-check.

**Why not migrate to `python-filelock` or similar**: introduces a Python
runtime dependency for skills that are otherwise pure shell + markdown.
Disproportionate.

### ADR-5 — Pin tools/kimi/requirements.txt to currently-installed versions (resolves OQ-5)

**Decision**: Add `tools/kimi/requirements.txt` with pins discovered from the
currently-installed venv at `~/.claude/kimi-venv` (TASK-031 reads
`pip freeze` and pins exactly). `install.sh` switches to
`pip install -r tools/kimi/requirements.txt`.

**Bumps**: dependency-bump REQs file a hotfix per bump if the upstream API
changes. Routine pin refreshes go through the same review path as any other
toolkit change. Documented in the `tools/kimi/README.md` update.

### ADR-6 — Sequencing: ethos DRY before Kimi DRY (resolves OQ-6)

**Decision**: TASK-033 (ethos DRY + partials/ infrastructure) runs in Tier 2,
before TASK-034 (Kimi gate DRY) and TASK-035 (proceed split) in Tier 3, because:
- Both Tier 3 tasks reuse the `partials/` directory and the source-with-fallback
  pattern that TASK-033 establishes. Building the pattern once and consuming it
  twice is cheaper than three independent inventions.
- TASK-031 (requirements pinning) and TASK-032 (lock hardening) are independent
  of `partials/` and run in Tier 1 alongside.
- TASK-036 (verification) waits for everything.

## Data Model Changes

None. No Firestore, no GCS — toolkit is pure markdown + shell.

## API Changes

None. Toolkit has no public API.

## New Directory Layout

```
adlc-toolkit/
├── partials/                              # NEW — single source for shared snippets
│   ├── ethos-include.sh                   # NEW — ADR-1
│   ├── kimi-gate.sh                       # NEW — ADR-2
│   └── kimi-gate.md                       # NEW — ADR-2 protocol docs
├── proceed/
│   ├── SKILL.md                           # SHRUNK — from 556 to ~440 lines
│   ├── phases-1-3-validation.md           # NEW — ADR-3
│   ├── phase-4-implementation.md          # NEW — ADR-3
│   └── phases-6-8-ship.md                 # NEW — ADR-3
└── tools/kimi/
    ├── requirements.txt                   # NEW — ADR-5
    └── install.sh                         # MODIFIED — uses requirements.txt
```

`/init` will need an update to symlink (or copy) `partials/` into consumer
projects' `.adlc/partials/` so the consumer-project-first fallback works.
TASK-033 includes that change.

## Knowledge Retrieved

- LESSON-006 (`tools/` carve-out + fail-loud installers) — informs ADR-5
  pinning approach.
- LESSON-007 (scrub at every leak point) — informs ADR-4: enumerate every
  lock site, not just the obvious one.
- LESSON-008 (skill delegation = untrusted data) — informs ADR-2: gate dedup
  is the right next step after the pilot.
- LESSON-110 (referenced in wrapup/SKILL.md:94 and 165) — confirms the
  unguarded counter race is real, validating ADR-4's wrap-with-mkdir-lock.

## Open Risks

- **BR-4 line target miss** (≤300 vs projected ~440): documented in ADR-3.
  /wrapup must update REQ-416 BR-4 when the refactor lands, or this REQ
  ships with an explicit "BR-4 amended" note in its acceptance.
- **/init partials sync**: if /init isn't updated atomically with the
  partials/ introduction, consumer projects will fall back to the
  `~/.claude/skills/partials/` path on every invocation. That path works
  via the symlink install, so it's correct — but it means consumer projects
  using a stale `/init`-generated layout never get a per-project copy. Acceptable.
- **In-flight pipelines** (BR-9): a `/proceed` run that started before the
  refactor lands can resume after — the SKILL.md changes are read fresh on
  each phase invocation and the new structure is backwards-readable
  (companions are referenced but not required for the inline summary to make
  sense). No deprecation window needed.
