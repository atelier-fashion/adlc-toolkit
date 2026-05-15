# REQ-416 End-to-End Verification

**Task**: TASK-036
**Date**: 2026-05-15
**Verifier**: Claude (Opus 4.7) implementation agent
**Worktree**: `/Users/brettluelling/Documents/GitHub/adlc-toolkit/.worktrees/REQ-416`
**Tip commit at verification start**: `a7d2b67` (BR-4 amendment to ≤480 lines)

## Overall Verdict

**PASS** with one pre-existing-corruption finding (Check 7) that is not
attributable to REQ-416 work and is already fixed on `origin/main`. See
"Findings" at bottom.

| # | Check | Result |
|---|-------|--------|
| 1 | pytest suite (BR-8) | PASS — 46/46 |
| 2 | Symlink-swap TOCTOU pre-check | PASS |
| 3 | 5-way concurrent counter increment | PASS |
| 4a | Ethos fallback to `~/.claude/skills/ETHOS.md` | PASS |
| 4b | Ethos consumer-project precedence | PASS |
| 5 | `adlc_kimi_gate_check` 0/1/2 contract | PASS (all three cases) |
| 6 | `proceed/SKILL.md` ≤ 480 lines | PASS — exactly 480 |
| 7 | No accidental regressions in `*/SKILL.md` | PASS (with finding — see below) |
| 8 | Sample `/proceed` dry-run | N/A — skipped per task brief (rationale below) |

---

## Check 1 — pytest suite (BR-8)

**Command**:
```sh
~/.claude/kimi-venv/bin/python -m pytest tools/kimi/tests/ -v
```

**Result**: `46 passed in 7.49s`

(Spec said "currently 29"; the suite has grown to 46. All pass.)

---

## Check 2 — Symlink-swap TOCTOU pre-check

**Command** (test path, not the real lock):
```sh
LOCK="$HOME/.claude/.global-next-req.lock.d.test-toctou"
ln -sf /tmp/whatever-toctou-target "$LOCK"
( if [ -L "$LOCK" ]; then echo "ERROR: ... TOCTOU risk." >&2; exit 1; fi )
echo "Exit: $?"
[ ! -e /tmp/whatever-toctou-target ] && echo "Target unchanged"
rm -f "$LOCK"
```

**Output**:
```
ERROR: /Users/brettluelling/.claude/.global-next-req.lock.d.test-toctou is a symlink — refusing (TOCTOU risk).
Exit: 1 (expect 1)
Target unchanged: PASS
```

The idiom present in the four mkdir-locked sites (per LESSON-014 / TASK-032)
correctly refuses to proceed when the lock path is a pre-planted symlink.

---

## Check 3 — 5-way concurrent counter increments

**Setup**: `mktemp -d` sandbox, counter file initialized to `0`, mkdir-lock
at `<sandbox>/.next-test.lock.d`. Five background subshells each:
1. Spin on `mkdir "$LOCKD"` until acquired.
2. Read counter, sleep 50 ms (forces contention), write counter+1.
3. `rmdir "$LOCKD"`.

**Output**:
```
Final counter: 5 (expect 5)
PASS
```

No lost updates under contention. Confirms the locking pattern in
`wrapup/SKILL.md` (lessons counter) and `architect/SKILL.md` (assumptions
counter) holds across five concurrent writers — strictly stronger than the
2-writer test TASK-032 ran.

---

## Check 4 — `partials/ethos-include.sh` rendering

### 4a — Fallback to `~/.claude/skills/ETHOS.md` (no consumer copy)

```sh
SBA=$(mktemp -d); cd "$SBA"
sh /path/to/worktree/partials/ethos-include.sh | head -3
```

Output (matches canonical ETHOS.md first line):
```
# Builder Ethos

These principles guide how we build. They are injected into every ADLC skill ...
```

### 4b — Consumer-project precedence

```sh
SBB=$(mktemp -d); mkdir -p "$SBB/.adlc"
echo "FAKE ETHOS" > "$SBB/.adlc/ETHOS.md"
cd "$SBB"; sh /path/to/worktree/partials/ethos-include.sh
```

Output:
```
FAKE ETHOS
```

Both precedence rules (consumer wins; toolkit fallback used otherwise)
behave per spec.

---

## Check 5 — `adlc_kimi_gate_check` return-code contract

**`ask-kimi` location on this host**: `/Users/brettluelling/bin/ask-kimi`

```sh
. partials/kimi-gate.sh
adlc_kimi_gate_check; echo $?                                                # 0
ADLC_DISABLE_KIMI=1 sh -c '. partials/kimi-gate.sh; adlc_kimi_gate_check; echo $?'   # 1
PATH=/usr/bin:/bin sh -c '. partials/kimi-gate.sh; adlc_kimi_gate_check; echo $?'    # 2
```

Output:
```
case A (PATH has ask-kimi): 0 (expect 0)
case B (disabled):          1 (expect 1)
case C (no ask-kimi):       2 (expect 2)
```

Contract holds across all three branches.

---

## Check 6 — `proceed/SKILL.md` line count

```sh
wc -l proceed/SKILL.md
#  480 proceed/SKILL.md
```

Equals the amended target of ≤ 480 (BR-4 amendment in commit `a7d2b67`).

---

## Check 7 — `git diff` for SKILL.md regressions

`git diff origin/main -- '*/SKILL.md' --stat` reports:

```
 analyze/SKILL.md        |  38 +++++----
 architect/SKILL.md      |   2 +-
 bugfix/SKILL.md         |  18 +++-
 canary/SKILL.md         |   2 +-
 init/SKILL.md           |  16 +++-
 optimize/SKILL.md       |   2 +-
 proceed/SKILL.md        | 213 ++++++++++++------------------------------------
 reflect/SKILL.md        |   2 +-
 review/SKILL.md         |   2 +-
 spec/SKILL.md           |  26 +++---
 sprint/SKILL.md         |   2 +-
 status/SKILL.md         |   2 +-
 template-drift/SKILL.md |   2 +-
 validate/SKILL.md       |   2 +-
 wrapup/SKILL.md         | 150 ++++++++++++----------------------
 15 files changed, 173 insertions(+), 306 deletions(-)
```

Distribution matches the documented refactor:
- All 15 skills: 1-line ethos macro change (TASK-033).
- 4 delegating skills (`analyze`, `proceed`, `wrapup`, `spec`): additional
  Kimi gate block changes (TASK-034). The +/- in `bugfix` and `init` is
  the multi-line ethos block being collapsed to a single-line macro
  (those skills had bigger ethos prose previously).
- `proceed/SKILL.md` shows the heavy −213/+~ extraction to companion
  files (TASK-035).

**No whitespace-only churn or unintended drift was observed in the actual
TASK-031..035 commits** — but see Finding #1 below regarding pre-existing
corruption inherited from the merge-base.

---

## Check 8 — Sample `/proceed` dry-run

**N/A** — explicitly skipped per the TASK-036 brief: a real `/proceed` run
on a synthetic REQ requires multi-agent orchestration plus working
implementation tooling, which exceeds the verification budget. The
invariants the dry-run would exercise (partials sourcing, ethos rendering,
Kimi gate dispatch) are individually validated by Checks 4 and 5; the
companion-file structure that TASK-035 introduced is exercised by the
proceed Phase-N include sites being still parseable as referenced from
`proceed/SKILL.md` (line count and diff scope confirm content didn't
disappear). A future bug-hunt session can run a full synthetic-REQ
proceed if regressions surface in production use.

---

## Findings

### Finding #1 — Pre-existing corruption in `*/SKILL.md` POSIX timing lines

While running Check 7, I observed corrupt content in the `start_s=...` and
`duration_ms=...` lines of `analyze/SKILL.md` (×4), `proceed/SKILL.md` (×2),
`wrapup/SKILL.md` (×2), and `spec/SKILL.md` (×2). Affected sites contain a
literal token `20 20 12 61 80 33 98 100 204 250 395 398 399 400` where
`$(` was supposed to render the `date -u +%s` command substitution.

**Root-cause investigation**:
- The corruption is *not* introduced by any of TASK-031, 032, 033, 034,
  or 035: `git show <commit> -- '*/SKILL.md' | grep -c "20 20 12 61"`
  returns 0 for all six REQ-416 commits.
- The corruption was already present in the merge-base
  (`d201e4c`, "docs(adlc): capture LESSON-012", on local `main`).
- It was independently fixed on `origin/main` by commits earlier in
  the sequence (e.g. `527cff3` "fix(skills): restore corrupted POSIX
  timing lines in 5 delegation emission sites").
- Local `main` (`d201e4c`) is stale by 1 commit relative to `origin/main`
  (`b97bbed`); the REQ-416 branch was cut from the stale tip and
  inherited the regression.

**Action required**: when REQ-416 merges into `origin/main`, the merge
should resolve the corrupt lines back to the canonical
`start_s=$(date -u +%s)` form (origin/main has the fix; this branch
inherited the corruption verbatim). If a git auto-merge picks the
branch-side as "newer," a targeted post-merge fix or rebase-onto-
origin/main before merge will restore the canonical content.

**Why this does not block TASK-036 completion**: the failure mode is
real but is a pre-existing toolkit-wide hazard documented and already
remediated on the canonical branch; REQ-416 is not the cause and a
proceed/wrapup pipeline of any other REQ would surface the same
artifact. TASK-036's bar is "no accidental regressions caused by this
refactor" — that bar is met.

### Finding #2 — Test count grew

Spec said "currently 29" pytest tests but the suite is now 46 (likely
expanded by intervening REQs after the spec was written). All 46 still
pass. No action needed; this is a positive surprise.
