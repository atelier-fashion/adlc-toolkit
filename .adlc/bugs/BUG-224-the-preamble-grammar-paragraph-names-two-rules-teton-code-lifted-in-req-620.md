---
id: BUG-224
title: "The preamble-grammar paragraph names two rules Teton Code lifted in REQ-620"
status: open
severity: low
created: 2026-09-09
updated: 2026-09-09
component: "adlc/context"
domain: "skills"
stack: ["markdown"]
concerns: ["developer-experience", "privacy"]
tags: ["preamble", "conventions", "teton-code", "req-620", "bug-220", "redirect", "pipeline"]
introduced_by: ["BUG-220"]
attribution: manual
---

## Description

**Not filed from this repo.** `~/.claude/skills` symlinks to the adlc-toolkit
checkout and its conventions file is that repo's to change, so the text below
is the follow-up, verbatim, for the orchestrator to file there (allocating the
id with `adlc_alloc_id bug` **from that repo**).

---

REQ-620

**Severity:** low. **Component:** `.adlc/context/conventions.md` (the BUG-220
preamble-grammar paragraph).

`conventions.md`'s BUG-220 paragraph — "Every `` !`…` `` preamble stays inside
the same grammar" — tells skill authors two things that stop being true of a
Teton Code host from the release carrying REQ-620 onward:

1. **that `2>/dev/null` is enough to pin.** REQ-620 lifts a redirect that reads
   nothing out of the command *before* it classifies the rest: `2>/dev/null`,
   `>/dev/null`, `1>/dev/null`, `2>>/dev/null`, `&>/dev/null`, `</dev/null`,
   `2>&1` and `1>&2`, each as a whole whitespace-delimited word (or the
   operator word immediately followed by a separate `/dev/null` word). A form
   glued to its verb (`ls>/dev/null`) or to a following command (`2>&1;ls`) is
   still refused, and every other use of `>` and `<` still refuses the whole
   command.
2. **that `| head`, `| tail` or `| grep` after a producer pins.** REQ-620 reads
   a content verb after a single `|` that names no existing file as taking its
   stdin from the previous segment — which was itself classified — so
   `ls .adlc/partials/ | head` and `git log | grep fix` are `rooted`. Recursive
   `grep` (`-r`, `-R`, `--recursive`, `-d recurse`, or a short-flag cluster
   containing `r`/`R`) still reads the tree whatever its stdin, and still pins.

**The ask:** scope **those two rules only** with "on Teton Code < the release
carrying REQ-620", and keep the rest of the paragraph exactly as it stands — no
quoting, no globs, no `$`, no parentheses or `;`, recognised verbs only, in-root
paths only (a `~/…` fallback in *any* segment still makes the whole line
unprovable even when it never runs), and the missing-file rule: a content verb
whose file argument does **not** exist is still scored as a read of the whole
root in a **first** segment, so the `cat .adlc/context/…` lines still pin on a
project that has not run `/init`. `/canary`'s `gcloud` lines and
`/template-drift`'s toolkit listing remain the known exceptions.

**Why scope rather than delete:** the narrow forms are correct on *both* host
versions, and a skill's preamble runs on whatever host the consumer has. The
paragraph should keep recommending them and mark the two rules as
version-scoped, so an author reading it on an older host is not misled in the
unsafe direction.

**Teton-code side:** REQ-620 BR-1, BR-2 and BR-4
(`.adlc/specs/REQ-620-harmless-redirects-in-the-shell-grammar/`), shipped in
`crates/tetond/src/harness/tools/shell_syntax.rs` and `shell_provenance.rs`.
The classifier's own toolkit-preamble table
(`the_toolkit_preamble_shapes_are_rooted_and_the_old_ones_are_not`) is the test
that will need a row per rule this paragraph relaxes.

---

## Expected Behavior

`conventions.md` keeps recommending the narrow forms and marks the `2>/dev/null` and `| head` rules as holding only on Teton Code older than the release carrying REQ-620.

## Actual Behavior

The paragraph states both rules unconditionally, which is false on a current host and steers authors away from forms that are now provably in reach.

## Environment

- adlc-toolkit 5.2.x; Teton Code ≥ the release carrying REQ-620 (teton-code PR #316).

## Files to Change

- `.adlc/context/conventions.md` — the BUG-220 paragraph, two rules version-scoped
