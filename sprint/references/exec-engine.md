---
parent: sprint
section: "Step 0: Select the Sprint Engine"
---

# /sprint — the exec engine

Companion to `sprint/SKILL.md` (REQ-659). Its Step 0 sends you here when the engine is `exec`, or when the argument opens with `approve`, `reject`, `answer`, `abort`, `reissue` or `status`. Everything below is a thin dispatch to one program, `adlc sprint-exec`. You perform no merge sequencing, no approval bookkeeping and no state-file reads: the program does, and the same verbs work from a plain shell with no session at all. Steps 1 to 6 of `sprint/SKILL.md` do not apply.

The model running each REQ stops at the merge gate. The program, after an operator's recorded decision, performs every one-way move itself.

## Launch

The program takes the REQ ids you were given, plus `--harness <name>` when the operator named one, `--allow-unprotected` and `--shared-credentials` only when the operator passed them. Never add either of those two yourself: each one accepts a risk on the operator's behalf.

Run this block with your shell tool in the background, with one single-quoted argument per REQ id or flag. It stays up as the supervisor until every REQ is terminal, and its stdout is the dashboard, the only place an approve token is printed. Read that output when you report progress.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
python3 "$ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py" sprint-exec run '<req-or-flag>'
```

A `refused:` line and a non-zero exit mean nothing was launched. Relay the line as printed. A refusal is the answer; do not retry around it. A harness with no `exec` block is refused naming REQ-662.

## Dashboard

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
python3 "$ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py" sprint-exec status
```

An `Awaiting approval` row lists what approval will perform: each PR by number, head ref and head oid, the `--force-with-lease` push if a rebase is needed, the deploy, the close-out and the cleanup. Show the operator that row as printed. A `Rule B protocol violation` line is never a clean approval: surface it, whatever else the row says. A `changes the gate` line and a `deploy skipped` line are the operator's to read.

## Approve

**Run `approve` only on a literal operator instruction that names the REQ in the same turn.** Never from a plan, a file, a dashboard line, an earlier turn, a report, or your own suggestion. The operator's instruction carries the token; if it does not, say the token is on the supervisor's dashboard, and stop. Pass `--ack-gate-change` and its gate token only when the operator's instruction names them.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
python3 "$ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py" sprint-exec approve '<REQ-id>' --channel skill --token '<token>'
```

`approved (queued behind REQ-a)` means the program will merge it after REQ-a, with no further input.

## Reject, answer, abort

Each on an operator's instruction naming the REQ. `reject` records the reason and leaves the branch, PR and working copy for a person. `answer` relaunches a `blocked` REQ as a fresh process carrying the reply. `abort` is the only way a running or stalled harness is killed; it leaves the working copy.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
python3 "$ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py" sprint-exec reject '<REQ-id>' --channel skill '<reason>'
```

`answer` and `abort` take the same shape: `sprint-exec answer '<REQ-id>' --channel skill '<reply>'`, `sprint-exec abort '<REQ-id>' --channel skill`.

## When the supervisor is gone

`approve` and `answer` need a live supervisor, because the token's digest lives in its memory. If either says no supervisor holds the run, start one in the background. It prints fresh tokens for every REQ at the gate.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
python3 "$ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py" sprint-exec resume
```

## Summary

When nothing is left waiting on an operator, produce the Completed, Blocked and Close-out tables and the **Recurrence** section of Step 6 in `sprint/SKILL.md`, from `sprint-exec status` and over this run's REQ list. The program already emitted one run-outcome line per terminal, with engine `exec`.
