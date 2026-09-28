---
id: LESSON-663
title: "To keep a model's shell inside a classifier's grammar, allowlist what it may run — forbidding commands one at a time never converges"
component: "adlc/analyze"
domain: "adlc"
stack: ["markdown", "sh"]
concerns: ["portability", "privacy"]
tags: ["teton-code", "shell-provenance", "session-pinned", "allowlist", "verification", "lint-skills", "bug-230", "bug-228"]
req: BUG-230
created: 2026-09-28
updated: 2026-09-28
---

## What happened

BUG-230 made `/analyze` runnable on Teton Code in three live-verified rounds.
Every round followed the skill's prescribed commands exactly, and every one of
those stayed in reach. Rounds 1 and 2 still pinned, each on a command the
model **made up**:

1. #176 rewrote Step 2a's hygiene shell in probe-verified spellings. The model
   improvised `cargo test --workspace` and pinned.
2. #177 forbade test runners, build tools and package managers. The model
   improvised `find crates -name '*.rs' | xargs wc -l` to size the scope and
   pinned.
3. #178 replaced the denylist with a positive rule: on such a harness the only
   shell allowed is the lines of the skill's `# provenance-safe` fences, and
   everything else goes through the harness's `glob`/`grep`/`read`. Run 5
   made 24 tool calls, 8 of them shell, every one a fence line. No pin.

The model understood the harness perfectly every time; it narrated each Teton
skip correctly. Its problem wasn't comprehension. A denylist leaves the space
of plausible commands open, and a capable model fills it.

## Lesson

When a host refuses whole categories of shell (Teton's classifier returns
`Unknown` for any unrecognised verb), a skill should state what shell **is**
allowed, not what isn't. This is the same allowlist-over-denylist polarity
Teton's own classifier is built on (ADR-614-1), applied one layer up. Two
things make the allowlist cheap to hold:

- **Verify the spellings against the real classifier.** A scratch
  `#[test]` calling `classify` with the built-in boundaries gave a definite
  answer per string, with controls that must come back `unknown`. It caught
  `--format=%cs` (the `=` reads as an env assignment), which prose review had
  passed.
- **Enforce the fences structurally.** `lint-skills`' `provenance-safe-fence`
  keeps a later "tidy-up" from reintroducing `$(…)` or `--flag=value`.

## How to apply

- Before shipping a skill that a Teton model will run, give it one top-level
  rule: "on a provenance-classifying harness, run only this skill's
  `# provenance-safe` fences; use glob/grep/read for everything else." Give
  every shell need (sizing, listing, git metadata) a fence. A need with no
  fence becomes an improvisation.
- Verify each new fence spelling with a scratch `classify` test in a
  throwaway teton-code worktree, and include a control that must be
  `unknown`.
- Verify the skill in a live Teton turn and read the transcript's
  `tool_call_input` records. The rule has held when every shell call is a
  fence line.
