---
id: REQ-660
title: "Session sidecar and multi-harness transcripts for the /wrapup knowledge loop"
status: complete
deployable: false
created: 2026-10-27
updated: 2026-10-30
component: "adlc/wrapup"
domain: "adlc"
stack: ["bash", "python", "markdown", "jsonl"]
concerns: ["reliability", "privacy", "portability", "harness-agnostic", "correctness"]
tags: ["wrapup", "extract-chat", "transcript", "transcripts", "session", "sidecar", "hooks", "hook", "multi-harness", "harness", "codex", "copilot", "gemini", "cursor", "fixtures", "jsonl-discovery", "session-routing", "delegation", "knowledge-capture", "gitignore", "self-mark", "worktree"]
lane: "full"
lane_reason: "footprint far above max_files (wrapup/SKILL.md, extract-chat, the transcript partial, the session-record partial, gitignore and /init surfaces, a fixture and tests) and it ships the command every harness's session-start hook runs"
lane_forced: false
---

## Description

This is Phase 5 of `.adlc/research/multi-harness-plan.md` (revision 2): the
knowledge loop — the part of the toolkit that turns a finished session into a
`LESSON-xxx` — made to work on Copilot CLI, Codex, Gemini CLI and Cursor, not
only on Claude Code.

Today `/wrapup` Step 4 finds the session transcript by a mark it printed itself
(BUG-253, which replaced the REQ-423 walk): step 1a prints a random mark, step 1b
greps `~/.claude/projects/` for the one file holding it, and that file goes to
`extract-chat`, which understands exactly one record shape: Claude Code's
`message.role` / `message.content`. On any other harness nothing under
`~/.claude/projects/` holds the mark, so `$JSONL` stays empty and Step 4 falls
through to **Fallback drafting** from in-context memory. That is the plan's
accepted degradation for P0–P4, but it is where lesson schema v2's `evidence`
field (REQ-646) gets its transcript quotes, so a port without it is a worse
product (`codex-portability.md` §2f). Each harness keeps its transcript somewhere
different and in an undocumented shape: Codex under
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`; Copilot under
`~/.copilot/session-state/<id>/events.jsonl`; Gemini under
`~/.gemini/tmp/<project_hash>/chats/session-*.jsonl`; Cursor writes
Claude-Code-compatible JSONL and hands hooks a `transcript_path`. Every one of the
five fires a session-start hook that is expected to carry a session id and, on
Claude Code and Cursor, the transcript path (Open Question 1 confirms the field
names against real payloads).

**Revision, 2026-10-30.** This spec was written on 2026-10-27, against the REQ-423
walk and an id anchor. BUG-253 and LESSON-733 then proved the anchor wrong: an id
proves a transcript mentions the work, not that it is the run. Under `/sprint` the
anchor picked an older session that merely named the REQ. So this revision makes
the mark the acceptance check on **every** rung. That removes the locators the
original needed (cwd matching, the Gemini project hash, the Codex day window, the
`session_id` narrowing) and the "no REQ id" branch, because a mark exists on every
run and no other file can hold it. The discovery code extends
`partials/session-transcript.sh`, which BUG-253 made the sourceable, tested unit
that the planned `partials/session-discovery.sh` was going to be. Only Claude Code
is installed and probed on this machine, so `extract-chat` proves `claude` alone;
the other four are accepted flag values that refuse until a real fixture lands
(Deferred). Session-start hooks do not fire for subagents, and a run that shares a
parent's sidecar is rejected by the mark, so the walk stays essential.

Three deliverables:

1. **The session-record hook command and the session sidecar contract.**
   REQ-657 (the harness adapter framework, plan P2a) declares `session-record`
   in `templates/hooks.yml` on the canonical `session-start` event, and its
   renderer writes it into `.claude/settings.json` (which Copilot CLI and
   Cursor read as-is) for the `claude` adapter (REQ-657 BR-10); the
   `.codex/hooks.json` and `.gemini/settings.json` renders arrive with the
   Codex and Gemini adapters (REQ-655, REQ-658) and the
   `.github/hooks/adlc.json` render with the Copilot adapter (REQ-656 BR-5).
   This REQ owns what that entry
   runs and what it leaves behind: `partials/session-record.sh`, the
   partial-backed command the entry's `command` string names, which at session
   start writes the **session sidecar** `.adlc/.session/<id>` ("sidecar" below;
   the `/wrapup` flag file written by `skill-flag.sh` is always called the
   "flag file") with the harness name, the session id, the transcript path
   when the payload carries one, the working tree and a start timestamp — and
   the contract `/wrapup` reads it by. The sidecar directory is gitignored and
   the hook prunes old entries, so nothing accumulates and nothing is
   committed.
2. **`/wrapup` reads the session sidecar first.** Step 4's discovery becomes a
   chain: sidecar → per-harness walk over the Claude, Codex, Copilot and Gemini
   roots (Cursor has a sidecar rung only, Open Question 3) → Fallback drafting.
   Every rung keeps the BUG-253 contract: the candidate must hold this run's
   mark, no holder or several holders refuses rather than guesses, the search
   never leaves `$HOME`, and exactly one stderr line says what was chosen and why.
3. **`extract-chat --format claude|codex|copilot|gemini|cursor`.** One parser per
   record shape, all producing today's `## Human` / `## Assistant` text with tool
   calls, tool results, images and base64 stripped, so the delegate's `--question`
   and the capture rules downstream are untouched. A format ships a parser only
   when one **real** transcript captured from an actual session on that harness
   proves it (plan §6.9 names Codex and Copilot; this REQ extends the rule to all
   five), redacted and trimmed, with a parser test. A format without one exits
   non-zero, so `/wrapup` falls through to Fallback drafting rather than parsing
   a guessed shape.

Nothing about the lesson changes: not the schema (REQ-646), not the capture
rules, not the `adlc-read --question` text, not post-validation. Only where the
evidence comes from.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| SessionSidecar | path | path | `<working tree>/.adlc/.session/<id>`; one file per session; written only when `<working tree>/.adlc/` already exists |
| SessionSidecar | harness | enum | `claude` / `copilot` / `codex` / `gemini` / `cursor` / `unknown`; always present; `unknown` when the entry carries no `--harness` argument and the payload matches no row of the partial's detection table (BR-6) |
| SessionSidecar | session_id | string | the harness's own id when the payload carries a safe one, else an id the hook generates; `^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$` (no leading dot, so never `.`, `..` or `.gitignore`), used as the file name |
| SessionSidecar | transcript_path | path or empty | absolute path under `$HOME` when the payload carries one (Claude, Cursor); empty otherwise; never a path outside `$HOME` |
| SessionSidecar | cwd | path | the working tree the hook ran in, as given by the payload or `$PWD` |
| SessionSidecar | started_at | timestamp | UTC, ISO-8601, set at first write; a re-fire for the same id (resume) rewrites the file and keeps `started_at` |
| SessionSidecar | format | rule | plain `key=value` lines, one per field, in the order `harness`, `session_id`, `transcript_path`, `cwd`, `started_at`; readable with POSIX sh and no JSON parser |
| SessionSidecar | mode | perm | 0600; never a credential |
| DiscoveryResult | source | enum | `sidecar` / `walk:claude` / `walk:codex` / `walk:copilot` / `walk:gemini` / `none`; no `walk:cursor` — Cursor has a sidecar rung only (Open Question 3) |
| DiscoveryResult | transcript | path or empty | the one file holding this run's mark; empty means Fallback drafting |
| DiscoveryResult | format | enum | the `extract-chat --format` value to use: the sidecar's `harness` at rung (a), the root the file was found under at rung (b) |
| DiscoveryResult | reason | string | the single stderr line's reason (`matched this run's mark in <basename> via sidecar`, `… REFUSING`, `no sidecar and no candidates under any harness root`) |
| HarnessRoot | harness | enum | `claude` / `codex` / `copilot` / `gemini` — the four harnesses with a walkable root; Cursor is sidecar-only (Open Question 3) |
| HarnessRoot | root | path | `~/.claude/projects`, `~/.codex/sessions`, `~/.copilot/session-state`, `~/.gemini/tmp`; every root is under `$HOME` and is spelled from `$HOME`, never `$ADLC_HOME` (BR-9) |
| HarnessRoot | search | rule | files named `*.jsonl` (Claude, depth 5), `rollout-*.jsonl` (Codex, depth 4), `events.jsonl` (Copilot, depth 2), `session-*.jsonl` (Gemini, depth 3), modified in the last 60 minutes, holding the mark as a fixed string. There is no cwd, project-hash or session-id locator: the mark decides, and a transcript that holds a mark printed a moment ago was by definition written in that window |
| TranscriptFixture | path | path | `tools/delegate/tests/fixtures/transcripts/<harness>.jsonl` plus `<harness>.expected.txt`; captured from a real session, redacted, trimmed; `claude` in this REQ, the others when each harness can be captured |
| TranscriptFixture | provenance | record | harness name and version, capture date, what was removed; recorded beside the fixture |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| session_recorded | the harness's session-start hook (`SessionStart` on Claude Code, Codex, Gemini and Cursor — Cursor sees the key from the as-is `.claude/settings.json`, as does Copilot's read of that file; `sessionStart` in Copilot's own `.github/hooks/adlc.json`) | the session sidecar written or rewritten; nothing on stdout that the harness would inject as context; exit 0 always |
| sidecar_pruned | every hook run | sidecars older than the retention window removed from the same directory; count reported nowhere (silent) |
| transcript_resolved | `/wrapup` Step 4 step 1 | one stderr line naming source, basename and reason; the chosen path and format persisted to the flag file (`skill-flag.sh mark`) for step 2 |
| discovery_refused | no candidate from any rung holds this run's mark, or more than one does | one stderr line; `$JSONL` empty; Fallback drafting |
| chat_extracted | `/wrapup` Step 4 step 2 | `extract-chat --format <format> <transcript> -o <tmpfile>`; same output contract as today |

_Permissions: not applicable — single-user machine tooling that reads the user's own session data under `$HOME`. Section omitted deliberately._

## Business Rules

- [ ] BR-1: **The session sidecar is the first rung, never the only one.** `/wrapup` Step 4 step 1 resolves the transcript in this order and stops at the first rung with a file holding this run's mark: (a) every `.adlc/.session/*` sidecar in the current working tree (`git rev-parse --show-toplevel`, else `$PWD`); (b) the walk over every HarnessRoot that exists on the machine; (c) Fallback drafting. A rung whose candidates do not hold the mark does not stop the chain, and only when every rung is exhausted does the refusal fire. Step 1a, which prints the mark, stays its own tool call: a running command is not yet in its own transcript (BUG-253). (informed by BUG-253, LESSON-733, LESSON-483)
- [ ] BR-2: **The mark is the one acceptance check, on every rung.** A candidate is accepted only if it holds this run's mark as a fixed string. An id anchor proves a transcript mentions the work, not that it is the run (LESSON-733), so no rung reads the REQ id. A sidecar whose `transcript_path` is empty, missing on disk, a symlink, outside `$HOME` after resolving its directory, or carrying a `..` segment, or whose `harness` is `unknown` or outside the enum, contributes nothing and rung (b) runs. Two sidecars naming one file are one candidate. (informed by BUG-253, LESSON-733, LESSON-013)
- [ ] BR-3: **Refuse, do not guess.** When no rung produced a file holding the mark, or a rung produced more than one distinct file (a forked copy), `$JSONL` stays empty, exactly one stderr line says so naming the rungs tried and the candidate counts, and control reaches Fallback drafting. A sidecar's presence never licenses delegating a transcript the mark check rejected: a planted sidecar naming another file under `$HOME` cannot pass, because that file cannot hold a mark generated a moment ago. (informed by BUG-253, LESSON-483)
- [ ] BR-4: **One stderr line per invocation, extended not replaced.** The line carries the prefix `/wrapup: session JSONL —` (REQ-423 BR-4, dropped by BUG-253, restored here) and gains the source: `matched this run's mark in <basename> via sidecar`, `… via walk:<harness>`, `no sidecar and no candidates under any harness root`, or the refusal. Close-out mode (BUG-249) still skips discovery entirely and emits nothing here. (informed by REQ-423 BR-4, LESSON-008 point 5)
- [ ] BR-5: **The hook is inert outside an ADLC working tree and never fails a session.** It writes only when `<cwd>/.adlc/` exists, writes only under `<cwd>/.adlc/.session/` and only mode 600, exits 0 on every path including a malformed or empty payload, prints nothing to stdout (every harness injects session-start stdout as model context), finishes well inside the entry's `timeout_s` (REQ-657), including after Gemini's unit conversion (REQ-658), and needs nothing beyond POSIX sh and `python3` stdlib — no `jq`, no network, no toolkit install. A machine with no toolkit and a repo with the hook entry committed must not break session start.
- [ ] BR-6: **The session sidecar records what the harness gives, no more.** `harness` and `session_id` are always written; `harness` is written by the command from, in order: (1) a `--harness <name>` argument when the rendered entry carries one, with `--field <item>=<key>` naming the payload key for `session_id`, `cwd` and `transcript_path`, both spelled by REQ-657's `harness_render.hook_args` from that adapter's `hook_payload`, and an item absent from the arguments is not read; (2) otherwise, for the `claude` render that Claude Code, Copilot CLI and Cursor all read, a detection table **embedded in the partial** (POSIX sh + `python3` stdlib cannot read `harness/*.yml` at session start); (3) `harness=unknown` when neither applies, and `/wrapup` treats `unknown` as pathless at rung (a). The table holds only rows read off a real payload: `claude`, captured from Claude Code 2.1.258 on 2026-10-30 (`session_id`, `transcript_path`, `cwd`, `hook_event_name`, `source`; distinguished by a `transcript_path` under `/.claude/projects/`), asserted equal to `hook_payload` in `harness/claude.yml` by a test. A `copilot` or `cursor` row is added only from a captured payload (OQ-1); until then both record `unknown` and fail closed, and the test checks `harness/copilot.yml` only when it exists and declares a field other than `unsupported`. `transcript_path` only when the payload carries one and it resolves under `$HOME`; `cwd` from the payload, else `$PWD`. The hook never derives, guesses or searches for a transcript path. A re-fire for the same session id (Claude `--resume`) rewrites the file in place; two sessions in one working tree produce two files. A second fire for the same session from a second hook file (Copilot reads both `.claude/settings.json` and `.github/hooks/adlc.json`, REQ-656 OQ-1) is a rewrite in place when the payload carries an id; when it does not, the second fire produces a second sidecar with a generated id, which rung (a) ignores because both are pathless.
- [ ] BR-7: **Gitignored everywhere and pruned by the writer.** `.adlc/.session/` is added to this repo's `.gitignore` and to the gitignore lines `/init` writes for consumer projects; `git status` in a working tree with sidecars present shows nothing. Each hook run deletes sidecars in the same directory older than the retention window (a constant the architecture fixes; 30 days is the proposal) so the directory is bounded without a scheduled job. `/wrapup` never deletes a sidecar. (informed by REQ-654 BR-13 posture — a seam that must not silently close: the gitignore line is checked by the lint in BR-15)
- [ ] BR-8: **One hook command, one entry, rendered by the framework.** The `session-record` entry in `templates/hooks.yml` and its `claude` render into `.claude/settings.json` (read as-is by Copilot CLI and Cursor) are REQ-657 BR-10's; the `.codex/hooks.json` and `.gemini/settings.json` renders are the Codex and Gemini adapters' (REQ-655, REQ-658) and the `.github/hooks/adlc.json` render is the Copilot adapter's (REQ-656 BR-5); this REQ ships `partials/session-record.sh`, the command that entry runs — a partial reached through the REQ-610 two-level sourcing spelling, so a consumer with a vendored copy and a bare machine with only `~/.claude/skills` both resolve it — and the per-harness payload-field mapping the command needs (Open Question 1). The two REQs share exactly one seam: the entry's `command` string, which names this REQ's partial; REQ-657 specifies nothing about the file the command writes. Where a harness loads project config only for trusted paths (Copilot, Codex, Gemini, Cursor — plan §1), an untrusted path simply has no sidecar and `/wrapup` runs rung (b); this REQ does not touch trust. **A hook command never holds the braced `${CLAUDE_PLUGIN_ROOT}` token:** Claude Code 2.1.258 does not run a project hook whose command contains it, so REQ-657's renders never fired on any session until this REQ. `templates/hooks.yml` spells the root line with the variable unbraced, and `unguarded-source` fails the braced spelling in `templates/hooks.yml` and in every committed render. (informed by REQ-610 BR-3)
- [ ] BR-9: **Per-harness discovery is bounded and contained.** Rung (b) scans each HarnessRoot that exists, with the depth, name and 60-minute bounds of the HarnessRoot table, following no symlinked file. A root that is itself a symlink is followed, as BUG-253 chose for a harness home on another volume: the walk may then read outside `$HOME`, and returns nothing but a file holding the mark. A root that is absent is skipped silently; a root that holds nothing recent contributes zero candidates. Harness roots are the harnesses' own data directories, never toolkit state: each is spelled from `$HOME`, not `$ADLC_HOME`, marked `# adlc-home: claude-code` (or registered in the lint's exception list for the other three), so the REQ-654 BR-13 and REQ-666 `no-harness-path` lints stay clean. (informed by BUG-253, REQ-423 BR-6)
- [ ] BR-10: **`extract-chat --format` is explicit, defaults to today's behaviour, and emits today's shape.** `--format` accepts exactly `claude`, `codex`, `copilot`, `gemini`, `cursor`; omitted means `claude`, so every existing caller and test is unchanged byte-for-byte. Every parser yields the same `## Human` / `## Assistant` sections, drops tool calls, tool results, system and harness-internal records, images, data URIs and raw base64 under the existing `_RAW_BASE64_MIN_LEN` rule, and skips malformed lines. A record whose `type` is present and is neither `user` nor `assistant` is harness-internal and is dropped before its `message` is read: Claude Code's `api-request-blob` records carry a `message` with role `user` holding injected context, which the pre-change parser emitted as `## Human` text. A format with no parser exits non-zero with one stderr line naming the missing proof and writes nothing to `-o`; the exit paths are that, an unreadable input, an unwritable `-o` target, and an unknown format. `cursor` joins `claude` as an alias only once a real fixture proves the shapes identical, but the flag value exists regardless so `/wrapup` can pass the sidecar's `harness` through unchanged. (informed by REQ-414 BR-2 — same artifact shape on every path)
- [ ] BR-11: **One real fixture per proven format, captured, redacted and trimmed.** A format ships a parser only with a transcript captured from an actual session on that harness (not synthesised, not hand-written — plan §6.9's rule for Codex and Copilot, applied to all five), trimmed to a small number of turns that still exercise a tool call, a tool result and a plain reply, redacted with the REQ-415 five-pattern credential chain and with every home-directory path rewritten to `~/`, free of any email address, and accompanied by its expected `extract-chat` output and a provenance note (harness, version, capture date, what was cut). A fixture is replaced, never edited by hand, when a harness's schema changes. This REQ ships `claude`; the other four are Deferred with the reason. (informed by REQ-646 BR-12, BR-13; LESSON-008 point 4)
- [ ] BR-12: **A parser test per proven format, plus the discovery matrix.** `tools/delegate/tests/test_extract_chat.py` gains a golden test (fixture in → expected text out, byte-equal) and a negative test (no `tool_use`/`tool_result`/harness-internal content survives) for each proven format, and a refusal test for each unproven one. `partials/tests/session-transcript.test.sh` gains the discovery matrix with sidecars: sidecar-with-path wins when it holds the mark; sidecar-with-path that does not hold it falls to the walk; a pathless or `unknown` sidecar falls to the walk; a stale sidecar for an older session on the same REQ loses to the transcript holding the mark; a walk hit under each of the four roots names its harness and format; two distinct holders refuse; no holder anywhere refuses. Both suites run under bash 3.2, zsh and `/bin/sh` as today. (informed by BUG-253 verification, REQ-610 BR-11)
- [ ] BR-13: **Nothing about the lesson changes.** `templates/lesson-template.md`, `partials/lesson-check.sh`, the `<!-- lesson-capture-rules -->` block, the delegated `--question` text, post-validation, the summary slot and telemetry schema (`mode` vocabulary, `ghost-skip` rewrite) are not modified. The only `/wrapup` edits are in Step 4 step 1 (discovery) and the `extract-chat` invocation in step 2, which gains `--format`. Prose-only renames of the existing 'sidecar' wording for the flag file (`wrapup/SKILL.md` lines 175, 198, 221, 231 and 353 as of 2026-10-30, 221 and 231 being comment lines inside a fence) to 'flag file' are permitted. The `invoked`/`exit` marks and the telemetry resolver are untouched, so a sidecar-resolved transcript records `mode=delegated` exactly as a walk-resolved one does today, and a format with no parser reaches the existing `extract-chat failed` line with `invoked` unset, recorded as `fallback`, never `ghost-skip`. Step 2 reads the format from the flag file and an absent `format` key means `claude`, so the close-out block (BUG-249), which marks `jsonl` empty and never writes `format`, needs no edit. (informed by REQ-646 BR-2, BR-4; REQ-522 BR-4, BR-6; REQ-424)
- [ ] BR-14: **Fence discipline holds.** Whatever lands in `wrapup/SKILL.md` keeps every fenced block self-contained: the chosen path and format cross to step 2 only through the flag file (`skill-flag.sh mark`/`read`), never a shell variable; a shared function is re-sourced in the block that calls it; no `\b` in `grep -E`, no `[[`, no `local`, no bare `$<digit>`, no `[0]` indexing; `tools/lint-skills` stays clean. `wrapup/SKILL.md` stays under the 500-line `skill-line-budget` (475 on 2026-10-30), or the step moves whole into a read-and-follow companion (REQ-661). Discovery extends `partials/session-transcript.sh`, keeping `adlc_transcript_find <mark>`'s stdout-and-rc contract and adding `adlc_transcript_format <path>`, so a consumer whose vendored copy is stale keeps today's Claude behaviour instead of breaking, as REQ-646 BR-9 and REQ-654 BR-3 accept for `stale`. (informed by REQ-522 BR-4, BR-5; REQ-610; LESSON-582; LESSON-013)
- [ ] BR-15: **Documentation and lint move with the change.** `README.md` and `tools/delegate/README.md` document `--format` and the sidecar; `.adlc/context/architecture.md`'s knowledge-retrieval paragraph names the three-rung chain; `CHANGELOG.md` names the consumer re-sync (settings.json hook entry, gitignore line, vendored partial) as the follow-up. `tools/lint-skills` gains a check that `.adlc/.session/` is present in the gitignore lines `/init` writes, so the sidecar cannot start leaking into consumer commits through a later edit. (informed by LESSON-012, LESSON-019)
- [ ] BR-16: **Privacy posture.** A session sidecar holds a home-directory path; it is written mode 600 and stays on the machine (gitignored, never read by anything but `/wrapup`, never copied into a lesson — REQ-646 BR-12 already rejects home paths in `evidence`). The transcript still passes through the existing `mktemp` + redaction step before `adlc-read` sees it, on every format. Discovery reads the four named roots, and each sidecar's `transcript_path` only if it resolves under `$HOME`; at most 64 sidecars are read, because a repo can commit them, and such a read answers one yes-or-no question about the mark, so nothing reaches `extract-chat` or a delegate without it. (informed by LESSON-008 points 3–4, REQ-423 BR-6)

## Acceptance Criteria

- [ ] AC-1: In a Claude Code session opened inside a harness worktree with `.adlc/` present, a sidecar appears at `<worktree>/.adlc/.session/<session_id>` within the first turn, naming `harness=claude`, the session id, a `transcript_path` under `~/.claude/projects/` that exists, and the worktree as `cwd`; `git status` shows nothing new; `claude --resume` of the same session rewrites the file with the same `started_at`. (BR-5, BR-6, BR-7)
- [ ] AC-2: In a directory with no `.adlc/`, the same hook run writes nothing anywhere and exits 0; fed an empty stdin, a non-JSON stdin and a payload with no id field, it exits 0 each time, prints nothing to stdout, and writes at most a sidecar with a generated id; its wall time on the test machine is inside the entry's `timeout_s` (REQ-657), including after Gemini's unit conversion (REQ-658). (BR-5)
- [ ] AC-3: `/wrapup REQ-xxx` in that worktree emits exactly one `/wrapup: session JSONL —` line ending `via sidecar`, naming the transcript's basename, and the delegated path runs against that file; the telemetry record shows `mode=delegated`. Delegation is off on machines where `delegate.enabled` is false, so the delegated half is exercised by the partial test and by a live run only where it is on. (BR-1, BR-4, BR-13)
- [ ] AC-4: With the sidecar's `transcript_path` pointing at a transcript that does **not** hold the mark, while a file under `~/.claude/projects` does, the line reads `via walk:claude` and that transcript is used; with no candidate anywhere holding it, the line is the refusal, `$JSONL` is empty, Fallback drafting runs and the telemetry resolver records what it records today for a no-transcript run. (BR-1, BR-2, BR-3)
- [ ] AC-5: In `partials/tests/session-transcript.test.sh`, run under bash 3.2, zsh and `/bin/sh` via `sh partials/tests/run.sh`, every row of the BR-12 matrix produces the stated outcome and the stated stderr reason, and the suite exits 0. (BR-12, BR-14)
- [ ] AC-6: A sidecar whose `transcript_path` is `/etc/passwd`, contains `..`, or is deleted after the hook ran is treated as pathless: rung (b) runs, nothing outside `$HOME` is opened (the test runs with `HOME` set to a sandbox directory, places the rejected targets outside it, and asserts `$JSONL` is empty or names a path under `$HOME`), and the stderr line does not name the rejected path. (BR-2, BR-9, BR-16)
- [ ] AC-7: `tools/delegate/tests/fixtures/transcripts/claude.jsonl` and `claude.expected.txt` are produced **before** the parser is touched, `claude.expected.txt` being the output of the pre-change `extract-chat` (`git show <merge-base>:tools/delegate/extract-chat`) on that fixture; after the change, `extract-chat claude.jsonl` with no `--format` equals it byte-for-byte (the trimmed fixture carries no `api-request-blob` record; that drop is proved by its own test), and `pytest tools/delegate/tests` passes with every pre-existing test unchanged (a mirror-of-the-parser test may gain the new flag). `extract-chat --format bogus` exits non-zero naming the accepted values. The order is proved by that regeneration, not by a separate commit, because one PR is one commit. (BR-10)
- [ ] AC-8: For `claude`: `extract-chat --format claude tools/delegate/tests/fixtures/transcripts/claude.jsonl` equals `claude.expected.txt` byte-for-byte; the output contains at least one `## Human` and one `## Assistant` section; `grep -c` for the fixture's tool-call and tool-result markers in the output is 0; the provenance note names a harness version and a capture date; and `grep -E` for the five credential patterns, for `/Users/|/home/`, and for an email address over the fixture finds nothing. For `codex`, `copilot`, `gemini`, `cursor`: `n/a` until a real session can be captured (not installed here, Deferred); each exits non-zero with its reason and writes no output. (BR-10, BR-11, BR-12)
- [ ] AC-9: On the `atelier-fashion` test bed, a Codex session and a Copilot session each run `/spec` → `/proceed` (lite) → `/wrapup`, and `/wrapup`'s stderr line ends `via sidecar` on each; with the sidecar directory emptied first, the line ends `via walk:codex` / `via walk:copilot` and names a transcript under that harness's root. Cursor and Gemini repeat the sidecar half; Cursor's walk half is `n/a` by design (sidecar rung only, Open Question 3). A harness whose CLI is not installed or whose adapter (REQ-655, REQ-656, REQ-658) has not landed is recorded `n/a` with that reason (External Dependencies). (BR-1, BR-8, BR-9)
- [ ] AC-10: With REQ-657's `claude` render in place, the as-is `.claude/settings.json` for Claude Code, Copilot and Cursor and — once the Codex, Gemini and Copilot adapters (REQ-655, REQ-658, REQ-656 BR-5) have landed — the rendered `.codex/hooks.json`, `.gemini/settings.json` and `.github/hooks/adlc.json` each fire the command on session start on a trusted path and produce a sidecar with the right `harness` value (never `unknown` for a harness whose `hook_payload` map is in place); a harness whose adapter has not landed is recorded `n/a` with the reason; on an untrusted path no sidecar appears and `/wrapup` reports a rung-(b) or refusal line, never an error. Run from a consumer with no vendored partial, the command still resolves through `~/.claude/skills/partials/`. (BR-5, BR-8)
- [ ] AC-11: `git diff` of this REQ touches none of `templates/lesson-template.md`, `partials/lesson-check.sh`, the lesson-capture-rules block, the `adlc-read --question` text in `wrapup/SKILL.md`, or `tools/delegate/emit-telemetry.sh`; `tools/lint-skills/check.sh` is clean, including the lockstep check between `/wrapup` and `/bugfix` capture blocks. (BR-13, BR-14)
- [ ] AC-12: `.gitignore` here and the gitignore content `/init` writes both contain `.adlc/.session/`; deleting the line from the `/init` source makes the new lint check fail naming the file; a consumer re-running `/init` gains the line; README, delegate README, architecture and CHANGELOG carry the new surfaces. (BR-7, BR-15)
- [ ] AC-13: A sidecar older than the retention window is removed by the next hook run in that working tree, a newer one is kept, and `/wrapup` run against an empty `.adlc/.session/` behaves as a rung-(b)-only run: `via walk:<harness>` when a root holds a matching transcript, otherwise AC-4's refusal. (BR-7)

## External Dependencies

- **REQ-657 (harness adapter framework, plan P2a; merged, #222).** Its BR-10 declares `session-record` in `templates/hooks.yml`, names `partials/session-record.sh` as the entry's `command`, and shipped a stub under that name that this REQ replaces. The rendered `.claude/settings.json` runs it on the `startup|resume|clear` matcher. Its HookEntry carries `timeout_s` (10 s, the bound BR-5 must fit inside) and each adapter carries a `hook_payload` map, which `harness_render.hook_args` spells as `--harness`/`--field` arguments for an adapter that renders its own hook file (BR-6).
- REQ-656 (Copilot + Cursor adapters, in flight), REQ-655 (Codex adapter), REQ-658 (Gemini adapter): gate AC-9's and AC-10's non-Claude halves. Until each lands, that harness's row in AC-9/AC-10 is recorded `n/a` with the reason. The sidecar contract, the discovery chain and the `claude` parser do not depend on them. REQ-656 fills `hook_payload` with `unsupported` until OQ-1 is answered, so its render carries no `--field` for an unverified key.
- REQ-666 (skill-text portability): merged. It no longer gates AC-9.
- REQ-654 (P0): merged. `ADLC_HOME` and the `~/.agents/skills` mount reach the toolkit on the non-Claude harnesses in the dogfood runs. No code dependency.
- None new at runtime: POSIX sh, `python3` stdlib, `grep -wF`, `tail`, `find`, `ls`, `date`.

## Assumptions

- Claude Code's `SessionStart` hook receives JSON on stdin carrying `session_id`, `transcript_path`, `cwd`, `hook_event_name` and `source` (read off a real 2.1.258 payload, 2026-10-30, a logged-out headless run in a throwaway `HOME`). Cursor's session-start hook is expected to carry a `transcript_path` and a conversation id; the field names for the other three are Open Question 1.
- A Cursor transcript is Claude-Code-compatible JSONL, so the `cursor` parser is expected to be the `claude` parser under another flag value; the real fixture decides.
- A harness worktree has its own `.adlc/` checkout, so sidecars are per working tree and a sprint's parallel sessions never share a sidecar directory. A subagent never fires a session-start hook, so a pipeline-runner's worktree has no sidecar of its own and it is found by the walk.
- A transcript records a tool's output before the next tool call runs. Measured on Claude Code by BUG-253; unmeasured on the other harnesses. One that flushes later simply has no holder, and the run refuses into Fallback drafting.
- Sessions on the non-Claude harnesses run on a trusted project path during dogfood, so project-level hooks fire; the plan's §6.8 experiment (hooks in headless mode after per-run trust) belongs to P6, not here.
- The five transcript roots and their shapes are as surveyed on 2026-10-27 (plan §1 Transcripts row; `codex-portability.md` §2f). Codex's rollout schema is explicitly undocumented and has moved between versions (`codex-portability.md` §4 item 3); the fixture pins one version and the provenance note says which.
- Fixtures are captured from the maintainer's own sessions on the `atelier-fashion` test bed, so there is no third-party content to clear beyond redaction.
- id allocated with remote reservation (`degraded=0`); no degraded-allocation note required.

## Open Questions

- [ ] OQ-1: What are the session-id and working-directory field names in the Codex, Copilot CLI and Gemini CLI session-start hook payloads, and which payload or environment field tells the three `.claude/settings.json` readers (Claude Code, Copilot CLI, Cursor) apart? Claude Code's half is answered from a real payload (BR-6); the rest is undocumented and no other CLI is installed here, so the code fails closed: those readers record `harness=unknown`, and a `copilot` or `cursor` table row and the adapter's `hook_payload` map arrive together from a captured payload.
- [x] ~~OQ-2: How does Gemini CLI derive `<project_hash>` under `~/.gemini/tmp/` from the working directory?~~ Moot (2026-10-30): the mark replaced the locator, so rung (b) scans every hash under the bounds and no rule is needed.
- [x] ~~OQ-3: Where does Cursor keep its transcripts when no hook recorded `transcript_path`, and is that root stable enough to walk?~~ Resolved (2026-10-27): sidecar rung only. No stable Cursor root is known, so there is no `walk:cursor` source and no Cursor HarnessRoot; a Cursor session with no usable sidecar reaches rung (b) over the other roots and then the refusal, and AC-9 records Cursor's walk half `n/a` by design.
- [x] ~~OQ-4: Should `install.sh` also install the session-record hook at user level (`~/.claude/settings.json` and each harness's user hook file) so a repo that was never `/init`-ed, or an untrusted path, still gets a sidecar?~~ Resolved (2026-10-27) as proposed: project-level here (the plan §2d puts the hook in project config); user-level installation is deferred to the framework REQ (REQ-657), which owns user-level renders, and is listed under Out of Scope.
- [x] ~~OQ-5: What is the REQ id of the harness adapter framework (plan P2a)?~~ Resolved (2026-10-27, at spec time): REQ-657; External Dependencies, BR-8 and AC-10 bind to its BR-10.
- [ ] OQ-6: Can a Gemini CLI fixture still be captured given the consumer-tier move to Antigravity CLI (plan §6.5), and on which binary? If only Antigravity is available, the fixture is captured there and the `gemini` format name is kept with the provenance note saying so.
- [x] ~~OQ-7: Is the Claude Code `SessionStart` hook's stdout injected as model context even when it is a single blank line?~~ Resolved (2026-10-27): moot — BR-5 requires empty stdout; AC-2 asserts it.
- [x] ~~OQ-8: Which REQ carries the hook command?~~ Resolved (2026-10-27): REQ-657 owns the `templates/hooks.yml` entry and every render; this REQ owns `partials/session-record.sh` (the command the entry's `command` string names), the sidecar field set and format, mode 600, the `started_at`-preserving rewrite, pruning, the `harness` derivation rule, the `/wrapup` consumer and `extract-chat --format`. REQ-657 BR-10 cites this partial and defines none of the file; its stub partial writes `harness=` and `session_id=` only until this REQ replaces it under the same name. The `/init` gitignore line and its lint are this REQ's (BR-7, BR-15).

## Out of Scope

- The harness adapter framework itself, `harness/<name>.yml`, `adlc harness install|render`, the `templates/hooks.yml` entry and the rendering of any hook into `.claude/settings.json` (REQ-657), `.codex/hooks.json` (REQ-655) or `.gemini/settings.json` (REQ-658).
- User-level installation of the session-record hook (`~/.claude/settings.json`, each harness's user hook file) by `install.sh` or `adlc harness install` — the framework REQ owns user-level renders (OQ-4).
- The ETHOS `sessionStart`/`subagentStart` injection hook (plan §2d) — it may share a settings entry with this hook, but its content and its subagent events are the framework's.
- Any change to the lesson template, `adlc_lesson_check`, the capture rules, the `--question` text, `/bugfix` Phase 6, `/review` escalation, or the telemetry schema — REQ-646, REQ-647, REQ-648 and REQ-424 stand.
- Reading transcripts for any purpose other than `/wrapup` Step 4 (no `/spec`, `/proceed` or `/sprint` consumer; REQ-423's "no CLI for find-the-JSONL" stays).
- A `--format auto` sniffer: the sidecar's `harness` or the root a file was found under already names the format.
- Transcript discovery above `$HOME`, across users, or on Windows.
- Per-run trust, headless hook delivery, and the exec engine's use of sidecars — plan P6 and its §6.8 experiment.
- Migrating or relocating any existing `~/.claude/projects/` data.
- Compressed Codex rollout archives (`.jsonl.zst`, `codex-portability.md` §4 item 3): rung (b) reads plain `.jsonl` only; an archived session has no holder, which is a refusal, not a decompression step.

## Deferred

Recorded at Phase 1 (2026-10-30), updated at close-out. REQ-656 landed during this run with every Copilot `hook_payload` field `unsupported`, so its render records `harness=copilot` with a generated id and no path.

- **`codex`, `copilot`, `gemini`, `cursor` parsers, fixtures and AC-8 rows.** `copilot`, `agent`, `codex`, `gemini` and `antigravity` are not on PATH on this machine, so no real transcript can be captured, and a parser written from the survey would be an invented shape. Each flag value refuses. When a harness can be captured, one fixture plus one parser closes its row; discovery already reaches its root.
- **AC-9 and the non-Claude rows of AC-10.** `n/a`: the CLI is not installed, and REQ-655, REQ-656 and REQ-658 have not landed.
- **OQ-1 for Codex, Copilot, Gemini and Cursor.** Their payload field names stay unverified. `harness=unknown`, or `unsupported` in an adapter's `hook_payload`, keeps each fail-closed.
- **Claude Code 2.1.309 (the desktop app's binary).** Its binary here is a Linux VM build, so the fix is measured on the standalone 2.1.258 only. The desktop session that ran this REQ, started from the old render, wrote no sidecar, which is consistent with the same cause and falls through to the walk.
- **Whether the other harnesses write a tool's output before the next call runs.** The walk depends on it. If one does not, that harness refuses into Fallback drafting.
- **AC-3 end to end.** A full `/wrapup` delegating from a sidecar has not run, because this repo's close-outs keep delegation off for transcripts (LESSON-746). Each part is verified alone.
- **Interactive sessions.** Every live run here was headless. Interactive firing, and whether an untrusted interactive path skips hooks, are unobserved.
- **A test that runs the Step 2 flag-file read.** It is held by `skill_wiring`'s text checks only.
- **OQ-6.** Open, unaffected: no Gemini or Antigravity binary here.

## Retrieved Context

- REQ-423 (spec, score 11): /wrapup Step 4: robust JSONL discovery so Kimi doesn't draft a lesson from the wrong session's transcript
- REQ-414 (spec, score 11): Pilot Kimi delegation in /analyze and /wrapup, with hard fallback to Claude when ask-kimi is unavailable
- REQ-646 (spec, score 10): Lesson schema v2: evidence, confidence, kind, enforcement — and reflector-style capture prompts
- LESSON-013 (lesson, score 10): BSD grep \b word-boundary in -E silently fails on macOS — use -wF instead
- REQ-603 (spec, score 9): Single-source the delegation authorization arms — the gate may veto, only Python may authorize
- REQ-610 (spec, score 9): Guard the two-level partial-sourcing pattern so a missing repo-local partial is not fatal under POSIX sh
- BUG-205 (bug, score 9): A legacy MOONSHOT_API_KEY/KIMI_API_KEY in the environment silently overrides an explicit `delegate.enabled: false`
- REQ-522 (spec, score 9): De-brand the delegation surface (no Kimi naming) and make skill telemetry single-fence-safe
- LESSON-313 (lesson, score 9): A global counter's namespace is its bootstrap scan root — seed from the live scan, not the doc's repo count
- REQ-473 (spec, score 9): Global cross-repo LESSON-ID counter (mirror the global REQ/BUG counters)
- REQ-425 (spec, score 9): Pre-merge detection of corrupted shell constructs in SKILL.md files
- REQ-417 (spec, score 9): Wave-2 Kimi skill delegation: /spec Step 1.6 retrieval, /analyze Step 2 audit pre-pass, /review verify
- LESSON-008 (lesson, score 9): When a Claude skill delegates to a cheaper model and feeds the result back to itself, the output is untrusted data
- BUG-209 (bug, score 8): `ADLC_DISABLE_DELEGATE=1` is inert in the delegate CLIs — the documented emergency stop lives only in the vendored shell gate
- BUG-152 (bug, score 8): /wrapup session-JSONL discovery silently delegates the wrong transcript in harness worktrees
