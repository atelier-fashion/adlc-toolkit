---
parent: proceed
section: "Run-outcome telemetry (REQ-648)"
---

# /proceed — Run-outcome telemetry

Companion to `proceed/SKILL.md` (REQ-661). Its "Run-outcome telemetry (REQ-648)" section sends you here before Step 0. Read this file whole, then return to `proceed/SKILL.md` at Step 0. Later steps name these fences as **Run-outcome telemetry** R1 to R5; each is run where that step says, and this file is where its text lives.

## Run-outcome telemetry (REQ-648)

Every terminal appends one flat JSON line to `~/Library/Logs/adlc-run-outcomes.log`
(`$ADLC_RUN_OUTCOMES_LOG`). `tools/delegate/run_outcome.py` builds it from the
primary-path state; you never compute a field. You supply only the terminal, the
engine (`solo` for a direct `/proceed`, `legacy` in subagent mode), a halt token,
and, at Phase 5, the consolidated findings. Each fence below runs
`"$DELEGATE_TOOLS"/emit-run-outcome.sh`, which always exits 0: relay the one line
it prints and continue, because telemetry never halts the pipeline (BR-3).
`<state>` is the primary-path `pipeline-state.json` named in `proceed/phases-state.md`
("Pipeline State Tracking") (the worktree's copy when that spec directory does not exist on the
primary checkout).

**R1 — the harness stamp** (Step 0 item 8 in `proceed/phase-0-setup.md`, before item 8a's push). `<mode>` is
`--fresh` on a fresh run and empty on a resume: the same decision Step 0 item 7
makes for the lessons, read from the progress record and never from whether a
`harness` key exists (LESSON-719). `--fresh` also clears the `validateAttempts`,
`verify` and `lessonsWritten` an earlier run of this REQ left behind.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
"$DELEGATE_TOOLS"/emit-run-outcome.sh record-harness --state "<state>" --toolkit-root "$ADLC_TOOLKIT_ROOT" <mode>
```

**R2 — a validation attempt** (Phases 1 and 3, before each `/validate`). The
attempt number is absolute, so a repeated call never double-counts.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
"$DELEGATE_TOOLS"/emit-run-outcome.sh record-validate --state "<state>" --phase <1|3> --attempt <n>
```

**R3 — the Phase-5 findings** (Step B, then again before Phase 5's end-of-phase
log). One JSON object per consolidated finding: `severity`, `file`, `title`, the
`class` its reviewer gave it, `lessonId` when it matched a lesson in the Phase-5
set, and `fixed` (`true` only once its fix commit has landed). `--loops` is `1`
when Step D re-verified, else `0`. The engine normalises the severity scale and
the class tiers; pass what the reviewers reported.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
"$DELEGATE_TOOLS"/emit-run-outcome.sh record-verify --state "<state>" --loops <0|1> --findings - <<'ADLC_VERIFY_JSON'
[{"severity":"Major","file":"<path>","title":"<title>","class":"<defect-pattern>","fixed":false}]
ADLC_VERIFY_JSON
```

**R4 — carry the run's state** (Phase 8 Step 8b, before `/wrapup`). It copies
every key of the worktree copy that the primary-path copy lacks, so the record
the line is built from survives teardown; the primary-path copy's own keys win.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
"$DELEGATE_TOOLS"/emit-run-outcome.sh record-carry --state "<state>" --from "<repos[primary].worktree>/.adlc/specs/REQ-xxx-<slug>/pipeline-state.json"
```

**R5 — the line itself.** Run it once at each terminal this run reaches: after
Step 8b for `merged`, after Step 8c's note for `pr-ready`, at each legitimate
halt before you stop (`blocked`, with the halt's token below), and on a `failed`
terminal. A resumed run that reaches another terminal emits again; readers keep
the latest line per REQ. Halt tokens: `validation-exhausted` (halt #1),
`reflector-questions` (#2), `merge-conflict` (#3), `other` (#4, a failed lane
check). A `failed` terminal passes `setup-error`, `no-worktree` or `no-pr`.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
"$DELEGATE_TOOLS"/emit-run-outcome.sh --state "<state>" --terminal <merged|pr-ready|blocked|failed> --engine <solo|legacy> --reason "<token, or empty>"
```
