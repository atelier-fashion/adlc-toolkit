# `partials/lessons.sh` — LessonSet retrieval (REQ-647)

`adlc_lessons <subcommand> [args…]` runs the installed toolkit's
`tools/adlc/lessons.py` and passes its stdout and return code through. It is how
`/proceed` (Step 0, each Phase-4 task, Phase 5), `/bugfix` Phase 2, standalone
`/validate` and the sprint workflow engine's retrieval leaves get lessons **by
the surface being touched**, after `/spec` Step 1.6 froze the spec's
`## Retrieved Context` (LESSON-604).

## Call shape

Source and call in the same fence, after the root line:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/lessons.sh ]; then . .adlc/partials/lessons.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lessons.sh"; fi
adlc_lessons select --set step0 --root "<worktree>" --spec "<requirement.md>" --state-out "<primary-path pipeline-state.json>" --fresh
```

## Subcommands

| Subcommand | Does | Prints |
|---|---|---|
| `select --set step0\|task\|phase5\|bugfix --root <dir> …` | computes one LessonSet; with `--state-out` merges it into `lessons.<set>` of that state file | the log line (`bugfix`: the `Prior lessons consulted:` list), then one `### LESSON-xxx — title` block of loaded text per lesson; `--format json [--with-text]` prints the set as JSON instead |
| `text <LESSON-nnn-slug.md>` | the loaded text of one lesson | up to 40 lines |
| `log-line --state <file> --key step0\|phase5\|tasks.TASK-nnn --root <dir>` | recomputes the log line for a recorded set | one line, with `(stale: N lessons newer than this set)` when lesson files changed after `retrievedAt` |
| `ack-check --state <file> --root <dir> --worktree <dir> --base <ref> [--tasks-dir <dir>] [--record]` | the BR-4 acknowledgement check over `lessons.phase5`; with `--record`, also writes `lessons.acknowledged` (REQ-648) | at most 5 `Applicable lesson not acknowledged: …` lines and `(+N more applicable lessons not listed)`, or `No unacknowledged applicable lessons.` |

`select` flags: `--spec` (the REQ's `requirement.md`; `--bug` for the bugfix
set), `--component <c>` repeatable (the most specific component of each path
being touched — the `/review` Step 1.7a inference; the engine adds ancestors),
`--task-id TASK-nnn` (task set), `--state` (where to read `lessons.step0` for
the task set's process carry-over; defaults to `--state-out`), `--state-out`,
`--fresh` (a fresh Step 0: reset `lessons` first; refused on any other set) or
`--reuse` (a resume: return a recorded set unchanged), `--base <ref>` (Phase 5:
lesson files the diff changes carry no escalation standing; when git cannot list
them, every lesson is treated as changed, so the set still loads and no
exemption survives), `--retrieved-at <iso>` (tests).

## Sets

| Set | Query | Size |
|---|---|---|
| `step0` | the REQ's own frontmatter | top 10 |
| `task` | the task paths' components (+ ancestors) and the REQ's domain, stack, concerns, tags | top 5, then up to 3 lessons newer than the spec (most specific component first), then the Step-0 set's `kind: process` lessons, never past 15 |
| `phase5` | the diff paths' components (+ ancestors) and the REQ's frontmatter | top 15; fewer than 5 scored ⇒ topped up with the most recent lessons, unscored, to 10 |
| `bugfix` | the bug's frontmatter and the reproduction paths' components (+ ancestors) | top 5 |

Scoring is the `/spec` Step 1.6 rule over lessons only. Each entry carries `id`,
`title`, `path`, and when known `component`, `score`, `confidence`, `kind`,
`newerThanSpec` and `supersededBy`. Loaded text is the frontmatter, `## Lesson`
and `## Applies When`, capped at 40 lines.

## Return codes

| rc | Meaning |
|---|---|
| 0 | success (an empty corpus is success: `Lessons loaded (<set>): none`) |
| 2 | could not retrieve: one `lessons: unavailable — <reason>` line on stdout, detail on stderr. This includes a lessons directory whose files all fail to parse: a reader that dropped the corpus must not look like an empty one (LESSON-571) |

The wrapper turns anything it cannot run — no engine in the installed toolkit,
no interpreter resolver, a relative root, an engine exit outside 0/2 — into the
same rc 2 line.

**Retrieval never halts a pipeline.** It is not a gate and adds no halt point.
A caller that gets rc 2 logs the line it printed and continues without lessons.
`pipeline-state.json.lessons` is additive and optional, and nothing reads it
for control flow.

## State record

`lessons.step0`, `lessons.tasks["TASK-xxx"]` and `lessons.phase5`, each
`{query, lessons[], cap, retrievedAt}` without the loaded text, written
atomically to the **primary repo path's** `pipeline-state.json` (the worktree
copy is deleted at teardown). Every other key in the file is preserved; an
unreadable state file is refused (rc 2), never overwritten.

`lessons.acknowledged` (REQ-648) is `{ids[], checkedAt}`: every `LESSON-nnn`
the branch acknowledged (`Lessons:` trailers since `--base` in each
`--worktree`, and the task files' `## Verification` blocks), applicable or not,
sorted. `ack-check --record` writes it, and nothing else does; without the flag
`ack-check` writes nothing and its output is unchanged. `--record` without
`--state` is a usage error (rc 2). It is the source of the RunOutcome
`lessons_cited` field (`tools/delegate/run_outcome.py`), and it is read by
nothing for control flow. A `select --fresh` at Step 0 clears it with the rest
of `lessons`.
