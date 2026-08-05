---
id: BUG-152
title: "/wrapup session-JSONL discovery silently delegates the wrong transcript in harness worktrees"
status: open
severity: high
created: 2026-08-05
updated: 2026-08-05
component: "wrapup/discovery"
domain: "adlc"
stack: ["sh"]
concerns: ["correctness", "knowledge-quality"]
tags: ["wrapup", "delegation", "worktree", "path-encoding", "claude-projects", "silent-failure"]
---

## Description

`/wrapup` Step 4 ("Delegated drafting") locates the Claude Code session transcript by
encoding the working directory into a `~/.claude/projects/` directory name. The encoder
only replaced `/`. Claude Code also replaces `.`, so any session running inside a Claude
Code **harness worktree** (`<repo>/.claude/worktrees/<slug>`) computed a directory name
that does not exist.

The walk then climbed to the repo-root-encoded directory, which holds *older, unrelated*
sessions, and the Phase-2 "newest in the closest candidate directory" fallback served one
of those. The delegate received a transcript of different work and drafted a confident,
well-formed lesson about a feature that was never worked on.

The only signal was a soft stderr line: `not mentioned in any candidate; using newest ...
as fallback`. Nothing failed, nothing exited non-zero.

Observed 2026-08-05 during a `/wrapup` for BUG-154 in `teton-code`: discovery selected a
transcript from Aug 1 with **zero** mentions of the feature being wrapped up.

## Reproduction Steps

Deterministic and offline — no real `~/.claude/projects/` needed:

```sh
enc() { printf '%s' "$1" | sed 's|[^A-Za-z0-9]|-|g'; }   # what Claude Code actually does
FH=/private/tmp/bug152; WT="$FH/gh/demo-repo/.claude/worktrees/some-slug-abc123"
RT="$FH/gh/demo-repo"; P="$FH/.claude/projects"
rm -rf "$FH"; mkdir -p "$WT" "$P/$(enc "$WT")" "$P/$(enc "$RT")"; git -C "$WT" init -q
printf '{"t":"REQ-700"}\n' > "$P/$(enc "$WT")/wt-session.jsonl"     # the real session
printf '{"t":"REQ-100"}\n' > "$P/$(enc "$RT")/old-session.jsonl"    # older, unrelated
touch -t 203001010000 "$P/$(enc "$RT")/old-session.jsonl"           # and NEWER by mtime

# Run Step 4's discovery block with REQ_ID=REQ-700 from inside $WT.
```

Note `/tmp` is a symlink to `/private/tmp` on macOS — use the physical path or the
`$HOME`-prefix guard rejects the fixture before discovery starts.

## Expected Behavior

Discovery selects `wt-session.jsonl` — the worktree's own transcript, the only one
mentioning `REQ-700`. When *no* candidate mentions the anchor id, `/wrapup` declines to
delegate rather than picking an arbitrary transcript.

## Actual Behavior

The worktree-level directory never matched, so the only candidate was the repo-root
directory. `REQ-700` appears nowhere in it, so Phase 2 fell through to "newest" and
selected `old-session.jsonl` — unrelated work — and delegated it.

Encoder output for the worktree path:

```
computed: -private-tmp-bug152-gh-demo-repo-.claude-worktrees-some-slug-abc123   (MISS)
real:     -private-tmp-bug152-gh-demo-repo--claude-worktrees-some-slug-abc123
```

Note `-.claude` vs `--claude`.

## Environment

- Platform: all; triggers whenever a session runs inside `.claude/worktrees/<slug>`,
  which is the normal state for any Claude Code harness worktree session
- Version: `wrapup/SKILL.md` @ `main` (REQ-423 discovery, unchanged since)

## Root Cause

Three defects, compounding.

**1. The path encoder is incomplete** (`wrapup/SKILL.md`, Step 4 step 1):

```sh
ENCODED=$(printf '%s' "$DIR" | sed 's|^/||; s|/|-|g')
BASENAME="-$ENCODED"
```

Claude Code encodes a path by replacing **every non-alphanumeric character** with `-`.
This replaced only `/`, so `.claude` became `-.claude` where the real name is `--claude`.

The leading-`/` strip plus manual `-` prefix is the same mistake seen from the other side:
the leading `-` is not a prefix, it *is* the path's leading `/` run through the same
substitution. Stripping it first and re-adding one `-` happens to produce the right answer
only for paths whose components contain no `.`.

**2. `ROOT` was de-worktree'd toward the wrong end.** The walk started at:

```sh
ROOT=$(git rev-parse --show-toplevel 2>/dev/null | sed 's|/\.worktrees/.*$||')
```

That `sed` strips the `/proceed` pattern `/.worktrees/` but not the harness pattern
`/.claude/worktrees/` — dead code for the case that matters. Worse, the *intent* is
backwards: a harness worktree has its **own** project directory holding the only transcript
of the session, so climbing to the repo root skips the correct answer. The upward walk
reaches the repo root anyway, so starting deeper costs nothing.

**3. The Phase-2 fallback guessed instead of refusing.** With a REQ id in hand and no
candidate matching it, every remaining candidate is by definition a transcript of different
work. "Newest wins" turned a *detected* miss into a silent wrong answer. A well-formed
lesson synthesized from an unrelated transcript is worse than no lesson: it is confidently
wrong, it is committed to `.adlc/knowledge/`, and nothing downstream marks it suspect.

## Fix Approach

1. Encode with the real rule — every non-alphanumeric character to `-`, no leading-slash
   strip, no manual prefix.
2. Start the walk at the current working tree; delete the de-worktree `sed`.
3. Refuse when a REQ id was available and no candidate mentions it — leave `$JSONL` empty
   so control falls through to Fallback drafting.
4. Verify against a real `~/.claude/projects/` listing, not by reasoning about the encoder.

## Resolution

**1. Correct, fork-free encoder.**

```sh
adlc_encode_project_dir() { printf '%s' "${1//[!A-Za-z0-9]/-}"; }
```

Parameter expansion rather than `sed` is load-bearing, not stylistic — see Verification.
`[!...]` (not `[^...]`) is the portable negated-class form; output verified byte-identical
to the `sed` equivalent in both bash and zsh.

**2. Lookup is exact-match first, normalized scan second.** The fast path stats
`$PROJECTS_DIR/$WANT` directly and hits for every directory Claude Code has actually
created. Only on a miss does the slow path re-scan the real listing, comparing both sides
through the *same* encoder — so a character Claude Code encodes differently than predicted
(`_`, say) still matches without anyone re-deriving the encoder table. Only entries
normalizing to `$WANT` are accepted, so the scan cannot widen the walk past the ancestor
under consideration. The BR-6 `$HOME` containment guard and BR-7 sanitization are unchanged.

**3. `ROOT` starts at the working tree**, with `|| ROOT="$PWD"` for non-git directories.

**4. Phase 2 refuses.** When `$REQ_ID` is set and nothing matches, the stderr line is now
`REFUSING to delegate a non-matching transcript — drafting directly instead` and `$JSONL`
stays empty. "Newest wins" survives only when there is no anchor id to check against.
Step 2's existing `[ -n "$JSONL" ]` guard carries it into Fallback drafting.

**5. Telemetry consistency.** Step 4's MANDATORY paragraph claimed the *only* acceptable
non-delegated outcome on a gate pass was `api-error`. There are now two: `api-error`, and
discovery legitimately resolving no transcript. The latter never reaches the call site, so
`invoked` is never marked and `_adlc_emit_step_telemetry` records `fallback`/`gate=fail` —
which the `ghost-skip` rewrite in `tools/delegate/emit-telemetry.sh:45` does not touch,
since that keys on `gate=pass`. Documented so a future reader does not "fix" a refusal
back into a guess to satisfy the compliance rule.

### Verification

Reproduced first — the old encoder misses the worktree directory, and discovery selects the
unrelated `old-session.jsonl` even though it is not the newest by walk order.

Behaviour matrix on the fixture above, run in **both** bash and zsh:

| anchor | in worktree transcript | in root transcript | in neither | no id |
|---|---|---|---|---|
| before | root's stale file | root transcript | silent wrong file | worktree |
| after | worktree transcript | root transcript | **REFUSED** | worktree |

Also verified: non-git cwd falls back to `$PWD`; the slow path finds a directory whose real
name preserves `_` where the encoder predicts `-`; and against the live
`~/.claude/projects/` listing, the current session's worktree transcript is selected and
sorts first in walk order.

**Two defects were caught by this pass and fixed before shipping**, both mine, neither
visible by reading:

- *Performance regression.* The first draft normalized **every** listing entry with a
  `sed` fork at **every** ancestor level. Measured **15.2s** on a deep path with 500
  project directories (~4500 forks). The exact-match fast path plus parameter-expansion
  encoding brings it to ~1.9s wall, nearly all of which is shell startup.
- *Fast path skipped the loop entirely.* `while IFS= read -r` returns false on a final
  line with no terminator, so the newline-less single-entry `$MATCHES` never entered the
  loop and **every** scenario refused. Fixed with `printf '%s\n'`; the extra blank line on
  the slow path is dropped by the existing `-n` guard. Caught only by re-running the full
  matrix after the performance fix — the change looked obviously correct.

`tools/lint-skills/check.py` clean (the `arg-templating` rule flags a bare dollar-digit,
which the braced `${1}` and a reworded comment avoid), 465 Python tests pass,
`sh partials/tests/run.sh` green.

### Scope

`/wrapup` Step 4 is the only site in the toolkit that encodes a `~/.claude/projects/`
path. `/bugfix` drafts lessons from in-context memory and performs no transcript discovery;
no partial does path encoding. Nothing to fix in parallel.

## Files Changed

- `wrapup/SKILL.md` — encoder, walk origin, exact-match/normalized-scan lookup, Phase-2
  refusal, and the surrounding prose + MANDATORY-paragraph correction
- `.adlc/bugs/BUG-152-wrapup-jsonl-worktree-path-encoding.md` — this report
