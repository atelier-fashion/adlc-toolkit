# REQ-648 Architecture — Per-run outcome telemetry

## Approach

Every number in a RunOutcome line is derived by code from `pipeline-state.json`.
The model supplies only what exists nowhere else: the consolidated Phase-5
findings (they live in the conversation), the terminal tag, the engine, and a
halt reason token. Everything else (counts, classes, retries, elapsed time,
redaction, the harness stamp) is computed by `tools/delegate/run_outcome.py`
(LESSON-012: a field the model computes is honor-system).

The pipeline gains four additive, optional state keys, each written by code at
the moment its fact occurs (LESSON-626), and one reader-side record:

| Fact | State key | Written by | When |
|---|---|---|---|
| which toolkit ran | `harness` | `run_outcome.py record-harness` | `/proceed` Step 0 item 8, before the draft-PR push |
| validation retries | `validateAttempts` | `run_outcome.py record-validate` | before each `/validate` at Phase 1 / 3 (solo, legacy); in the workflow's validate leaf prompt |
| Phase-5 findings | `verify` | `run_outcome.py record-verify` | Phase 5 Step B (and Phase 5 (lite)); again after Step C/D; the workflow's state-write leaves |
| lessons acknowledged | `lessons.acknowledged` | `lessons.py ack-check --record` | Phase 5 Step B (REQ-647's own key) |
| lessons written | `lessonsWritten` | `run_outcome.py record-lessons-written` | `/wrapup`, end of Step 4, both modes |
| the run's outcome | one log line | `emit-run-outcome.sh` → `run_outcome.py emit` | per the BR-2 ownership table |

Every state write targets the **primary repo path's** copy
(`<repos[primary].path>/.adlc/specs/REQ-xxx-*/pipeline-state.json`), the same
file `partials/lessons.sh` and Step 8b write, because the worktree copy is
deleted at teardown. Writes are atomic (tempfile in the same directory +
`os.replace`) and merge-preserving (read, set one key, write), exactly as
`tools/adlc/lessons.py::write_state` does.

Two readers consume the log: `check-run-outcomes.sh` (POSIX `sh` + `awk`, no
`jq`) in two modes — `--recurrence` for `/sprint`'s summary and the default
per-`toolkit_version` window summary for `/analyze` Step 1.10.

## Components

### `tools/delegate/run_outcome.py` (new, stdlib only)

Subcommands (argparse; a usage error is rc 2):

- `emit --state <abs> --terminal <merged|pr-ready|blocked|failed> --engine <solo|legacy|workflow> [--reason <text>] [--req <REQ-id>]`
  prints one flat JSON line on stdout; rc 0. The state file may lack any
  additive key (AC-4): derived fields fall back to `-` (strings) or `"0"`
  (counts). A missing state file is tolerated only with `--req` (the workflow
  emits for a REQ whose Phase 0 never recorded a path); every derived field is
  then `-`/`0`. Without both, rc 1 with one stderr line.
- `record-harness --state <abs> --toolkit-root <dir> [--fresh]`: writes
  `harness` once (on a resume an existing `harness` is kept, BR-10 "never
  re-read"); `version` from `<dir>/VERSION` validated against
  `^[0-9A-Za-z._+-]{1,64}$`, `sha` from `git -C <dir> rev-parse --short HEAD`
  validated against `^[0-9a-f]{4,40}$` and read only when `<dir>/.git` exists
  (`git -C` walks up, and a cache copy inside a git-tracked HOME must not take
  the outer repo's sha), each `-` when unresolvable. `--fresh`, the same
  fresh-or-resume decision Step 0 makes for the lessons (LESSON-719), re-stamps
  it and clears an earlier run's `validateAttempts`, `verify` and
  `lessonsWritten`. Prints `harness: <version> <sha>`.
- `record-validate --state <abs> --phase <1|3> --attempt <n>`: sets
  `validateAttempts.phase<N> = max(existing, n)`. Absolute and monotone, so a
  replayed workflow leaf or a repeated call never double-counts.
- `record-verify --state <abs> [--loops <n>] --findings <file|->`: reads a JSON
  array of findings, normalises each, and replaces `verify.findings`; sets
  `consolidatedAt` (now) and `loops` (given, else kept, else 0).
- `record-lessons-written --state <abs> (--ids <LESSON-a,LESSON-b> | --no-entry)`.
- `record-carry --state <primary-path copy> --from <worktree copy>`: copies every
  top-level key the primary-path copy lacks (`startedAt`, `repos`,
  `phaseHistory`, …), the primary-path copy's own keys winning. Step 8b runs it
  before `/wrapup` writes anything there, so the record the line is built from
  survives teardown and no partial terminal write can shadow a key.

Pure functions (unit-tested): `normalize_severity` (`High→Major`,
`Medium→Minor`, `Low→Nit`, `Critical` unchanged, unknown → `Minor`),
`finding_class` (BR-6 tiers), `class_tier`, `title_slug`, `redact` (the
five-arm chain), `normalize_blocked_reason`, `validate_retries`, `build_record`.

**Field derivation** (`build_record(state, terminal, engine, reason, now)`):

| key | source |
|---|---|
| `timestamp` | now, ISO-8601 Z |
| `skill`, `step` | literals `proceed`, `run-outcome` |
| `req` | `state.req`, else `--req`; validated `^REQ-[0-9]{3,6}$`, else `-` |
| `repo` | basename of the primary entry's `path` with `/.worktrees/…` stripped; `-` when none |
| `engine`, `terminal` | the arguments, checked against their enums (rc 2 otherwise) |
| `toolkit_version`, `toolkit_sha` | `state.harness`, `-` when absent or malformed |
| `blocked_reason` | blocked/failed: `normalize_blocked_reason(--reason)`; merged/pr-ready: `close-out-failed` when `closeOut.status == "failed"`, else empty |
| `validate_retries` | Σ `max(int(attempts) − 1, 0)` over `phase1`, `phase3`; a non-int counts 0 |
| `verify_loops` | `verify.loops`, int-guarded; `"0"` when absent |
| `findings_*` | counts by normalised severity over `verify.findings` |
| `finding_classes` | comma-joined `finding_class` per finding, in stored order |
| `lessons_cited` | comma-joined valid ids from `lessons.acknowledged.ids` |
| `lessons_written` | `lessonsWritten` list → comma-joined valid ids; `"NO_ENTRY"` → `NO_ENTRY`; absent → empty |
| `elapsed_s` | now − `startedAt`, int seconds; `-` when unparseable |

Every count is a quoted decimal string (or `-`); every value is a JSON string;
the line has no nested object or array (REQ-424 BR-1/2). Free-text-bearing
values (`repo`, `toolkit_version`) pass `redact` before encoding; `class`
elements and ids are regex-validated instead, which is why redaction cannot
rewrite them (BR-6). `json.dumps(..., ensure_ascii=True, separators=(",",":"))`
guarantees one line.

`normalize_blocked_reason` maps the workflow's free-text reasons (BR-5) and the
solo tokens onto the closed enum: `*-validation`, `validation*` →
`validation-exhausted`; `reflector-questions` → itself; `merge-conflict`,
`needs-manual-rebase`, `trial-merge` → `merge-conflict`; `merge-unverified` →
itself; `close-out-failed` → itself; `phase0-no-worktree`, `no-worktree` →
`no-worktree`; `phase8-no-pr`, `no-pr` → `no-pr`; `phase8-no-repo`,
`setup-error` → `setup-error`; anything else non-empty → `other`; empty → empty.

### `tools/delegate/emit-run-outcome.sh` (new, POSIX sh, executed)

`emit-run-outcome.sh <args>`: runs `python3 <its own dir>/run_outcome.py emit
<args>` and appends the line to `${ADLC_RUN_OUTCOMES_LOG:-$HOME/Library/Logs/adlc-run-outcomes.log}`
under `umask 077` (a new file is created 0600). `emit-run-outcome.sh record-<x>
<args>` passes through to the same subcommand. **It always exits 0**; every
failure is one `run-outcome: <reason>` stderr line (BR-3). No `set -e`: the
contract is "never blocks", and `set -e` is how a wrapper surprises a caller.
Like `emit-telemetry.sh` it is executed, never sourced (the umask must not
leak). Located by call sites through `partials/delegate-tools-path.sh`
(`"$DELEGATE_TOOLS"/emit-run-outcome.sh`), so `tools/` stays un-vendored
(REQ-433). `emit-telemetry.sh` and `check-delegation.sh` are not touched.

### `tools/delegate/check-run-outcomes.sh` (new, POSIX sh + awk)

- `--recurrence --reqs REQ-a,REQ-b,…`: takes the latest line per listed REQ
  (file order: the log is append-only), and prints `<class>\t<k>\t<N>\t<tier>`
  for every class, where `k` is the number of listed REQs whose latest line
  carries it and `N` the number of listed REQs; sorted `k` desc then class asc;
  then `<REQ>\tno-record` for each listed REQ with no line, in list order.
  Tier: `lesson` for `LESSON-…`, `title-slug` for `title-slug:…`, `reviewer`
  otherwise. A missing log means every REQ is `no-record`.
- default (`[--window <N>d]`, default 7): latest line per REQ within the
  window, grouped by `toolkit_version`; TSV header
  `toolkit_version runs merged pr_ready blocked failed mean_validate_retries verify_loop_rate critical major minor nit top_classes`.
  **Exit contract** (LESSON-571 — distinct signals for distinct empties):
  log absent → rc 0, no output; present but no parsed line in the window →
  rc 0, the single line `no runs in <N>d window`; at least one non-empty line
  but none parses as a RunOutcome → rc 1 (corrupt); usage error → rc 2.
  A line that does not parse has no timestamp to exclude it by, so it counts
  toward the corrupt rule.
- The window cutoff is computed once as an ISO-8601 Z string (BSD `date -u -r`,
  GNU `date -u -d @`) and compared lexicographically, which ISO-8601 Z permits;
  no per-line `date` call. No `mktemp` at all (one `awk` pass).

### `tools/adlc/lessons.py` (modified)

`ack-check --record` writes `lessons.acknowledged = {ids: sorted, checkedAt}`
into the `--state` file after computing the acknowledged set, through a new
`write_acknowledged(path, ids, now)` that reuses `write_state`'s atomic write.
Output lines are unchanged. Without `--record`, behaviour is byte-identical.

### Reviewer agents + `/review` (modified, markdown)

A canonical block, `<!-- finding-class -->` … `<!-- /finding-class -->`, defined
once in `review/SKILL.md` Step 3 and copied byte-for-byte into the five reviewer
agents, `agents/reflector.md` and `agents/lite-reviewer.md`. It requires a
`**Class**:` line on every finding (the class regex, the "reuse a class already
emitted in this run" rule) and states the severity mapping. Each agent's output
template gains the `**Class**:` line. A pytest pins the block's presence and
byte-equality in every copy (LESSON-441: copies drift, the test is the guard).

### Workflow engine (modified)

- `FINDING_CLASS_PATTERN` (the three-tier regex) is a PURE-block constant;
  `FINDINGS.findings[].class` is **required** with that `pattern` (LESSON-331:
  closed schema extended in the same change, pinned by a structural test).
- `reviewPrompt` asks for `class` and states the severity scale.
- Pure `verifyEntry(finding, fixed)` maps a consolidated finding to
  `{severity, file, title, class, lessonId?, fixed}`; pure
  `markWorkflowFixed(before, after)` applies BR-4's workflow rule (fixed ⇔ in
  the first consolidation's blocking subset and absent from the re-verify
  consolidation, matched on repo + dedupe key or repo + file + class; a finding
  new in the re-verify is appended unfixed); pure `runOutcomeArgs(term)` gives
  the emit leaf `TERMINAL.state` verbatim and a shell-inert raw reason.
- `verify()` dispatches a state-write leaf (`verifyStatePrompt`) after the first
  consolidation (`loops: 0`) and, when the fix loop ran, after the re-verify
  (`loops: 1`). The leaf runs `emit-run-outcome.sh record-verify`. A leaf throw
  is logged and swallowed — never a halt.
- `gate()`'s validate prompt gains one line: run `record-validate --phase <n>
  --attempt <i>` first. The attempt number is the script's loop counter, so the
  prompt stays deterministic and a replay never double-counts.
- `emitRunOutcomes(closed, todo)` runs after `closeOutMerged`, one leaf per REQ,
  serially, regardless of terminal, passing `TERMINAL.state` verbatim and
  `reason`/`detail.reason` raw (the Python normalises — BR-5). Never throws; the
  returned `results` are unchanged.

### Skill text (modified)

One "Run-outcome telemetry (REQ-648)" section in `proceed/SKILL.md` holds the
canonical fences (record-harness, record-validate, record-verify, emit), each
preceded by the BUG-228 provenance line; phases and companions point at it.
Halt-point emits: one fence, run at each halt with that halt's token.
`agents/pipeline-runner.md` gains the runner's emit. `/sprint` gains the
orchestrator emit in Step 5, a Recurrence section in Step 6, and a summary step
on the workflow branch. `/wrapup` records `lessonsWritten` at the end of Step 4. `/analyze`
gains Step 1.10. `tools/lint-skills`'s `harness-skip` check also fires on a fence
that invokes `emit-run-outcome.sh`.

## Key decisions

**ADR-1 — One Python module owns every derivation; the wrapper owns only I/O.**
The record's correctness lives in pure functions with unit tests, and the shell
wrapper does what shell is good at (append with a umask). Rejected: deriving in
`awk` (state is nested JSON; a POSIX JSON walker is the bug farm REQ-609 removed
from the config reader) and deriving in the model (LESSON-012).

**ADR-2 — State writes go through the same module, not through freehand JSON
edits.** The pipeline's state keys are written by `record-*` subcommands so the
shape is enforced at write time and a resumed run cannot double-count
(`record-validate` is absolute + monotone). Rejected: "increment
`validateAttempts.phase1`" prose — a replayed workflow leaf or a re-run step
would double it.

**ADR-3 — `lessons.acknowledged` lives in REQ-647's namespace and is written by
REQ-647's engine.** The acknowledged set is computed inside `ack-check`; exporting
it there costs one flag and keeps one owner for the `lessons` key. Rejected: a
second trailer scan in `run_outcome.py` (two readers of one fact — LESSON-441),
and scanning at emit time (the worktree is gone by then).

**ADR-4 — `lessonsWritten` is a top-level key written at the end of `/wrapup` Step 4.**
Solo `/wrapup` writes no `closeOut` key (only close-out mode does), so nesting it
there would leave solo runs without a source. Step 5 is where the
`### Lessons captured` outcome is final in both modes.

**ADR-5 — The workflow's `fixed` flags are computed in pure JS; class tiering
in Python.** The workflow has the before/after consolidations in memory and
nothing else does, so the `fixed` rule is pure JS with node:test coverage; the
class tiering happens once, in `record-verify`, for all three engines.

**ADR-6 — One emit leaf per REQ, serial.** A per-REQ leaf diverges from the
journal only for the REQ whose terminal changed on a resume, so an untouched REQ
does not re-emit. Readers keep the latest line per REQ either way.

**ADR-7 — The recurrence denominator is the sprint's REQ list.** A REQ that
crashed has no line; it is a `no-record` row, never a silent absence from `N`
(BR-2, LESSON-571).

**ADR-8 — Redaction is a Python copy of `emit-telemetry.sh`'s chain, held equal
by a parity test that runs the real `sed` line.** `_common._KEYISH_RE` is a
detector with a different arm set. When REQ-671's `tools/adlc/credential_redact.py`
lands (its `INTAKE_PATTERN` is the same five arms), whichever lands second points
`run_outcome.py` at it.

## Lessons applied

LESSON-012 (structural, not prose), LESSON-019/020 (guards follow indirection;
partials sourced per fence), LESSON-331 (closed schema + structural test),
LESSON-441 (two copies drift — parity tests), LESSON-571 (distinct empty
signals), LESSON-626 (record at the moment of the event), LESSON-712 (census of
every emit site: solo, runner, legacy orchestrator, workflow), LESSON-732 (REQ-
scoped scratch files), LESSON-403 (registry lines are conflict magnets — the
`run.sh` harness list).
