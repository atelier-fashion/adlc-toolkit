# REQ-660 Architecture

## Approach

Three pieces, each small. The hook records what the harness says at session start.
Discovery asks one question of every candidate: does this file hold the mark this
run printed? `extract-chat` gains a format switch that refuses any format no real
transcript has proven. The hook command changes by one token (ADR-8).

```
SessionStart ──▶ adlc_session_record ──▶ .adlc/.session/<id>   (0600, gitignored, pruned)

/wrapup Step 4
  1a adlc_transcript_mark ─ prints adlc-transcript-mark-<hex>
  1b adlc_transcript_find <mark>
       rung (a) sidecars with a usable path, harness in the enum, holding the mark
       rung (b) ~/.claude/projects, ~/.codex/sessions, ~/.copilot/session-state,
                ~/.gemini/tmp: recent files holding the mark
       exactly one holder ─▶ path on stdout       anything else ─▶ rc 1, refusal
     adlc_transcript_format <path> ─▶ flag file (jsonl, format)
  2  extract-chat "$JSONL" -o "$TMPFILE" --format "$FORMAT"
       no parser for that format ─▶ non-zero ─▶ Fallback drafting
```

## Key decisions

### ADR-1: The mark is the only acceptance check

The spec's REQ-id anchor is the check BUG-253 removed. LESSON-733 records why: an
id proves a transcript mentions the work, not that it is the run. A mark also
answers the threat a sidecar adds. A sidecar is a file in the working tree, and a
hostile repo could commit one naming any file under `$HOME`. That file cannot hold
a value generated a moment ago, so it is never delegated. An id anchor would pass
any file containing the id.

Consequences: no cwd locator, no Gemini project hash (OQ-2 moot), no Codex day
window, no `started_at` tie-break, no "no REQ id" branch. `started_at` stays in the
sidecar because the contract names it and a future reader may want it; nothing
reads it for control flow. Rejected: mark first with an id fallback for harnesses
whose flush timing is unmeasured. That reinstates the wrong-transcript failure on
exactly the harnesses nobody can test, and a refusal is safe by construction.

### ADR-2: Extend `partials/session-transcript.sh`; no `session-discovery.sh`

BUG-253 already made this partial the sourceable, tested unit the spec wanted.
`adlc_transcript_find <mark>` keeps its stdout-and-rc contract. A consumer whose
vendored copy predates this REQ therefore keeps exact Claude behaviour, because the
two-level source prefers the stale copy and the stale copy still answers. A new
function name would turn that into a silent degrade. `adlc_transcript_format
<path>` is new; the fence reads it with `2>/dev/null` and an empty fallback, and
step 2 treats empty as `claude`.

### ADR-3: Format travels by a second function, not on stdout

`adlc_transcript_find` printing `format:path` would break ADR-2's compatibility.
`adlc_transcript_format` answers from the sidecar that names the path, else from
the root the path is under, else empty.

### ADR-4: The hook is one embedded Python program

The stub parsed JSON with `sed`, which cannot read an escaped string, and the full
contract (path containment, `started_at` carry-over, pruning, atomic write, a
stdin deadline) is more than POSIX sh should hold. The partial is a thin sh
function around a single-quoted program run as `command python3 -I -c`:
`command` defeats a shadowing function (LESSON-717) and `-I` keeps a planted
`json.py` in the repo, the working directory of a session-start hook, out of
`sys.path`. `-I` is safe here because the program is stdlib only; it would break
`lessons.sh`, which needs PyYAML. With no `python3` the function returns 0 and
writes nothing: rung (b) still works.

The detection table is one `TABLE = {...}` JSON line in that program, read by a
test and compared with `harness/claude.yml`'s `hook_payload`. It holds `claude`
alone: a row is added from a captured payload, never from a survey (OQ-1).

### ADR-5: Unproven formats refuse

`extract-chat --format codex|copilot|gemini|cursor` exits non-zero with one stderr
line and writes nothing. `/wrapup`'s existing `extract-chat failed` branch then
runs Fallback drafting with `invoked` unset, which telemetry records as `fallback`,
not `ghost-skip`. The alternative, parsers written from `codex-portability.md`,
would be an invented shape that could emit partial text to a delegate. `cursor` is
not aliased to `claude` either: the alias is exactly the claim a fixture must prove.

### ADR-6: `extract-chat` reads the record's `type`

The captured fixture session showed `api-request-blob` records whose `message` has
role `user` and holds injected `<system-reminder>` context, which is where the
user's email and CLAUDE.md text live. The pre-change parser never read `type`, so
those became `## Human` sections and went to the delegate. A record whose `type` is
present and is neither `user` nor `assistant` is now dropped before `message` is
read. A record with no `type` still parses, because the existing tests and older
transcripts carry none. This narrows LESSON-746's exposure without replacing its
rule: `/wrapup` keeps `ADLC_DISABLE_DELEGATE=1` in this repo's close-outs.

### ADR-7: Sidecar lifecycle

Retention is 30 days by `mtime`, swept by the writer. The `.gitignore` of `*` the
stub wrote inside `.adlc/.session/` stays, alongside the new top-level ignore line:
a consumer has the hook as soon as the render lands but gets the top-level line
only from a re-run of `/init`, and a sidecar holds a home path. Temporary files
start with a dot, as does the `.gitignore`, and discovery skips dotfiles.

### ADR-8: A hook command spells the plugin root unbraced

Found in Phase 4 by running the render through the real binary. On Claude Code
2.1.258, a project hook whose command contains the literal `${CLAUDE_PLUGIN_ROOT}`
does not run: no error, no output. Bisecting one setting and one token at a time
showed that `plain`, `$CLAUDE_PLUGIN_ROOT`, `${HOME}` and a multi-line command all
fire, and only the braced token does not. REQ-657 rendered the canonical root line
into both hooks, so neither has ever run in a session, while every test passed
because the tests run the text through `sh`. That is why ASSUME-013 stayed open.

The token exists for skill text, which Claude Code rewrites on the plugin route. A
project hook gets no rewrite and no such variable, so `$CLAUDE_PLUGIN_ROOT` expands
empty and the pointer-file arm serves the plugin route. `hooks/hooks.json` is a
plugin hook, where the token is valid, and is untouched. `HOOK_ROOT_LINE` is derived
from `TOOLKIT_ROOT_LINE` in `check.py`, so the two cannot drift, and `unguarded-source`
refuses the braced token in `templates/hooks.yml` and every render.

Consumers whose `.claude/settings.json` was rendered before this REQ keep a hook that
never runs until they re-render. `/template-drift` reports it as `harness-config`.

Two consequences. In a project hook the first arm of the line is now dead, so on a
machine with both installs the symlink copy wins, which is what a fence does there
too. And the hooks are live for the first time, so `.adlc/partials/*.sh` is sourced at
session start. That is the REQ-610 two-level rule BR-8 requires, and it adds no
attack: a repo able to commit a partial can as easily commit a hook in
`.claude/settings.json`. ADR-4's `-I` guards against a planted module for that reason
only, and does not claim to contain a hostile vendored partial.

### ADR-9: A root that is a symlink is followed

`find` keeps its trailing slash (BUG-253), so a harness home moved to another volume
still works, and the walk can then read outside `$HOME`. Rung (a) stays strict because
a sidecar is repo content and a root is not. Nothing is returned from a followed root
unless it holds the fresh mark, so BR-9 and BR-16 state the exception rather than
removing it.

## Files

Hook: `partials/session-record.sh`, `partials/tests/hooks.test.sh`,
`tools/adlc/tests/test_session_record_table.py`, `templates/hooks.yml`, the renders.
Discovery: `partials/session-transcript.sh`, `partials/tests/session-transcript.test.sh`,
`tools/lint-skills/check.py`, `tools/lint-skills/tests/test_toolkit_path.py`,
`tools/lint-skills/README.md`. Parser: `tools/delegate/extract-chat`,
`tools/delegate/tests/test_extract_chat.py`, the fixture. Skill: `wrapup/SKILL.md`.
Gitignore: `.gitignore`, `init/SKILL.md`, the lint check. Docs: `README.md`,
`tools/delegate/README.md`, `partials/README.md`,
`.adlc/context/architecture.md`, `CHANGELOG.md`.

## Constraints from exploration

- The fake `extract-chat` in `tools/lint-skills/tests/test_read_bin_fences.py`
  writes to `$3`, so `--format` goes after `-o "$TMPFILE"`.
- `tools/delegate/claude-md-routing.txt` is hash-pinned: leave it.
- No fixture text may contain the banned brand word `test_no_kimi_brand.py` scans.
- `tools/lint-skills/README.md` is read by four tests: edit it additively.

## Applicable lessons

LESSON-733 and LESSON-734 (the mark), LESSON-746 (email in transcripts), LESSON-717
(`command`, `find -exec grep`), LESSON-335 (no bare glob under zsh), LESSON-013
(`-F`, never `\b`), LESSON-755 (the matcher), LESSON-751 (re-measure at Phase 1).
