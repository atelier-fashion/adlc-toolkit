---
id: LESSON-329
title: "Skill bash runs under the operator's shell (zsh) — dogfood by executing it, don't trust lint or an sh-only run"
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "zsh", "sh", "claude-skills"]
concerns: ["portability", "testing", "correctness"]
tags: ["zsh", "word-splitting", "dogfooding", "shell-portability", "posix", "lint-gap"]
req: REQ-482
created: 2026-06-04
updated: 2026-06-04
---

## What Happened

While building `/manifest` (REQ-482), the skill's `sh` fenced block passed `tools/lint-skills` (sentinels, paren-balance, posix-fence, cross-fence-fn — all clean) **and** ran correctly under `sh -c`, but produced a broken glob when executed by the Bash tool, whose shell on macOS is **zsh**. An unquoted `for sr in $self_list` kept the list's trailing space because **zsh does not word-split unquoted parameter expansions by default** — yielding `req="REQ-482 "` and the glob `.adlc/specs/REQ-482 -*/requirement.md`, which zsh aborts with "no matches found". A `$TO="timeout 20"` prefix used as a bare `$TO git fetch` had the same hazard (zsh runs it as a single word).

## Lesson

ADLC skill bash is executed by Claude via the Bash tool, and that shell is **not guaranteed POSIX sh/bash** — on macOS it is zsh, whose splitting semantics differ. Therefore:

1. **Dogfood a skill by EXECUTING its fenced block under the real shell** — ideally both `sh -c` and `zsh -c` — not by reading it and not only by `sh -c`. Extract the block (`awk '/^```sh$/{f=1;next} f&&/^```$/{exit} f'`) and run it.
2. **Never rely on unquoted word-splitting.** Iterate lists over newlines with `printf '%s\n' "$items" | while read -r x`, and wrap a variadic command prefix (a timeout) in a function using `"$@"` (`with_timeout() { command -v timeout >/dev/null 2>&1 && timeout 20 "$@" || "$@"; }`) rather than an unquoted `$VAR`.

## Why It Matters

`tools/lint-skills` checks *structure* (paren balance, `local` in `sh` fences, cross-fence functions) but **cannot catch runtime shell-semantics divergence** — a skill can be lint-clean and still misbehave under the executor shell. This is the same class as LESSON-013 (BSD vs GNU grep), extended to sh-vs-zsh: a portability bug that only a real-shell *execution* surfaces. Every skill that loops over a derived list or builds a command prefix is exposed, so the guard is a habit (write split-free bash) plus a verification step (run it under the real shell), not a linter rule.
