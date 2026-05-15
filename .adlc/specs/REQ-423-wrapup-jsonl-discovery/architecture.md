---
req: REQ-423
status: draft
created: 2026-05-15
updated: 2026-05-15
---

## Approach

Replace the single-path `ls -t ~/.claude/projects/-<encoded>/*.jsonl | head -1` heuristic in
`wrapup/SKILL.md` Step 4 with a **content-anchored walk-up discovery loop** that:

1. Computes the repo-root-encoded path (today's behavior).
2. Walks upward one directory at a time, encoding each ancestor down to (but not above) `$HOME`.
3. For each encoded path, collects candidate JSONLs that pass a path-sanitization regex.
4. Among candidates, grep the **last 200 lines** of each for a word-boundary `\bREQ-XXX\b` match.
5. Pick the newest id-matching JSONL. If none match, pick the newest overall (with a stderr warning).
6. If no candidates exist at all, emit a "no candidates" stderr line and fall through to direct drafting.

This is a pure-markdown change: no new files, no tooling, no shell deps beyond what `/wrapup` already
invokes (`tail`, `grep`, `find`, `ls`, `sed`). The change is contained entirely within the existing
"Delegated drafting → step 1" block (lines ~125-131 of `wrapup/SKILL.md`).

## Why content-anchored over directory-anchored

The prior heuristic (REQ-417) assumed `git rev-parse --show-toplevel` uniquely identifies the
*session's* encoded path. That assumption fails when Claude Code is opened at a parent directory and
later navigates into a nested repo — the active session's JSONL lives under the parent's encoded
path, but `git rev-parse` resolves to the inner repo. The fix can't be "use cwd at session start"
(we don't know it from inside a turn), so we anchor on **content** instead: any candidate JSONL whose
last 200 lines mention the active REQ id is, by construction, the right transcript.

## ADRs

### ADR-1: Word-boundary fixed-string grep (`-wF`), NOT `-E \b…\b`

**Decision**: use `grep -qwF "$REQ_ID"` (fixed-string + word-regexp) when matching the active
REQ id. Do NOT use `grep -qE "\b$REQ_ID\b"`.

**Why**: resolves OQ-3 from the requirement. Fixed-string `REQ-422` matches inside `REQ-4220`,
`REQ-42200`, etc., producing false positives — so a word-boundary form is required. Two forms
were initially considered:

- `grep -qE "\b$REQ_ID\b"` — **rejected**. The `\b` word-boundary assertion is not reliably
  supported by macOS BSD grep in `-E` mode; on the dominant deployment platform it may match
  nothing, silently defeating the entire content-anchored discovery (caught in Phase 5 review).
- `grep -qwF "$REQ_ID"` — **adopted**. `-w` is portable across BSD grep (macOS `/usr/bin/grep`)
  and GNU grep. `-F` treats `$REQ_ID` as a literal fixed string, which both eliminates the
  portability risk AND defends against regex injection if `$REQ_ID` ever contains regex
  metacharacters from a future caller that lacks input validation.

**Supersedes**: BR-5 in the requirement (which spells out the fixed-string form without `-w`).
The task implementation uses `-qwF` — fixed-string AND word-boundary, neither alone.

### ADR-2: Termination at `$HOME`, not at filesystem root

**Decision**: the upward walk stops when the encoded path would represent `$HOME` itself, and
never goes above. Above-`$HOME` encoded paths (`-Users`, `-`) are not enumerated even if they
exist on disk.

**Why**: BR-6 — defends against accidentally scanning other users' or system session data.
The loop's stop condition is structural ("while current directory != $HOME, step up"), not a
denylist of specific paths. Easier to audit.

### ADR-3: Path sanitization applied per-candidate, not per-encoded-path

**Decision**: the BR-7 regex (`^-[A-Za-z0-9_./-]+$`) is checked against each computed
encoded-path basename before that path is passed to `ls`. Encoded paths that fail the regex
are silently dropped (no error emitted — they'd only fail if the directory tree contained
unusual characters, which is a non-attack signal).

**Why**: per-candidate is the narrowest sanitization point. Sanitizing the input to the encoding
(the cwd itself) would conflate "username contains a dash" with "attacker-supplied input"; the
encoded basename is the actual string that gets passed to a shell glob, so that's where the check
belongs.

### ADR-4: Single stderr line per `/wrapup` invocation

**Decision**: discovery emits exactly one line, even when walking through many encoded paths.
The line names the **chosen** JSONL basename and the reason (matched / fallback / none). Per-path
debug output is not emitted to stderr.

**Why**: BR-4 — keeps the wrapup log scannable. Per-path debug would multiply the log lines by
the directory depth, drowning the actual telemetry signal in unactionable detail. If a future
debug session needs per-path visibility, that's an `ADLC_DEBUG=1` knob, not the default.

## Discovery algorithm (reference shell)

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null | sed 's|/\.worktrees/.*$||')
REQ_ID="${1:-}"   # active REQ id passed to /wrapup, may be empty

# Build candidate list: walk from ROOT up to (and including) $HOME
CANDIDATES=()
DIR="$ROOT"
while [ -n "$DIR" ] && [ "$DIR" != "/" ]; do
    ENCODED=$(printf '%s' "$DIR" | sed 's|^/||; s|/|-|g')
    ENC_DIR="$HOME/.claude/projects/-$ENCODED"
    # BR-7 sanitization on the basename we're about to pass to ls
    BASENAME="-$ENCODED"
    if printf '%s' "$BASENAME" | grep -qE '^-[A-Za-z0-9_./-]+$' && [ -d "$ENC_DIR" ]; then
        while IFS= read -r f; do
            [ -n "$f" ] && CANDIDATES+=("$f")
        done < <(ls -t "$ENC_DIR"/*.jsonl 2>/dev/null)
    fi
    # Stop after processing $HOME
    [ "$DIR" = "$HOME" ] && break
    DIR=$(dirname "$DIR")
done

JSONL=""
REASON=""
if [ ${#CANDIDATES[@]} -eq 0 ]; then
    echo "/wrapup: session JSONL — no candidates found; skipping Kimi delegation" >&2
    # fall through to Fallback drafting
else
    # Phase 1: id-match among candidates (word boundary, last 200 lines)
    if [ -n "$REQ_ID" ]; then
        for c in "${CANDIDATES[@]}"; do
            if tail -n 200 "$c" 2>/dev/null | grep -qE "\b$REQ_ID\b"; then
                JSONL="$c"
                REASON="matched $REQ_ID in $(basename "$c")"
                break   # CANDIDATES is mtime-sorted within each dir; first match wins
            fi
        done
    fi
    # Phase 2: fallback to newest overall if no id-match
    if [ -z "$JSONL" ]; then
        JSONL="${CANDIDATES[0]}"   # ls -t already sorted newest first per-dir; first overall is newest of newest
        if [ -n "$REQ_ID" ]; then
            REASON="$REQ_ID not mentioned in any candidate; using newest $(basename "$JSONL") as fallback"
        else
            REASON="no REQ id provided; using newest $(basename "$JSONL")"
        fi
    fi
    echo "/wrapup: session JSONL — $REASON" >&2
fi
```

**Note on mtime ordering across multiple encoded dirs**: `ls -t` sorts within a single
directory. When candidates come from multiple ancestor dirs, the simple concatenation above is
*close-enough* to newest-first (each dir's candidates are interleaved in walk-up order, not by
true global mtime). For the id-match phase this is fine — the first match found is the newest
match within its directory, and the directory closest to the repo root is checked first, which
matches user intent. For the no-id-match fallback, if global-newest correctness matters more,
swap line `JSONL="${CANDIDATES[0]}"` for `JSONL=$(printf '%s\n' "${CANDIDATES[@]}" | xargs ls -t 2>/dev/null | head -1)`. Task spec uses the simpler form first; tighten only if verify
catches a real failure.

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| `tail -n 200` misses a REQ mentioned in older turns | Acceptable per requirement assumption — `/wrapup REQ-xxx` invocation guarantees a recent turn with the id. |
| Bash array syntax not portable to `/bin/sh` | The existing `wrapup/SKILL.md` block uses bash idioms already (`<()`). No regression. |
| Multiple ancestor dirs all contain id-matching JSONLs (e.g., user wrapped same REQ twice) | Walk order is repo-root first, so the most-specific dir wins. This matches "the user is in the repo now" intent. |
| `git rev-parse` fails (not a git repo) | Existing code already handles via `2>/dev/null`; `ROOT` becomes empty and the loop body skips. Add an explicit `[ -z "$ROOT" ]` short-circuit to the "no candidates" branch for clarity. |

## Files affected

| File | Repo | Change |
|------|------|--------|
| `wrapup/SKILL.md` | adlc-toolkit | Replace lines ~125-131 (single-path discovery) with the discovery algorithm above. Update BR-4 log lines to match. |
| `.adlc/specs/REQ-423-wrapup-jsonl-discovery/architecture.md` | adlc-toolkit | This file. |
| `.adlc/specs/REQ-423-wrapup-jsonl-discovery/tasks/TASK-034-*.md` | adlc-toolkit | One task (see below). |

No other SKILL.md is touched. No Python tooling is touched (REQ-413's pytest suite of 36 tests
remains green by structural exclusion).

## Lessons applied

- **LESSON-008** (skill delegation = untrusted data + sanitize citations) → ADR-3 (per-candidate
  sanitization regex).
- **LESSON-010** (delegated-model silent truncation + advisory anchoring) → ADR-4 (single
  stderr line; the failure mode being addressed is also silent — wrong JSONL with no signal).
- **LESSON-011** (rc-fallback / self-healing) → BR-9 / requirement (graceful degrade to direct
  drafting when no candidates).
- **LESSON-009** (hotfix verify finds what original verify missed) → background: this REQ
  exists because REQ-417's verify didn't anticipate the parent-dir case. Verify checklist for
  this task includes the parent-dir scenario explicitly.
