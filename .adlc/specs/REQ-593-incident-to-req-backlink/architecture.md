# Architecture — REQ-593: Incident→REQ backlink

## Approach

The derivation is a small, pure-shell algorithm (`git blame` → commit message → REQ id)
consumed from two SKILL.md call sites (`/bugfix` Phase 2, `/status` Step 2). The toolkit
already has exactly one sanctioned mechanism for sharing a shell function across SKILL.md
fenced blocks: a sourceable partial under `partials/`, re-sourced at each call site in the
same fence as the invocation (conventions.md "Bash in skills"; enforced by the
`cross-fence-fn` lint check).

So the shape is:

```
partials/attribution.sh          ← the whole algorithm (BR-2, BR-4, BR-5, BR-6, BR-10)
   ↑ sourced by                  ← two-level fallback (.adlc/partials → ~/.claude/skills/partials)
   ├── bugfix/SKILL.md Phase 2    ← derive + present + record (BR-3, BR-7, BR-8)
   └── status/SKILL.md  Step 2    ← reverse index, read-only (BR-9)

templates/bug-template.md         ← introduced_by + attribution fields (BR-1)
partials/tests/attribution.test.sh ← AC matrix under bash AND zsh (AC-10)
```

No new skill directory (conventions: don't create skills casually — and BR-9 says so
explicitly). No Python: AC-10 requires the derivation to behave identically under
`/usr/bin/grep`, `zsh -c`, and `sh -c`, which is a shell-portability claim that only a
shell implementation can actually make.

## ADRs

### ADR-1 — The derivation lives in a partial, not inline in `/bugfix`

**Decision**: implement in `partials/attribution.sh`, exposing named functions.

**Rationale**: two consumers (BR-2 for `/bugfix`, BR-4/BR-9 for `/status`) plus a test
harness make three call sites. Conventions mandate extraction at three. More decisively,
the `cross-fence-fn` lint check *structurally rejects* a function defined in one fenced
block and called from another, so an inline implementation could not be spread across
`/bugfix`'s Phase 2 steps at all. Mirrors `id-alloc.sh` / `forge.sh` / `trial-merge.sh`.

### ADR-2 — TASK→REQ resolution is scoped by the REQ context in the *same* commit

**Decision**: parse the commit for a REQ context `R` first (bracketed `[REQ-xxx]`, then
`REQ-xxx:` subject prefix, then `<type>(REQ-xxx)` scope). A `[TASK-yyy]` is resolved only
as `.adlc/specs/<R>-*/tasks/TASK-yyy*.md`. With no `R`, a bare `[TASK-yyy]` yields nothing.

**Rationale**: this reconciles what reads at first like a conflict between AC-1 (a commit
carrying `[TASK-yyy]` attributes via that task's `req:` frontmatter) and BR-10 / AC-6 (a
bare `[TASK-001]` with no REQ context yields no candidate, and specifically must not halt
with three candidates). The reconciling reading — the only one that satisfies both — is
that AC-1's commit *does* carry REQ context in some form, and the task lookup resolves and
confirms within that REQ. Measured: `TASK-001.md` exists as an exact filename in 3 REQ
directories, and a `TASK-001*.md` glob matches **16** files across 157 task files, so an
unscoped glob would manufacture a false multi-candidate halt under BR-3 — worse than the
spec's own estimate. Scoping is load-bearing, not defensive.

**Consequence**: when `R` is known and the task file is absent (renamed, never committed),
the candidate falls back to `R` itself rather than being dropped. Dropping would lose a
correct, independently-attested attribution over a missing file.

**Spec correction (found in Phase 5).** The requirement — and the adversary report before
it — states that each TASK file carries a `req:` frontmatter field. It does not. The
canonical `templates/task-template.md` emits `parent:`, and **157 of this repo's 163 task
files use `parent:` while only 6 use `req:`**. An implementation faithful to the spec's
wording would have missed 96% of real task files. The resolver therefore reads `req:`
first (the documented field wins where both appear) and falls back to `parent:`, and the
test harness deliberately fixtures one of each so the dominant real-world spelling is not
left unverified. Worth a lesson: a spec that names a field should be checked against the
template that actually emits it.

### ADR-3 — `git log`, not `git blame --porcelain`, supplies the commit message

**Decision**: blame yields SHAs only; each SHA is then read with
`git log -1 --format='%s%n%b'`.

**Rationale**: blame's porcelain `summary` field carries the **subject only**. Re-measured
on this repo at implementation time (187 commits): 37 commits carry a bracketed trailer in
the subject, 37 in the body, 59 in either. A subject-only read finds 37 of the 75 commits
carrying any accepted form — it silently loses **51%**. This is F1 of the adversary report
and the single highest-value decision in the REQ.

### ADR-4 — The reverse edge is derived, never stored

**Decision**: REQ→incidents is computed by scanning `.adlc/bugs/*.md` frontmatter on every
read. Nothing is written into `.adlc/specs/**`.

**Rationale**: BR-4, informed by LESSON-019 (cross-reference guards rot when the thing they
point at moves) and the derive-don't-store posture of `/manifest`. A stored reverse edge
breaks silently on rename or renumber; a derived one cannot drift from its source.

### ADR-5 — Validation resolves against the **primary** repo, always

**Decision**: `adlc_attr_validate_req` takes an explicit primary-repo path and checks
`<primary>/.adlc/specs/<id>-*/`; the blamed repo path is a separate argument.

**Rationale**: BR-5 + BR-8 interaction. In cross-repo mode the blame runs in a sibling's
history but spec directories exist only in the primary. Conflating the two would make
every cross-repo attribution fail closed to `none` (AC-12 exists precisely to catch this).

## Component Design

### `partials/attribution.sh`

| Function | Contract |
|---|---|
| `adlc_attr_req_context <repo> <sha>` | Emits the REQ id providing context for the commit, per BR-2 precedence. Empty when none. A `<type>(BUG-xxx)` scope never contributes. |
| `adlc_attr_commit_reqs <repo> <primary> <sha>` | Emits validated candidate REQ ids for one commit (applies ADR-2 scoping, then BR-5 validation). Empty on no candidate. |
| `adlc_attr_blame_reqs <repo> <primary> <file> <start> <end>` | Blames the line range, unions `adlc_attr_commit_reqs` over the distinct SHAs, emits sorted-unique ids. |
| `adlc_attr_validate_req <primary> <id>` | BR-5: strict `^REQ-[0-9]{3,6}$` **and** `<primary>/.adlc/specs/<id>-*/` exists. Return 0/1, emits nothing. |
| `adlc_attr_bugs_with_attribution <primary> [req]` | BR-4/BR-9 reverse index: emits `BUG-id<TAB>REQ-id` for every bug whose `introduced_by` is non-empty, optionally filtered to one REQ. Read-only. |

All functions are prefixed `adlc_attr_` (namespaced like `adlc_forge_*`, `adlc_alloc_*`).

### Shell-portability rules applied throughout (BR-6)

- `grep -E` only — never `-P`, never `\b` (LESSON-013: BSD grep silently fails `\b` in `-E`).
- `printf`, never `echo`, for anything containing a variable.
- No word-splitting reliance: candidate lists travel through `while IFS= read -r` loops,
  never `for x in $var` (zsh does not word-split unquoted parameters — BUG-118/LESSON-399).
- No variable named `status` (zsh reserves it as an alias for `?`).
- No bare `$<digit>` in sed/grep replacement text inside SKILL.md fences (LESSON-335).
- Every glob that may not match goes through `find`, never a bare shell glob (zsh aborts
  on an unmatched glob — LESSON-335).

### `templates/bug-template.md` (BR-1)

Two optional fields appended to the existing frontmatter block — no rename, no reorder:

```yaml
introduced_by: []   # REQ ids whose merge introduced the defect, e.g. ["REQ-483"]
attribution: none   # derived | manual | none — how introduced_by was populated
```

A bug file with neither field stays valid (AC-15): every consumer treats absent as
`attribution: none` with an empty list.

### `/bugfix` Phase 2 integration (BR-3, BR-7, BR-8)

A new step 6 after root-cause validation, keyed off the file/line set Phase 2 already
produced. Per touched repo (BR-8), derive candidates; then:

- 0 candidates → write `attribution: none`, emit exactly **one** stderr line naming the
  reason, continue (BR-7 benign path — never halts, never fabricates).
- 1 candidate → write `introduced_by: [REQ-xxx]`, `attribution: derived`.
- 2+ candidates → present all of them, write nothing, let the operator select **one or
  more** (BR-3; selecting several is what makes `introduced_by` an array reachable —
  adversary F3). Refuse rather than guess (LESSON-483).

### `/status` integration (BR-9)

A new read-only `#### Incident Attribution` subsection after `#### Open Bugs`, populated
by `adlc_attr_bugs_with_attribution`. Modifies no file (AC-14).

## Task Graph

```
TASK-001 (partial + tests)  ─┬─→ TASK-003 (/bugfix wiring)
TASK-002 (bug template)     ─┘
                             └─→ TASK-004 (/status wiring)
TASK-005 (docs) ← depends on 003, 004
```

TASK-001 and TASK-002 are independent. TASK-003 and TASK-004 both depend on the partial
existing; TASK-003 also needs the template fields. TASK-005 documents what shipped.

## Files to Create/Modify

| File | Task | Action |
|---|---|---|
| `partials/attribution.sh` | 001 | create |
| `partials/tests/attribution.test.sh` | 001 | create |
| `partials/tests/run.sh` | 001 | modify (register harness) |
| `templates/bug-template.md` | 002 | modify (2 optional fields) |
| `bugfix/SKILL.md` | 003 | modify (Phase 2 step 6) |
| `status/SKILL.md` | 004 | modify (attribution subsection) |
| `CHANGELOG.md` | 005 | modify |
| `.adlc/context/architecture.md` | 005 | modify (cross-cutting dependency entry) |

## Verification Strategy

`partials/tests/attribution.test.sh` builds a **sandbox git repo** with fixture commits in
each accepted form, plus a fixture `.adlc/specs/` tree, and asserts one case per acceptance
criterion. It runs under bash and zsh via `partials/tests/run.sh` (AC-10). No network, no
mutation of the real repo — the same posture as `id-alloc.test.sh` and `forge.test.sh`.

Additionally, `python3 tools/lint-skills/check.py` must stay at exit 0 and
`python3 -m pytest tools/ -q` must stay at 484 passed (measured baseline before any edit).
