---
id: REQ-660
title: "Session sidecar and multi-harness transcripts for the /wrapup knowledge loop"
status: draft
deployable: false
created: 2026-10-27
updated: 2026-10-27
component: "adlc/wrapup"
domain: "adlc"
stack: ["bash", "python", "markdown", "jsonl"]
concerns: ["reliability", "privacy", "portability", "harness-agnostic", "correctness"]
tags: ["wrapup", "extract-chat", "transcript", "transcripts", "session", "sidecar", "hooks", "hook", "multi-harness", "harness", "codex", "copilot", "gemini", "cursor", "fixtures", "jsonl-discovery", "session-routing", "delegation", "knowledge-capture", "gitignore", "path-encoding", "worktree"]
lane: "full"
lane_reason: "footprint far above max_files (wrapup/SKILL.md, extract-chat, a discovery partial, the session-record partial, gitignore and /init surfaces, five fixtures and their tests) and it ships the command every harness's session-start hook runs"
lane_forced: false
---

## Description

This is Phase 5 of `.adlc/research/multi-harness-plan.md` (revision 2): the
knowledge loop — the part of the toolkit that turns a finished session into a
`LESSON-xxx` — made to work on Copilot CLI, Codex, Gemini CLI and Cursor, not
only on Claude Code.

Today `/wrapup` Step 4 finds the session transcript by walking
`~/.claude/projects/<encoded cwd>/*.jsonl` (REQ-423, repaired for harness
worktrees by BUG-152) and hands it to `extract-chat`, which understands exactly
one record shape: Claude Code's `message.role` / `message.content`. On any other
harness the walk has nothing to find — no transcript of that session lives
under `~/.claude/projects/` — so `$JSONL` is expected to stay empty and Step 4
to fall through to **Fallback drafting** from in-context memory. That is the
plan's accepted degradation for P0–P4, but it is where lesson schema v2's
`evidence` field (REQ-646) gets its transcript quotes, so a port without it is
a worse product (`codex-portability.md` §2f). Each harness keeps its
transcript somewhere different and in an undocumented shape: Codex under
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (`session_meta`, `response_item`,
`event_msg` records, located by `cwd`, not by directory name); Copilot under
`~/.copilot/session-state/<id>/events.jsonl`; Gemini under
`~/.gemini/tmp/<project_hash>/chats/session-*.jsonl`; Cursor writes Claude-Code-
compatible JSONL and hands hooks a `transcript_path`. Reverse-engineering five
directory layouts is the fragile way in. The robust way is to ask the harness at
the moment it knows: every one of the five fires a session-start hook that is
expected to carry a session id and, on Claude Code and Cursor, the transcript
path (Open Question 1 confirms the field names against real payloads).

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
   chain: sidecar → per-harness transcript discovery (the existing Claude walk
   plus new rules for the Codex, Copilot and Gemini roots; Cursor has a sidecar
   rung only, Open Question 3) → Fallback drafting. Every rung keeps the
   REQ-423 / BUG-152 contract: the candidate's
   recent content must mention the active REQ id, a detected miss refuses
   rather than guesses, the walk never leaves `$HOME`, and exactly one stderr
   line says what was chosen and why.
3. **`extract-chat --format claude|codex|copilot|gemini|cursor`.** One parser
   per record shape, all producing today's `## Human` / `## Assistant` text with
   tool calls, tool results, images and base64 stripped, so the delegate's
   `--question` and the capture rules downstream are untouched. Each format is
   proven against one **real** transcript captured from an actual session on
   that harness (plan §6.9 names Codex and Copilot; this REQ extends the rule
   to all five), redacted and trimmed, with a parser test per format.

Nothing about the lesson changes: not the schema (REQ-646), not the capture
rules, not the `adlc-read --question` text, not post-validation. Only where the
evidence comes from.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| SessionSidecar | path | path | `<working tree>/.adlc/.session/<id>`; one file per session; written only when `<working tree>/.adlc/` already exists |
| SessionSidecar | harness | enum | `claude` / `copilot` / `codex` / `gemini` / `cursor` / `unknown`; always present; `unknown` when the entry carries no `--harness` argument and the payload matches no row of the partial's detection table (BR-6) |
| SessionSidecar | session_id | string | the harness's own id when the payload carries one, else an id the hook generates; `^[A-Za-z0-9._-]{1,128}$`, used as the file name |
| SessionSidecar | transcript_path | path or empty | absolute path under `$HOME` when the payload carries one (Claude, Cursor); empty otherwise; never a path outside `$HOME` |
| SessionSidecar | cwd | path | the working tree the hook ran in, as given by the payload or `$PWD` |
| SessionSidecar | started_at | timestamp | UTC, ISO-8601, set at first write; a re-fire for the same id (resume, compaction) rewrites the file and keeps `started_at` |
| SessionSidecar | format | rule | `plain key=value lines`; exact format is an architecture decision, but it is readable with POSIX sh and no JSON parser |
| SessionSidecar | mode | perm | 0600; never a credential |
| DiscoveryResult | source | enum | `sidecar` / `walk:claude` / `walk:codex` / `walk:copilot` / `walk:gemini` / `none`; no `walk:cursor` — Cursor has a sidecar rung only (Open Question 3) |
| DiscoveryResult | transcript | path or empty | the chosen transcript; empty means Fallback drafting |
| DiscoveryResult | format | enum | the `extract-chat --format` value to use, derived from the sidecar's `harness` or from the root the walk found the file under; `unknown` → the root the file was found under |
| DiscoveryResult | reason | string | the single stderr line's reason (`matched REQ-xxx in <basename> via sidecar`, `REQ-xxx not mentioned … REFUSING`, `no candidates`) |
| HarnessRoot | harness | enum | `claude` / `codex` / `copilot` / `gemini` — the four harnesses with a walkable root; Cursor is sidecar-only (Open Question 3) |
| HarnessRoot | root | path | `~/.claude/projects`, `~/.codex/sessions`, `~/.copilot/session-state`, `~/.gemini/tmp`; every root is under `$HOME` and is spelled from `$HOME`, never `$ADLC_HOME` (BR-9) |
| HarnessRoot | locator | rule | a sidecar `session_id` narrows the scan to the entry it names (Copilot `session-state/<id>/`, Codex `rollout-*-<id>.jsonl`, Gemini `session-<id>*`) before the cwd rule applies; how a candidate is tied to the working tree: Claude by encoded directory name; Codex by `cwd` inside `session_meta`; Copilot by cwd inside `events.jsonl` (Assumption) else by scanning every `session-state/<id>/`; Gemini by project hash (Open Question 2) else by scanning every hash; Cursor by `transcript_path` only |
| TranscriptFixture | path | path | `tools/delegate/tests/fixtures/transcripts/<harness>.jsonl` plus `<harness>.expected.txt`; captured from a real session, redacted, trimmed |
| TranscriptFixture | provenance | record | harness name and version, capture date, what was removed; recorded beside the fixture |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| session_recorded | the harness's session-start hook (`SessionStart` on Claude Code, Codex, Gemini and Cursor — Cursor sees the key from the as-is `.claude/settings.json`, as does Copilot's read of that file; `sessionStart` in Copilot's own `.github/hooks/adlc.json`) | the session sidecar written or rewritten; nothing on stdout that the harness would inject as context; exit 0 always |
| sidecar_pruned | every hook run | sidecars older than the retention window removed from the same directory; count reported nowhere (silent) |
| transcript_resolved | `/wrapup` Step 4 step 1 | one stderr line naming source, basename and reason; the chosen path and format persisted to the flag file (`skill-flag.sh mark`) for step 2 |
| discovery_refused | a REQ id was known and no candidate from any rung mentions it | one stderr line; `$JSONL` empty; Fallback drafting |
| chat_extracted | `/wrapup` Step 4 step 2 | `extract-chat --format <format> <transcript> -o <tmpfile>`; same output contract as today |

_Permissions: not applicable — single-user machine tooling that reads the user's own session data under `$HOME`. Section omitted deliberately._

## Business Rules

- [ ] BR-1: **The session sidecar is the first rung, never the only one.** `/wrapup` Step 4 step 1 resolves the transcript in this order and stops at the first rung that yields a candidate mentioning the active REQ id: (a) every `.adlc/.session/*` sidecar in the current working tree (`git rev-parse --show-toplevel`); (b) per-harness transcript discovery over every HarnessRoot that exists on the machine; (c) Fallback drafting. A rung that finds candidates none of which mention the REQ id does not stop the chain — the next rung runs — and only when every rung is exhausted does the refusal fire. With no REQ id to anchor on, the newest sidecar with a usable `transcript_path` (by `started_at`) wins at rung (a) and the existing newest-in-closest-directory rule applies at rung (b), each with its own stderr reason. (informed by REQ-423, BUG-152, LESSON-483)
- [ ] BR-2: **The anchor check is unchanged and applies to every rung.** A candidate is accepted only if the last 200 lines of its transcript contain the active REQ id as a whole word (`grep -qwF`, fixed-string, never `\b` in `grep -E`); among accepted candidates the newest wins (sidecar `started_at` at rung (a); at rung (b), the existing order — closest directory first, newest within it (`wrapup/SKILL.md:289-290`) — extended across harness roots by a rule the architecture fixes; this REQ does not change the Claude walk's tie-break). A sidecar whose `transcript_path` is empty, missing on disk, or outside `$HOME` contributes its `harness` and `session_id` to rung (b)'s locator and nothing else. (informed by REQ-423 BR-2, BR-5; LESSON-013)
- [ ] BR-3: **Refuse, do not guess.** When a REQ id was known and no rung produced a candidate mentioning it, `$JSONL` stays empty, exactly one stderr line says so naming the rungs tried and the candidate counts, and control reaches Fallback drafting. A sidecar's presence never licenses delegating a transcript the anchor check rejected. (informed by BUG-152, LESSON-483)
- [ ] BR-4: **One stderr line per invocation, extended not replaced.** The REQ-423 BR-4 line keeps its prefix `/wrapup: session JSONL —` and gains the source: `matched REQ-xxx in <basename> via sidecar`, `… via walk:<harness>`, `no sidecar and no candidates under any harness root`, or the refusal. Close-out mode (BUG-249) still skips discovery entirely and emits nothing here. (informed by REQ-423 BR-4, LESSON-008 point 5)
- [ ] BR-5: **The hook is inert outside an ADLC working tree and never fails a session.** It writes only when `<cwd>/.adlc/` exists, writes only under `<cwd>/.adlc/.session/` and only mode 600, exits 0 on every path including a malformed or empty payload, prints nothing to stdout (every harness injects session-start stdout as model context), finishes well inside the entry's `timeout_s` (REQ-657), including after Gemini's unit conversion (REQ-658), and needs nothing beyond POSIX sh and `python3` stdlib — no `jq`, no network, no toolkit install. A machine with no toolkit and a repo with the hook entry committed must not break session start.
- [ ] BR-6: **The session sidecar records what the harness gives, no more.** `harness` and `session_id` are always written; `harness` is written by the command from, in order: (1) a `--harness <name>` argument when the rendered entry carries one — whether a render carries it is REQ-657's renderer's decision (spelled from that adapter's `hook_payload`, REQ-657 BR-10), never this REQ's; (2) otherwise, for the `claude` render that Claude Code, Copilot CLI and Cursor all read, a detection table **embedded in the partial** (POSIX sh + `python3` stdlib cannot read `harness/*.yml` at session start) that maps each of the three payloads' distinguishing fields and its `session_id`/`cwd`/`transcript_path` names, captured per OQ-1; the `claude` and `copilot` rows of that table must equal the `hook_payload` map in `harness/claude.yml` and `harness/copilot.yml`, asserted by a test; the `cursor` row lives only in the partial (REQ-656 declares no Cursor `hook_payload`); (3) `harness=unknown` when neither applies, and `/wrapup` treats `unknown` as pathless at rung (a) and scans every root at rung (b). `transcript_path` only when the payload carries one and it resolves under `$HOME`; `cwd` from the payload, else `$PWD`. The hook never derives, guesses or searches for a transcript path — that is `/wrapup`'s job at rung (b). A re-fire for the same session id (Claude `--resume`, `compact`) rewrites the file in place; two sessions in one working tree produce two files. A second fire for the same session from a second hook file (Copilot reads both `.claude/settings.json` and `.github/hooks/adlc.json`, REQ-656 OQ-1) is a rewrite in place when the payload carries an id; when it does not, the second fire produces a second sidecar with a generated id, which rung (a) tolerates (both are pathless and feed the same locator).
- [ ] BR-7: **Gitignored everywhere and pruned by the writer.** `.adlc/.session/` is added to this repo's `.gitignore` and to the gitignore lines `/init` writes for consumer projects; `git status` in a working tree with sidecars present shows nothing. Each hook run deletes sidecars in the same directory older than the retention window (a constant the architecture fixes; 30 days is the proposal) so the directory is bounded without a scheduled job. `/wrapup` never deletes a sidecar. (informed by REQ-654 BR-13 posture — a seam that must not silently close: the gitignore line is checked by the lint in BR-15)
- [ ] BR-8: **One hook command, one entry, rendered by the framework.** The `session-record` entry in `templates/hooks.yml` and its `claude` render into `.claude/settings.json` (read as-is by Copilot CLI and Cursor) are REQ-657 BR-10's; the `.codex/hooks.json` and `.gemini/settings.json` renders are the Codex and Gemini adapters' (REQ-655, REQ-658) and the `.github/hooks/adlc.json` render is the Copilot adapter's (REQ-656 BR-5); this REQ ships `partials/session-record.sh`, the command that entry runs — a partial reached through the REQ-610 two-level sourcing spelling, so a consumer with a vendored copy and a bare machine with only `~/.claude/skills` both resolve it — and the per-harness payload-field mapping the command needs (Open Question 1). The two REQs share exactly one seam: the entry's `command` string, which names this REQ's partial; REQ-657 specifies nothing about the file the command writes. Where a harness loads project config only for trusted paths (Copilot, Codex, Gemini, Cursor — plan §1), an untrusted path simply has no sidecar and `/wrapup` runs rung (b); this REQ does not touch trust. (informed by REQ-610 BR-3)
- [ ] BR-9: **Per-harness discovery is bounded and contained.** Rung (b) scans each HarnessRoot that exists, with the same `$HOME` containment, `..`-rejection and sanitization the Claude walk already applies to every path it touches, and a bound on how much it reads: at most the last 200 lines of any candidate for the anchor check, and for roots organised by date (Codex) at most a fixed recent window of day-directories (the architecture fixes it; 14 days is the proposal). A root that is absent is skipped silently; a root that is present but holds nothing for this working tree contributes zero candidates. Locating a candidate by `cwd` accepts the current working tree or any ancestor up to `$HOME`, the same set the Claude walk enumerates, so a session opened at a parent directory is found on every harness as it is on Claude. Harness roots are the harnesses' own data directories, never toolkit state: `~/.claude/projects` is spelled from `$HOME`, not `$ADLC_HOME`, and is registered as a documented exception to the REQ-654 BR-13 lint (or kept in the SKILL.md fence, which that lint does not scan). (informed by REQ-423 BR-1, BR-6, BR-7)
- [ ] BR-10: **`extract-chat --format` is explicit, defaults to today's behaviour, and emits today's shape.** `--format` accepts exactly `claude`, `codex`, `copilot`, `gemini`, `cursor`; omitted means `claude`, so every existing caller and test is unchanged byte-for-byte. Every parser yields the same `## Human` / `## Assistant` sections, drops tool calls, tool results, system and harness-internal records, images, data URIs and raw base64 under the existing `_RAW_BASE64_MIN_LEN` rule, skips malformed lines, and exits non-zero only for an unreadable input, an unwritable `-o` target, or an unknown format. `cursor` may share the `claude` parser if the fixture proves the shapes identical, but the flag value exists regardless so `/wrapup` can pass the sidecar's `harness` through unchanged. (informed by REQ-414 BR-2 — same artifact shape on every path)
- [ ] BR-11: **One real fixture per harness, captured, redacted and trimmed.** For each of the five formats the repo carries a transcript captured from an actual session on that harness (not synthesised, not hand-written — plan §6.9's rule for Codex and Copilot, applied to all five), trimmed to a small number of turns that still exercise a tool call, a tool result and a plain reply, redacted with the REQ-415 five-pattern credential chain and with every home-directory path rewritten to `~/`, and accompanied by its expected `extract-chat` output and a provenance note (harness, version, capture date, what was cut). A fixture is replaced, never edited by hand, when a harness's schema changes. (informed by REQ-646 BR-12, BR-13; LESSON-008 point 4)
- [ ] BR-12: **A parser test per format, plus the discovery matrix.** `tools/delegate/tests/test_extract_chat.py` gains, per format, a golden test (fixture in → expected text out, byte-equal) and a negative test (no `tool_use`/`tool_result`/harness-internal content survives). `partials/tests/run.sh` gains a discovery case that sources `partials/session-discovery.sh` (BR-14) and reproduces the BUG-152 behaviour matrix (prose in the bug record today; this REQ commits it as a test) with sidecars added: sidecar-with-path wins when it matches; sidecar-with-path that does not match falls to the walk; sidecar-without-path drives the locator; stale sidecar for an older session on the same REQ loses to the newer; no match anywhere refuses. Both suites run under bash 3.2, zsh and `/bin/sh` as today. (informed by BUG-152 verification, REQ-610 BR-11)
- [ ] BR-13: **Nothing about the lesson changes.** `templates/lesson-template.md`, `partials/lesson-check.sh`, the `<!-- lesson-capture-rules -->` block, the delegated `--question` text, post-validation, the summary slot and telemetry schema (`mode` vocabulary, `ghost-skip` rewrite) are not modified. The only `/wrapup` edits are in Step 4 step 1 (discovery) and the `extract-chat` invocation in step 2, which gains `--format`. Prose-only renames of the existing 'sidecar' wording for the flag file (SKILL.md ~166, 188, 318, 329, 450) to 'flag file' are permitted; no fence code changes (318 and 329 are comment lines inside a fence — a comment edit is prose, not code). The `invoked`/`exit` marks and the telemetry resolver are untouched, so a sidecar-resolved transcript records `mode=delegated` exactly as a walk-resolved one does today. Step 2 reads the format from the flag file and an absent `format` key means `claude`, so the close-out block (BUG-249), which marks `jsonl` empty and never writes `format`, needs no edit. (informed by REQ-646 BR-2, BR-4; REQ-522 BR-4, BR-6; REQ-424)
- [ ] BR-14: **Fence discipline holds.** Whatever lands in `wrapup/SKILL.md` keeps every fenced block self-contained: the chosen path and format cross to step 2 only through the flag file (`skill-flag.sh mark`/`read`), never a shell variable; a shared function is re-sourced in the block that calls it; no `\b` in `grep -E`, no `[[`, no `local`, no bare `$<digit>`, no `[0]` indexing; `tools/lint-skills` stays clean. Discovery moves into `partials/session-discovery.sh` (decided: BR-12 needs a sourceable unit — `partials/tests/` has no fence-extraction mechanism, so a walk that lives only in the fence cannot be tested from `run.sh`); the Step 4 step 1 fence sources it through the REQ-610 two-level spelling and persists its result through the flag file. It ships through the existing `/init` vendoring and `/template-drift` surfaces and consumers see `stale` until re-synced, as REQ-646 BR-9 and REQ-654 BR-3 accept. (informed by REQ-522 BR-4, BR-5; REQ-610; LESSON-582; LESSON-013)
- [ ] BR-15: **Documentation and lint move with the change.** `README.md` and `tools/delegate/README.md` document `--format` and the sidecar; `.adlc/context/architecture.md`'s knowledge-retrieval paragraph names the three-rung chain; `CHANGELOG.md` names the consumer re-sync (settings.json hook entry, gitignore line, vendored partial) as the follow-up. `tools/lint-skills` gains a check that `.adlc/.session/` is present in the gitignore lines `/init` writes, so the sidecar cannot start leaking into consumer commits through a later edit. (informed by LESSON-012, LESSON-019)
- [ ] BR-16: **Privacy posture.** A session sidecar holds a home-directory path; it is written mode 600 and stays on the machine (gitignored, never read by anything but `/wrapup`, never copied into a lesson — REQ-646 BR-12 already rejects home paths in `evidence`). The transcript still passes through the existing `mktemp` + redaction step before `adlc-read` sees it, on every format. Discovery reads only under `$HOME` and only the four named roots. (informed by LESSON-008 points 3–4, REQ-423 BR-6)

## Acceptance Criteria

- [ ] AC-1: In a Claude Code session opened inside a harness worktree with `.adlc/` present, a sidecar appears at `<worktree>/.adlc/.session/<session_id>` within the first turn, naming `harness=claude`, the session id, a `transcript_path` under `~/.claude/projects/` that exists, and the worktree as `cwd`; `git status` shows nothing new; `claude --resume` of the same session rewrites the file with the same `started_at`. (BR-5, BR-6, BR-7)
- [ ] AC-2: In a directory with no `.adlc/`, the same hook run writes nothing anywhere and exits 0; fed an empty stdin, a non-JSON stdin and a payload with no id field, it exits 0 each time, prints nothing to stdout, and writes at most a sidecar with a generated id; its wall time on the test machine is inside the entry's `timeout_s` (REQ-657), including after Gemini's unit conversion (REQ-658). (BR-5)
- [ ] AC-3: `/wrapup REQ-xxx` in that worktree emits exactly one `/wrapup: session JSONL —` line ending `via sidecar`, naming the transcript's basename, and the delegated path runs against that file; the telemetry record shows `mode=delegated`. (BR-1, BR-4, BR-13)
- [ ] AC-4: With the sidecar's `transcript_path` pointing at a transcript that does **not** mention `REQ-xxx`, while the Claude walk holds one that does, the line reads `via walk:claude` and that transcript is used; with no candidate anywhere mentioning `REQ-xxx`, the line is the refusal, `$JSONL` is empty, Fallback drafting runs and the telemetry resolver records what it records today for a no-transcript run. (BR-1, BR-2, BR-3)
- [ ] AC-5: On the BUG-152 offline fixture extended with sidecars, run under bash 3.2, zsh and `/bin/sh` via `sh partials/tests/run.sh`, every row of the BR-12 matrix produces the stated outcome and the stated stderr reason, and the suite exits 0. (BR-12, BR-14)
- [ ] AC-6: A sidecar whose `transcript_path` is `/etc/passwd`, contains `..`, or is deleted after the hook ran is treated as pathless: rung (b) runs, nothing outside `$HOME` is opened (the test runs with `HOME` set to a sandbox directory, places the rejected targets outside it, and asserts `$JSONL` is empty or names a path under `$HOME`), and the stderr line does not name the rejected path. (BR-2, BR-9, BR-16)
- [ ] AC-7: `tools/delegate/tests/fixtures/transcripts/claude.jsonl` and `claude.expected.txt` are committed **before** the parser is touched, `claude.expected.txt` being the output of the pre-change `extract-chat` (`git show <merge-base>:tools/delegate/extract-chat`) on that fixture; after the change, `extract-chat claude.jsonl` with no `--format` equals it byte-for-byte, and `pytest tools/delegate/tests` passes with every pre-existing test unchanged. `extract-chat --format bogus` exits non-zero naming the accepted values. (BR-10)
- [ ] AC-8: For each of `claude`, `codex`, `copilot`, `gemini`, `cursor`: `extract-chat --format <h> tools/delegate/tests/fixtures/transcripts/<h>.jsonl` equals `<h>.expected.txt` byte-for-byte; the output contains at least one `## Human` and one `## Assistant` section; and `grep -c` for the fixture's tool-call and tool-result markers in the output is 0. The fixture's provenance note names a harness version and a capture date, and `grep -E` for the five credential patterns and for `/Users/|/home/` over the fixture finds nothing. (BR-10, BR-11, BR-12)
- [ ] AC-9: On the atelier-fashion test bed, a Codex session and a Copilot session each run `/spec` → `/proceed` (lite) → `/wrapup`, and `/wrapup`'s stderr line ends `via sidecar` on each; with the sidecar directory emptied first, the line ends `via walk:codex` / `via walk:copilot` and names a transcript under that harness's root. Cursor and Gemini repeat the sidecar half; Cursor's walk half is `n/a` by design (sidecar rung only, Open Question 3) and Gemini's is gated on Open Question 2 and recorded as `n/a` with the reason when it cannot run. A harness whose adapter (REQ-655, REQ-656, REQ-658) has not landed is recorded `n/a` with that reason (External Dependencies). (BR-1, BR-8, BR-9)
- [ ] AC-10: With REQ-657's `claude` render in place, the as-is `.claude/settings.json` for Claude Code, Copilot and Cursor and — once the Codex, Gemini and Copilot adapters (REQ-655, REQ-658, REQ-656 BR-5) have landed — the rendered `.codex/hooks.json`, `.gemini/settings.json` and `.github/hooks/adlc.json` each fire the command on session start on a trusted path and produce a sidecar with the right `harness` value (never `unknown` for a harness whose `hook_payload` map is in place); a harness whose adapter has not landed is recorded `n/a` with the reason; on an untrusted path no sidecar appears and `/wrapup` reports a rung-(b) or refusal line, never an error. Run from a consumer with no vendored partial, the command still resolves through `~/.claude/skills/partials/`. (BR-5, BR-8)
- [ ] AC-11: `git diff` of this REQ touches none of `templates/lesson-template.md`, `partials/lesson-check.sh`, the lesson-capture-rules block, the `adlc-read --question` text in `wrapup/SKILL.md`, or `tools/delegate/emit-telemetry.sh`; `tools/lint-skills/check.sh` is clean, including the lockstep check between `/wrapup` and `/bugfix` capture blocks. (BR-13, BR-14)
- [ ] AC-12: `.gitignore` here and the gitignore content `/init` writes both contain `.adlc/.session/`; deleting the line from the `/init` source makes the new lint check fail naming the file; a consumer re-running `/init` gains the line; README, delegate README, architecture and CHANGELOG carry the new surfaces. (BR-7, BR-15)
- [ ] AC-13: A sidecar older than the retention window is removed by the next hook run in that working tree, a newer one is kept, and `/wrapup` run against an empty `.adlc/.session/` behaves as a rung-(b)-only run: `via walk:<harness>` when a root holds a matching transcript, otherwise AC-4's refusal. (BR-7)

## External Dependencies

- **REQ-657 (harness adapter framework, plan P2a; fixed 2026-10-27, now cites this partial).** Its BR-10 declares `session-record` in `templates/hooks.yml`, names this REQ's `partials/session-record.sh` as the entry's `command`, defines nothing about the file the command writes, and stands in a stub partial under the same name (writing `harness=` and `session_id=` only) until this REQ lands; its AC-8 exercises the `claude` render. Its HookEntry carries `timeout_s` (the bound BR-5 must fit inside) and each adapter carries a `hook_payload` map of per-harness payload field names for the session id, cwd and transcript path, which BR-6 consumes. Until it ships, no harness fires the hook from rendered config, so AC-1, AC-3, AC-9's sidecar half and AC-10 can be exercised only with the hook entry added to `.claude/settings.json` by hand (Claude, Copilot, Cursor); the discovery rung, the parsers, the fixtures and the refusal paths have no dependency and are verifiable alone.
- REQ-656 (Copilot + Cursor adapters), REQ-655 (Codex adapter), REQ-658 (Gemini adapter): gate AC-9's and AC-10's non-Claude halves. Until each lands, that harness's row in AC-9/AC-10 is recorded `n/a` with the reason, the way AC-9 already handles OQ-2/OQ-3. The sidecar contract, the discovery chain, the parsers and the fixtures do not depend on them.
- REQ-666 (skill-text portability): gates AC-9's non-Claude runs; until it lands those rows are `n/a` with that reason.
- REQ-654 (P0): `ADLC_HOME` and the `~/.agents/skills` mount, for the toolkit to be reachable on the non-Claude harnesses in the dogfood runs. No code dependency.
- None new at runtime: POSIX sh, `python3` stdlib, `grep -wF`, `tail`, `find`, `ls`, `date`.

## Assumptions

- Claude Code's `SessionStart` hook receives JSON on stdin carrying `session_id`, `transcript_path`, `cwd`, `hook_event_name` and `source`, and re-fires on resume and compaction with the same `session_id`. Cursor's session-start hook carries a `transcript_path` and a conversation id. These are the two harnesses the plan names as giving the path; the field names for the other three are Open Question 1.
- A Cursor transcript is Claude-Code-compatible JSONL, so the `cursor` parser is expected to be the `claude` parser under another flag value; the real fixture decides.
- Copilot's `events.jsonl` carries the working directory in its first records; if not, rung (b) scans every `session-state/<id>/` and lets the anchor check decide.
- A harness worktree has its own `.adlc/` checkout, so sidecars are per working tree and a sprint's parallel sessions never share a sidecar directory (the BUG-152 shape, now a feature).
- Sessions on the non-Claude harnesses run on a trusted project path during dogfood, so project-level hooks fire; the plan's §6.8 experiment (hooks in headless mode after per-run trust) belongs to P6, not here.
- The five transcript roots and their shapes are as surveyed on 2026-10-27 (plan §1 Transcripts row; `codex-portability.md` §2f). Codex's rollout schema is explicitly undocumented and has moved between versions (`codex-portability.md` §4 item 3); the fixture pins one version and the provenance note says which.
- Fixtures are captured from the maintainer's own sessions on the atelier-fashion test bed, so there is no third-party content to clear beyond redaction.
- id allocated with remote reservation (`degraded=0`); no degraded-allocation note required.

## Open Questions

- [ ] OQ-1: What are the session-id and working-directory field names in the Codex, Copilot CLI and Gemini CLI session-start hook payloads, and which payload or environment field tells the three `.claude/settings.json` readers (Claude Code, Copilot CLI, Cursor) apart? They are undocumented; the hook can only record what a real payload carries, so the mapping is read off a captured payload per harness during architecture, lands in the partial's table and, for claude and copilot, in the adapter's `hook_payload` map (REQ-657), kept equal by test, and a harness that gives no id gets a hook-generated one (BR-6); a payload no rule recognises records `harness=unknown`.
- [ ] OQ-2: How does Gemini CLI derive `<project_hash>` under `~/.gemini/tmp/` from the working directory? With the rule, rung (b) looks in one directory; without it, rung (b) scans every hash's `chats/` and lets the anchor check decide, which is correct but slower.
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
- Compressed Codex rollout archives (`.jsonl.zst`, `codex-portability.md` §4 item 3): rung (b) reads plain `.jsonl` only; an archived session is a refusal, not a decompression step.

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
