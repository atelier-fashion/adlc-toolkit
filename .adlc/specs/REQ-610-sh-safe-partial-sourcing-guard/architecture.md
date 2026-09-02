# REQ-610 Architecture — sh-safe partial sourcing guard

## Approach

Replace the two-level source line at every executable call site with one canonical
guarded spelling, make the linter the thing that keeps it that way, and prove the spelling
with a harness that executes the *real* lines from the *real* files under every shell
`run.sh` drives. No new partial, no new skill, no new file family beyond one test harness
and one lint check.

The change has three independent legs and one dependent leg:

| Leg | What | Depends on |
|---|---|---|
| A | `partials/tests/source-guard.test.sh` + `run.sh` registration (+ `dash`) | — |
| B | `tools/lint-skills` `unguarded-source` check, `CANONICAL_LITERALS` move, fixtures, tests, README, `/analyze` check-name list | — |
| C | Documentation, partial header comments, companion `.md` examples, `CHANGELOG` | — |
| D | The rewrite of every executable site (45 fences, 1 prose line, 2 non-skill fence files, 1 live line in a partial) | A, B |

A and B are the verification; D is the change they verify. Landing A and B first is what
lets the PR record the **red** `/bin/sh` state (AC-1) before D turns it green, and lets the
lint prove D is complete rather than trusting a grep.

## Key decisions

### ADR-1: Per-call-site `if`/`else` guard; no bootstrap partial

**Decision.** The canonical spelling is

```sh
if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; else . ~/.claude/skills/partials/<name>.sh; fi
```

on one line, applied at every call site. There is no `partials/source-partial.sh`.

**Rationale.** A bootstrap partial has to be sourced by every fence with the same
repo-local-first two-level pattern it is meant to replace, so every fence still carries a
guard and the bootstrap saves nothing per site while adding a third file for `/init` to
vendor and `/template-drift` to police. The `if`/`else` form is the only one of the four
candidates that is correct under all of `/bin/sh` (macOS, bash-posix), `dash`, `bash`,
`bash --posix`, and `zsh` (spec table): `command .` still exits under macOS `/bin/sh`, and
`[ -f A ] && . A || . B` double-sources when `A`'s final status is non-zero — which for a
function-defining partial is whatever its last top-level statement returned, a property no
partial author is thinking about. One line, so it survives the Skill loader's
`$<digit>` templating unchanged (LESSON-335) and stays a single statement for the
`cross-fence-fn` check's line-based parsing. No `2>/dev/null` anywhere: BR-4, and
LESSON-441 says the copy that crashed must be diagnosable.

`[ -f ]` rather than `[ -r ]`: an existing-but-unreadable vendored copy then fails loudly
at the `.` instead of silently falling through to canonical and hiding a permissions
problem on the consumer's file (spec Assumptions).

### ADR-2: One lint check with two rules, prose included, implemented in the check (not `sentinels.txt`)

**Decision.** `check_unguarded_source(text, rel)` in `check.py` applies two rules to every
walked file:

1. **Fence rule.** Inside any ` ```sh `, ` ```bash `, or ` ```shell ` fence, a non-comment
   line carrying a statement-position `.` whose operand contains `partials/<name>.sh`
   must match `CANONICAL_SOURCE_RE` exactly; otherwise it is an `unguarded-source`
   finding at that line. Statement position = start of line, or after `;`, `&&`, `||`,
   `then`, `do`, `{` — the same positions `posix-fence` uses for `local`. The canonical
   regex carries a backreference so the three `<name>` occurrences must agree; a line
   that guards `forge.sh` and then sources `intake.sh` is a finding, not a pass.
2. **Retired-spelling rule.** The literal `2>/dev/null || . ~/.claude/skills/partials/`
   anywhere in the file — prose, inline code, fence comment — is a finding. The one
   prose occurrence (`analyze/SKILL.md` Step 1.5) tells the agent to type the line, and
   a fence comment quoting it is one paste away from being live.

Unlike `posix-fence`, **` ```bash ` fences are not exempt**: the fence label does not choose
the shell that executes the block (`run.sh` and consumers run fences under `/bin/sh`
regardless of label), and the failure is a property of the executing shell, not the
label.

**Rationale for not using `sentinels.txt`.** Sentinels walk only `SKILL.md` (spec Open
Question resolved here). The retired spelling also lives in `agents/delegate-pre-pass.md`
and `proceed/phases-6-8-ship.md`, and a sentinel carries no actionable message. One check,
one message ("replace with the guarded spelling — see conventions.md 'Bash in skills'"),
all three file families.

**Benign path.** The executable-partial macro `sh .adlc/partials/x.sh 2>/dev/null || sh ~/.claude/skills/partials/x.sh`
matches neither rule (the command is `sh`, not `.`; the literal has `|| sh ~/`, not
`|| . ~/`). The canonical spelling matches rule 1's regex and contains no retired literal.
Both are fixture-tested as must-not-fire.

### ADR-3: Walk set = `SKILL.md` ∪ `agents/*.md` ∪ `proceed/phase*.md`; only `SKILL.md` counts

**Decision.** A new `find_phase_files(root)` yields `proceed/phase*.md` (the glob covers
`phase-4-implementation.md`, `phases-1-3-validation.md`, `phases-6-8-ship.md` — all three
are `/proceed` companion files that carry fences; one of them sources `forge.sh` today).
`check_unguarded_source` runs in the main `SKILL.md` loop, in the existing
`find_read_bin_extra_files` loop, and in a new loop over `find_phase_files`. Neither extra
loop increments `scanned` (REQ-609's reasoning in `find_read_bin_extra_files`'s docstring:
the REQ-595 vacuous-scan figure must keep counting `SKILL.md` so a dead skill walk cannot
be masked by companion files). Same symlink-escape guard as the other walks.

`find_read_bin_extra_files`'s own walk is **not** widened: `read-bin-fallback` on the
phase files would be a scope change to an unrelated check.

### ADR-4: `CANONICAL_LITERALS` moves in the same change; fixtures move with it

**Decision.** The two source-line literals (`delegate-gate.sh`, `delegate-tools-path.sh`)
become the canonical spelling. The 15 fixtures carrying the old spelling are rewritten to
the canonical one **except** one new negative fixture (`unguarded-source-fence.md`) and one
updated negative case in `test_missing_canonical_reports_per_rule`, which keep the old
spelling deliberately and assert it is reported by *both* `canonical-helper` (the literal
moved) and `unguarded-source` (the shape is retired). `test_check.py` assertions at lines
144–145, 190, 322–323, 338–341 are updated to the new literal.

**Rationale.** REQ-436 ADR-4 / LESSON-019 #1: a literal-presence guard rots when the thing
it guards changes shape. Moving the literal and the fences in one change, and keeping one
fixture that proves the *old* shape now fails, is how the guard is shown to still be
alive rather than silently widened.

### ADR-5: The harness executes the corpus, not a copy of the spelling

**Decision.** `source-guard.test.sh` extracts every distinct line that dot-sources a
partial — leading whitespace stripped, matched by `^(\. |if \[ -f ).*partials/[a-z0-9-]+\.sh`
— from `*/SKILL.md`, `agents/*.md`, `proceed/phase*.md`, and the non-comment lines of
`partials/*.sh` (this is what covers `emit-step-telemetry.sh`'s live self-source). For each
line it creates a marker-printing fake canonical partial per referenced `<name>` under a
fake `$HOME` and runs the line verbatim under `$ADLC_TEST_SHELL` via `-c`, with `echo AFTER`
on a following line, in:

- **(a)** a cwd with no `.adlc/` — expect every `CANON:<name>` marker and `AFTER`;
- **(b)** a cwd whose `.adlc/partials/<name>.sh` prints `LOCAL:<name>` and then runs
  `false` — expect `LOCAL`, expect no `CANON`, expect `AFTER`;
- **(c)** `$HOME` pointing at a nonexistent dir and no `.adlc/` — expect non-empty stderr
  naming `<name>.sh`;
- **(d)** the executable-macro form for `ethos-include.sh` with the repo-local file absent
  — expect `CANON` and `AFTER` (benign control);
- **(f)** (added by leg D) the `/architect` Step 5 fence extracted from `architect/SKILL.md`
  and run under `$ADLC_TEST_SHELL` in a sandbox with a fake canonical `forge.sh` and no
  `pipeline-state.json` — expect the "standalone run, skipping footprint publish" line
  (AC-8, the original 2026-09-01 reproduction);
- **(e)** (added by leg D, proving leg C's outcome) a `grep -rF` of the retired literal over the distribution surface
  — expect zero hits (AC-6), and a grep of the canonical spelling in `conventions.md` —
  expect a hit (AC-7).

Lines are iterated with `while IFS= read -r`, never a `for` over an unquoted expansion
(LESSON-329). The line is passed as the whole `-c` script with `AFTER` on its own line so
a trailing shell comment in a fence cannot swallow the sentinel.

**Rationale.** A harness that hardcodes the spelling proves the spelling, not the fences.
Extracting from the files proves that what is *actually in the corpus* survives `/bin/sh`,
and it is what makes case (a) red before leg D and green after with no test edit in
between. The lint (ADR-2) proves every site uses the one spelling; the harness proves the
spelling works — together they close the loop without either duplicating the other.

### ADR-6: `run.sh` drives `dash` when installed

**Decision.** `run.sh`'s shell loop becomes `bash zsh /bin/sh dash`, with the existing
skip-with-notice for an absent shell. On a Debian-family box `/bin/sh` *is* dash and the
pass runs twice; harmless.

**Rationale.** dash is the `/bin/sh` of the consumers most likely to run fences under `sh`
(Linux CI). It is one word in a loop that already exists.

### ADR-7: The rewrite is a Python script with count assertions, not `perl -i` in a shell

**Decision.** Leg D applies the substitution with a throwaway Python script (kept in the
task's Technical Notes, not committed): regex
`\. \.adlc/partials/([a-z0-9-]+)\.sh 2>/dev/null \|\| \. ~/\.claude/skills/partials/\1\.sh`
→ canonical, per file, asserting the per-file replacement count against the expected
table before writing. The prose occurrence in `analyze/SKILL.md` is rewritten by hand.

**Rationale.** REQ-424 shipped corrupted fences because a `perl -i -pe` replacement string
was interpolated by the invoking shell. A Python source file has no shell interpolation
layer, and asserting counts catches a site the regex missed (an indented or
differently-quoted variant) instead of leaving it for the lint to find later.

### ADR-8: Docs describe the retired form with a placeholder, never the literal

**Decision.** `conventions.md`, `partials/README.md`, and `tools/lint-skills/README.md`
show the retired shape as `. <local> 2>/dev/null || . <canonical>` (or in words), and show
the two rejected alternatives (`command .`, the `&&`/`||` chain) with their failure modes.

**Rationale.** AC-6 requires zero hits for the retired literal under `.adlc/context/` and
`README.md`; the *reason* it was retired must still be findable by the next author.

## Proposed additions to `.adlc/context/architecture.md`

Partials paragraph: replace the sourceable-partial example with the canonical spelling and
add one sentence — "`.` is a POSIX special built-in, so a failed source is fatal under `sh`;
the repo-local copy is therefore tested with `[ -f ]` before it is sourced, and never
guessed at with `||` (REQ-610)." Leg C carries this edit.

## Task dependency graph

```
TASK-100 (harness + run.sh)        ─┐
TASK-101 (lint check + literals)   ─┼─▶ TASK-102 (rewrite executable sites; harness case f)
TASK-103 (docs, comments, CHANGELOG)               ─┘   (102 owns harness cases e and f;
                                                            it depends on 100, 101, and 103)
```

Tier 1: TASK-100, TASK-101, TASK-103 in parallel. Tier 2: TASK-102.

## Lessons applied

- LESSON-329 / LESSON-605: dogfood under every executing shell; a shell that passes
  manufactures false evidence — hence `run.sh` under four shells and the corpus-executing
  harness.
- LESSON-335: no `$<digit>` in the spelling; one line so templating cannot split it.
- LESSON-441 / LESSON-465: vendored partials shadow canonical; `emit-step-telemetry.sh`'s
  live line is fixed at canonical *and* the CHANGELOG names the per-file re-sync.
- LESSON-012 / LESSON-019: structural enforcement over prose; move the literal guard in
  lockstep and keep one fixture proving the old shape fails.
- LESSON-013: no `\b` in `grep -E` anywhere in the harness.
- REQ-424 / REQ-425: no shell-interpolated bulk edits of SKILL.md.
