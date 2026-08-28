# Adversary Report — REQ-593

Target: `.adlc/specs/REQ-593-incident-to-req-backlink/requirement.md` (spec)
Date: 2026-08-27
Venue: single-context (agents not dispatched — see Coverage)
Verdict: **found problems**

## F1 — BR-2 extracts the wrong field with the wrong pattern (critical, high)

**Break scenario.** `/bugfix` blames the root-cause lines of a bug in `ETHOS.md` and gets
commit `0998a623`, whose subject is `REQ-526: Context-doc truth pass — ETHOS count, /map
removal, stale-claim sweep (#91)`. BR-2 extracts `\[(REQ|TASK)-[0-9]{3,6}\]` from the
**subject** → no match: the subject uses a bare `REQ-526:` prefix, not a bracketed trailer.
BR-7 fires and writes `attribution: none`. Measured **per commit** across this repo's 173
commits: 72 carry provenance in some accepted form, but only 37 carry a bracketed trailer in
the subject — so BR-2 as written finds 37 of 72 and silently loses **49%** of available
attributions. (An earlier draft of this finding said "the large majority", derived from a
`grep -c` that counted matching *lines* rather than commits; the per-commit figure is 49% and
is the one that matters.) The three real-world forms are `[TASK-xxx]`/`[REQ-xxx]` (37 subject,
37 body), `REQ-526: …` (20 subject-prefix), and `fix(BUG-145): …` (19 scope, correctly not an
attribution).

**Refutation attempt.** I tried arguing that `git blame --porcelain` exposes only a `summary`
field (the subject), so BR-2 is merely describing what blame makes available. That inverts
the problem: an implementer would faithfully read the subject and faithfully miss the
trailer, because the trailer lives in the body and requires a second
`git log -1 --format=%b <sha>` that BR-2 never mandates.

## F2 — TASK ids are not globally unique, so TASK→REQ resolution is ambiguous (major, high)

**Break scenario.** Blame yields a commit whose body carries `[TASK-001]`. BR-2 resolves it
"via that task file's `req:` frontmatter" — but `TASK-001.md` exists three times across
different REQ directories (as do `TASK-002.md` and `TASK-003.md`; 157 task files, 151
distinct names). The glob returns three files with three different `req:` values. BR-3 sees
"more than one distinct REQ" and halts — on an ambiguity manufactured by the id scheme, not
by genuine multi-REQ causation. Recent REQs restart task numbering at 001, so this affects
new work, not just legacy.

**Refutation attempt.** I tried arguing the blamed commit's subject disambiguates (it often
literally says `REQ-526:`). It frequently does — but that is a different derivation path
than BR-2 specifies, and relying on it collapses into F1's subject-vs-body confusion. BR-2
as written has no REQ-scoping step for the task lookup.

## F3 — the `introduced_by` array is unreachable beyond one element (minor, medium)

**Break scenario.** The System Model types `introduced_by` as an array, implying a bug can be
attributed to several REQs — a real case when a defect emerges from the interaction of two
merged REQs. But BR-3 halts whenever more than one REQ survives validation, and AC-5 resolves
that halt by "writes nothing until one is chosen". The derived path can therefore only ever
produce a one-element array; genuine multi-attribution is reachable only by hand-editing with
`attribution: manual`.

**Refutation attempt.** I argued the operator could choose to record both candidates at the
halt. Neither BR-3 nor AC-5 permits it — AC-5 says one is chosen.

## Coverage

Lenses run: omissions, untestable rules, contradictory BRs/ACs, unstated assumptions, scope holes.
Lenses skipped: none applicable (spec target — correctness/diff lenses do not apply).

Execution venue: single-context. The `adversary` agent was not dispatched: this session carries
a standing operator instruction not to use the Agent tool unless explicitly requested. The
skill's documented degradation path (same lenses, inline) was used, and this is stated rather
than silently skipped.

BR enumeration — BR-1 attacked, BR-2 attacked (F1, F2), BR-3 attacked (F3), BR-4 attacked,
BR-5 attacked, BR-6 attacked, BR-7 attacked (F1), BR-8 attacked, BR-9 attacked. None skipped.

AC enumeration — all 11 attacked. None skipped.
