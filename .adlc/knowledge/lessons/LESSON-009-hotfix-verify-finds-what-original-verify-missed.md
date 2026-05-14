---
id: LESSON-009
title: "An /analyze run on the post-REQ-414 toolkit found 8+ issues that REQ-414's own 6-agent verify pass missed — manual prose validation rules are uniquely fragile, and your auditor must run on the same-machine state your users hit"
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "bash"]
concerns: ["security", "verify-quality", "installer-portability"]
tags: ["hotfix", "verify", "audit", "path-traversal", "shell-detection", "launchctl", "gitignore", "prose-validators"]
req: REQ-415
created: 2026-05-13
updated: 2026-05-13
---

## What Happened

REQ-414 shipped the first Kimi delegation in ADLC skills (`/analyze`, `/wrapup`) with a
6-agent verify pass that approved the work. Within hours of merge, running `/analyze` on
the toolkit itself surfaced 8 issues — one Critical, three High, four Major/Minor — that
the original verify pass had missed. REQ-415 (this REQ) shipped to fix them. Then REQ-415's
own 6-agent verify pass found 4 more issues in REQ-415's fixes — the `..`-rejection rule
was still ambiguous, `dscl` could fail on Linux under `set -eu`, `case` arms didn't match
versioned shell paths, and only 3 of 8 tracked `pipeline-state.json` files had been
initially removed.

Two patterns are responsible:

1. **Prose-as-validator is uniquely fragile.** When a skill instructs an LLM at runtime to
   "reject any path that contains a `..` segment," the reviewer agent reads that and says
   "looks reasonable." But the LLM at execution time has to operationalize the prose, and
   subtle wording differences ("a `..` segment" vs "the two-character substring `..`" vs
   "a path component equal to `..`") produce different rejection behavior. The fix has to
   spell out the exact check with examples of every shape it must reject.

2. **The original verify pass tested the artifact in a clean repo state, not the messy
   real-world state the user hits.** REQ-414 verify approved code that worked on the
   reviewer's clean main + zsh shell. The `/analyze` audit a few hours later was run on a
   real machine with: (a) bash login shell on a second device, (b) GUI-launched Claude
   Code that couldn't see env vars, (c) 8 stale `pipeline-state.json` files committed by
   the prior 3 REQ pipelines. None of those were in the reviewer's simulated context.

## Lesson

1. **For LLM-interpreted validation rules, write the check as both an English description
   AND a concrete example list.** "Reject if any segment equals `..`" plus "this rejects
   `../etc`, `./../etc`, `subdir/../etc`, `safe/..//etc`" gives the runtime LLM something
   to pattern-match against, not just a vague rule. The original REQ-414 fix said "reject
   any path containing a `..` segment" with one example — that wasn't enough.
2. **Installer scripts that touch shell rc files MUST detect the actual login shell.**
   Defaulting to `~/.zshrc` on macOS is correct ~70% of the time but wrong for every user
   who chose bash. `dscl . -read /Users/$USER UserShell` is the macOS-canonical way; wrap
   it in `command -v dscl` for Linux portability and `|| true` for `set -eu` safety.
3. **`case` patterns for shell-binary names need globs, not literals.** `case
   "$(basename "$SHELL")" in zsh)` doesn't match `zsh-5.8` (Homebrew versioned install).
   Use `zsh*) / bash*)` to be robust to versioned suffixes.
4. **`launchctl setenv` is the missing link between `~/.zshrc` and GUI-launched Mac apps.**
   Env vars in `~/.zshrc` are invisible to Spotlight-launched Claude Code. `launchctl
   setenv` runs once per boot and makes the var inheritable by every subsequent GUI
   process. Add it to any macOS installer that expects "the user set this in their rc."
5. **Transient per-run state files (`pipeline-state.json`) should be gitignored from day
   one, not retrofitted three REQs later.** Once they're tracked, they accumulate stale
   `completed:true + merged:false` rows that confuse future audits. Add the `.gitignore`
   entry the same commit you create the state-file pattern.
6. **The auditor that runs against real consumer state will find what the verify-pass
   reviewer missed.** Don't ship a feature whose verify pass and `/analyze` run yield
   different results. If you can't run `/analyze` from a clean checkout immediately
   post-merge, the test surface is incomplete.

## Why It Matters

Each of the issues REQ-415 fixed would have either silently broken a user (path traversal,
shell detection) or accumulated technical debt (stale state files, dead sed patterns,
missing Prerequisites). The verify pass is good but not sufficient — the cheap thing to
add is "post-merge, run `/analyze` once and treat any High+ findings as a follow-up REQ."
That habit catches the gap between "reviewer reads the diff in a clean context" and
"user runs the code on their actual machine."

## Applies When

Writing or reviewing any ADLC skill that contains LLM-interpreted validation rules in its
markdown body; writing or reviewing any installer script that touches user shell rc files;
adding any new per-run state file to a tracked directory; closing out a REQ that shipped
a new flow and deciding whether a post-merge audit is worth running.
