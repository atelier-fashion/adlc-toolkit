# REQ-660 verification

Live runs of 2026-10-30. Every run that used the real `claude` binary used a throwaway
`HOME` and `ADLC_HOME`, and paths below are written `<T>`.

## The rendered hooks ran for the first time

Claude Code 2.1.258, headless, logged out, in a throwaway project. A logged-out run
still fires `SessionStart` and writes a transcript before its API call fails.

| Command text in the project hook | Fired |
|---|---|
| plain `cat`/`echo` | yes |
| `$CLAUDE_PLUGIN_ROOT` | yes |
| `${HOME}` | yes |
| a multi-line command | yes |
| `${CLAUDE_PLUGIN_ROOT}` | **no** |

Removing `_comment`, `permissions.allow`, `permissions.ask` or `defaultMode` from the
render changed nothing, so the token alone stops the hook.

With the committed render, `harness/claude/rendered/settings.json`:

```
harness=claude
session_id=ad7d9773-b214-4240-b20d-13f6f8607701
transcript_path=<T>/home/.claude/projects/<encoded cwd>/ad7d9773-b214-4240-b20d-13f6f8607701.jsonl
cwd=<T>/proj
started_at=2026-10-30T20:43:33Z
```

- The file is mode 0600 and the transcript it names exists.
- `claude --resume <id>` rewrote the same file with the same `started_at`, and there
  was still one sidecar.
- `git status --porcelain` was empty.
- Both `SessionStart` hooks exited 0, and `ethos-inject`'s stdout reached the session.

This session, a Claude Code 2.1.309 desktop session started from the old render, has
no `.adlc/.session/`. That binary is a Linux VM build, so 2.1.309 was not tested
directly.

The same run in a linked worktree, `<T>/main/.claude/worktrees/wt`, wrote a full sidecar
with that path as `cwd`, and `git status --porcelain` there was empty.

In both runs the throwaway project had no `.adlc/partials/`, and `~/.claude/skills/partials`
in the throwaway `HOME` was a symlink to this branch's `partials/`. So the command
resolved through the toolkit copy, as a consumer with no vendored partial does.

## Discovery against this session

Walk, with no sidecar present, from a mark printed in an earlier tool call:

```
/wrapup: session JSONL — matched this run's mark in f9dd0613-6799-4756-98e8-f021e4108aa2.jsonl via walk:claude
```

Sidecar, after piping this session's real id and path through the rendered hook command
with this branch's partial, since the session's own start predates the fix:

```
/wrapup: session JSONL — matched this run's mark in f9dd0613-6799-4756-98e8-f021e4108aa2.jsonl via sidecar
```

`adlc_transcript_format` returned `claude` both times, and `extract-chat --format claude`
produced 1,311 lines. The sidecar was then deleted. With `~/.claude/skills` still on `main`,
the same command ran the old stub, wrote a pathless sidecar, and the walk found the
transcript, so a stale partial degrades safely.

## The record-type filter, on this session's real transcript

| | Before | After |
|---|---|---|
| Output size | 224,326 bytes | 105,016 bytes |
| Lines with `<system-reminder>` | 18 | 3 |
| Lines with the user's email address | 1 | 0 |

The three remaining lines are this session discussing the tag in its own turns.

## Acceptance criteria

| AC | Result |
|---|---|
| AC-1 | Pass on 2.1.258 in a linked worktree: fields, `git status`, and `--resume` keeping `started_at` (in the non-worktree run). Headless and logged out under a throwaway `HOME`. Not seen in an interactive session |
| AC-2 | Pass: `hooks.test.sh` |
| AC-3 | Partial. The `via sidecar` line and format are live, above, on a hand-fired hook. A full `/wrapup` delegating from a sidecar was not run: this repo's close-outs set `ADLC_DISABLE_DELEGATE=1` (LESSON-746), so `mode=delegated` on that path is unobserved |
| AC-4 | Pass for selection: `session-transcript.test.sh`. The telemetry half was checked by reading `emit-step-telemetry.sh`: `invoked` unset gives `fallback` |
| AC-5, AC-6, AC-13 | Pass: `session-transcript.test.sh` |
| AC-7 | Pass: the golden is the merge-base parser's output |
| AC-8 | `claude` passes. `codex`, `copilot`, `gemini`, `cursor`: `n/a`, CLI not installed |
| AC-9 | `n/a` for every row: `copilot`, `agent`, `codex`, `gemini` and `antigravity` are not on PATH, and REQ-655, REQ-656 and REQ-658 have not landed |
| AC-10 | Claude Code on the as-is render passes, and the no-vendored-partial resolution passes, above. Untrusted path: headless 2.1.258 fired the hooks in an untrusted workspace, with a warning about the allowlist only, so the spec's "no sidecar on an untrusted path" did not hold there. Interactive untrusted behaviour was not tested. Every other harness: `n/a`, as AC-9 |
| AC-11 | Pass: lint, and `git diff` touches none of the listed files |
| AC-12 | Pass for the lint and the lines: `test_session_gitignore.py`, and the docs name the surfaces. "A consumer re-running `/init` gains the line" is `/init` following its Step 5 text, which the lint holds; `/init` itself was not run |
