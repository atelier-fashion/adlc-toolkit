# REQ-647 — Architecture

## Approach

One deterministic selection engine, one sourced partial in front of it, and
call sites that only say *which* set to compute and *where the loaded text
goes*. The model keeps the one step that needs judgment, the path → component
inference (`/review` Step 1.7a), and passes the result in as `--component`
flags. Everything after that is code: the Step 1.6 score, the recency rule,
the caps, the loaded-text extraction, the state write, the log line and the
acknowledgement check. That is what lets AC 2, AC 4 and AC 6 be scripted, and
it keeps every call site on one implementation (Out of Scope: "a second
retrieval implementation").

```
        model: paths → components (Step 1.7a judgment)
                         │  --component …
                         ▼
partials/lessons.sh ── adlc_lessons <cmd> ──▶ <ToolkitRoot>/tools/adlc/lessons.py
                                                 │
       ┌──────────── select ─────────────────────┼──────── text / log-line / ack-check
       ▼                                         ▼
 pipeline-state.json.lessons.<set>         stdout: log line + loaded text
 (primary-path copy, no text)              (or --format json for a workflow leaf)
```

### Call sites

| Site | Set | Query | Cap | Written to |
|---|---|---|---|---|
| `/proceed` Step 0 item 7 | `step0` | REQ frontmatter | 10 | `lessons.step0` |
| `/proceed` Phase 4, before each task | `task` | task paths' components + REQ frontmatter | 5 + 3 recency + process carry-over, ≤ 15 | `lessons.tasks["TASK-xxx"]` |
| `/proceed` Phase 5, before Step A | `phase5` | diff paths' components + REQ frontmatter | 15, top-up to 10 | `lessons.phase5` |
| `/proceed` Phase 5 Step B | ack check over `lessons.phase5` | — | 5 Info lines | — |
| `/validate` implementation phase (standalone) | ack check | — | 5 Info lines | — |
| `/bugfix` Phase 2, first step | `bugfix` | bug frontmatter + reproduction paths' components | 5 | not written (no state file) |
| workflow engine, after Phase 0 / after Phase 2 / before Phase 5 | `step0` / `task` ×N / `phase5` | as `/proceed` | as `/proceed` | the leaf runs the same `select` |

## Engine — `tools/adlc/lessons.py`

Stdlib only (no PyYAML): lesson frontmatter is the toolkit's one-line format
(`key: value`, quoted scalar, or inline `[a, b]` list). The block is found the
way `adlc_lesson_check` and the `/review` superseded lookup find it: a leading
BOM and trailing CRs are dropped, blank lines and HTML comments (multi-line
ones included — four lessons open with one) are skipped, and the block opens
only when the first other line is `---`. A file whose block does not parse is
skipped, never a crash (Step 1.6 sub-step 2).

Subcommands. Each prints to stdout; a usage or I/O error is rc 2 with a
`lessons: unavailable — <reason>` line on stdout and the detail on stderr:

- `select --set step0|task|phase5|bugfix --root <dir> [--spec <requirement.md>] [--bug <bug.md>] [--component <c>]… [--task-id TASK-xxx] [--state <file>] [--state-out <file>] [--fresh|--reuse] [--base <ref>] [--format text|json] [--with-text] [--retrieved-at <iso>]`
- `text <lesson.md>` — the loaded text of one lesson.
- `log-line --state <file> --key step0|phase5|tasks.TASK-xxx --root <dir>` — the BR-10 line, with the stale suffix.
- `ack-check --state <file> --root <dir> --worktree <dir> --base <ref>` — BR-4's Info lines.

### Selection (the Step 1.6 rule over lessons only)

`+3` when `doc.component ∈ components`, `+2` same domain, `+2` per shared
concern, `+1` per shared stack entry or tag, `+1` floor for a lesson with none
of the five fields. Score-0 dropped. Sort key `(score DESC, effective_date
DESC, id ASC)` — `corpus_priority` is constant, since only lessons are scored.
`effective_date` is `updated` → `created` → file mtime → epoch-min.

`components` is the caller's list **plus each entry's ancestors** short of a
one-segment root (`adlc/partials/forge` adds `adlc/partials`). The caller's
entries are the *most specific* set; the derived ancestors are not. For
`step0` the REQ's own `component` is the caller list; for `bugfix` the bug's
`component` joins the caller's.

**Recency rule (`task` only, BR-1a).** Candidates: not already selected,
`created` later than the spec's `created` (ISO date string compare; a missing
date is never newer), and `component ∈ components` or (`domain` equal and
`component` a `/`-bounded prefix of one of them). Order: a candidate whose
`component` is one of the caller's entries first, then the rest; within each,
the Step 1.6 key. Up to 3. `newerThanSpec: true` on **every** member whose
`created` is later than the spec's, however it was admitted.

**Process carry-over (`task` only).** Every `kind: process` entry of
`lessons.step0` (read from `--state`; recomputed in memory from the spec when
the state has none) not already present, in Step-0 order, until 15 members.

**Phase-5 top-up.** Fewer than 5 scored ⇒ add the most recent lessons by
`effective_date`, unscored (no `score` key), until 10. "Most recently
modified" is read as `effective_date` rather than raw mtime, because a fresh
worktree gives every file the checkout's mtime and the order would be
arbitrary.

**Escalation standing (REQ-646 BR-6, for BR-3 and BR-6).** Each entry carries
the lesson's `confidence` and a `supersededBy` list from the corpus-wide
reverse lookup. On the `phase5` set with `--base`, a lesson file the diff adds
or modifies carries no standing: its `confidence` is omitted and it is not
counted as superseding anything (`/review` Step 1 item 7f, in code).

### Loaded text (BR-1b)

The frontmatter block (with its `---` lines), then `## Lesson`, then
`## Applies When`, separated by one blank line, each section running from its
heading to the next `## ` heading outside a code fence, trailing blank lines
dropped. Fallbacks: no `## Lesson` ⇒ the first `## ` body section; no
`## Applies When` ⇒ the line `Applies When: <title>`. More than 40 lines ⇒ the
first 39 plus `[… truncated — read LESSON-xxx for the rest]`, exactly 40.

### State write (BR-7)

`--state-out <file>` reads the file if present (else starts from
`{"req": <spec id>}`), sets `lessons.step0`, `lessons.tasks.<TASK-xxx>` or
`lessons.phase5` to the set **without** `text`, and writes it back atomically
(temp file in the same directory, `os.replace`). Every other key is preserved.
`--fresh` (a fresh Step 0) replaces the whole `lessons` object first, so a
prior run's task and Phase-5 sets do not survive into this one. `--reuse` (a
resume) returns the existing set unchanged when it is present and computes only
when it is not (BR-1; LESSON-719: the caller decides resume from the progress
record, not from whether the key exists).

The target is the **primary-path** copy,
`<repos[primary].path>/.adlc/specs/REQ-xxx-*/pipeline-state.json` (Entities;
the worktree copy is deleted at teardown). The file is gitignored, so writing
it does not dirty the parent repo; `agents/pipeline-runner.md` rule 4 names it
as a sanctioned target beside the Step 8b terminal record.

### Log line (BR-10)

`Lessons loaded (<set>[ <TASK-xxx>]): LESSON-a, LESSON-b [newer-than-spec: LESSON-c]`,
or `Lessons loaded (<set>): none`, plus ` (stale: N lessons newer than this set)`
when N lesson files under `--root` have an mtime later than the set's
`retrievedAt`. `select` prints the line first; `log-line` recomputes it later,
which is how a Phase-4 end-of-phase log can be stale (AC 11).

### Acknowledgement check (BR-4)

`unacknowledged(lessons, components, acknowledged, limit=5)` is the pure
function under test (AC 6). A lesson qualifies when its `component ∈
components` (the set's recorded `query.components`, ancestors included) or it
carries `kind: process`, and its id is not acknowledged. Ordered by score
(unscored last), then id. Returns at most 5 `Applicable lesson not
acknowledged: LESSON-xxx — <title>` lines, then `(+N more applicable lessons
not listed)` when N > 0. The CLI collects acknowledgements from `Lessons:`
trailers in `git log <base>..HEAD` and from LESSON ids in the
`## Verification` block of every task file under the spec's `tasks/`.

## Partial — `partials/lessons.sh`

`adlc_lessons <subcommand> [args…]`. Resolves the engine at
`${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/lessons.py` (the
installed toolkit, as `lane-check.sh` does), the interpreter through
`forge.sh`'s `_adlc_forge_python` (the documented coupling REQ-652 ADR-3
introduced), and runs `command "$py" -E …`. Return code and stdout pass
through. A missing engine, a missing resolver or a relative root is rc 2 with
one `lessons: unavailable — <reason>` line, so a call site can log it and carry
on. POSIX, dash-clean, prefixed globals, no `case` inside `$( )` (LESSON-582).

**Retrieval never halts a pipeline.** Every call site treats a non-zero return
as "log the line, continue with no lessons". It is not a gate and adds no halt
point (BR-7: nothing reads `lessons` for control flow).

## Workflow engine (BR-6)

PURE block additions:

- `LESSON_ENTRY`, `LESSONS` (`{query, lessons[≤15], retrievedAt, cap?,
  unavailable?}`, closed) and `TASK_LESSONS` (`{sets: [{taskId, set:
  LESSONS}]}`). `LESSON_ENTRY` declares `id, title, path` (required) and
  `score, confidence, kind, component, newerThanSpec, supersededBy, text`
  (optional). `text` carries the loaded text into prompts; the state record
  omits it.
- `escalateByLessons(findingsByRepo, set)` — a finding's `lessonId` escalates
  one level only when it is an id in the set and that entry has neither
  `confidence: "low"` nor a `supersededBy`; an id outside the set is removed from
  the finding (an agent-written id is untrusted, LESSON-008) and never
  escalates. Runs before `dedupeAndRank`.
- `dedupeAndRank` unions lesson ids: the survivor keeps the first non-empty
  `lessonId` and a sorted `lessonIds` union.
- `lessonsBlock(set, heading)` and `lessonsLogLine(label, set)` — the prompt
  text and the BR-10 line, both pure and deterministic.

Orchestration: three retrieval leaves (after Phase 0, after Phase 2 for every
task in one call, before the Phase-5 fan-out), each schema-validated.
`architectPrompt` carries the Step-0 block, `implementPrompt` the task's
block, `reviewPrompt` the Phase-5 block for all six members (the reflector told
it was pre-computed). The leaves' prompts depend only on the REQ id, the
worktree and the task list, never on `args.answers`, so a resume replays them
from the journal and every downstream prompt stays byte-identical (REQ-474
BR-7).

## Key decisions

**ADR-1 — Python engine behind a sourced partial, not model-executed scoring.**
The spec's ACs require scripted reproduction (AC 2, AC 4, AC 6), which a
model-executed score cannot give, and five call sites executing a prose rule
would be five implementations. `lane_check.py` behind `lane-check.sh` is the
precedent: stdlib Python for the logic, a POSIX wrapper for the fence, the
installed toolkit's copy as the engine. `/spec` Step 1.6 keeps its
model-executed form; this REQ does not change it (Out of Scope).

**ADR-2 — The model infers components; the engine adds ancestors.** Path →
component vocabulary is project-specific (`API/auth` in a consumer,
`adlc/partials/forge` here), which is why `/review` Step 1.7a is a judgment
step. The engine takes the most specific components and derives the ancestors
itself, so "most specific first" in the recency rule is decidable in code.
Measured on today's corpus: with ancestors scored but no specificity order,
the recency slots go to `adlc/partials` lessons and LESSON-582 drops out of the
REQ-593 task set; with the order it is the first recency add.

**ADR-3 — The task set is capped at 15, so one schema bounds every set.**
BR-1a as drafted could reach 5 + 3 + 10. Capping the process carry-over at 15
members keeps `LESSONS.maxItems: 15` valid for all four sets and the
implementer prompt within the Phase-5 budget (600 lines).

**ADR-4 — `text` lives in the leaf output, not the state record.** The
workflow script has no filesystem, so the only way a prompt can carry the
loaded text is for the leaf to return it. The state record stays small and is
read by nothing for control flow.

**ADR-5 — Escalation exemptions are enforced in code on the engine path.**
BR-3 requires `/review` Step 4's rule inside Phase 5. On the workflow path the
script escalates, so the set entries carry `confidence` and `supersededBy`, and
the "lesson changed in this diff" rule is applied when the set is computed. On
`/proceed` the model applies Step 4 as written, reading the same fields.

**ADR-6 — The acknowledgement check is Info-only and runs on `/proceed` and
standalone `/validate`.** The workflow engine's Phase 5 gets BR-6's escalation
but not the Info list: BR-4 names `/proceed` Phase 5 Step B and `/validate`,
and the engine has no Step B narrative to put Info lines in. A follow-up can
add it to the engine's consolidation log.

**ADR-7 — `agents/reflector.md` keeps its grep for standalone use.** BR-3
replaces the reflector's grep when `/proceed` supplies a set. `/reflect` and
any other caller that supplies none still get the grep, so the agent says
"use the supplied set and do not grep; grep only when no set was supplied".

## Lessons applied

- LESSON-604 — the per-task set and the recency rule are its remedy.
- LESSON-331 — the new closed schemas ship with a pure structural test.
- LESSON-008 — an agent-written `lessonId` is checked against the set ids.
- LESSON-582, LESSON-617, LESSON-335 — the partial is dash-clean, guarded, and
  hands the shell no unmatched glob.
- LESSON-719 — resume reuse is decided by the caller from the progress record.
- LESSON-403 — no hand-maintained count is added to a shared doc.
- LESSON-718 — the engine is the installed toolkit's copy, as for the lane
  check, though retrieval is not a gate.
