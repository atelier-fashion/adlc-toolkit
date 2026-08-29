---
id: LESSON-582
title: "bash 3.2 cannot parse a `case` statement inside `$( )` — the shell that rejects your script is the oldest one a user has, not the newest one CI runs"
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash", "zsh", "sh"]
concerns: ["portability", "ci", "developer-experience", "silent-failure"]
tags: ["bash-3.2", "macos-system-bash", "command-substitution", "case-statement", "cross-shell", "dual-shell-runner", "BR-9", "syntax-error"]
req: BUG-201
created: 2026-08-28
updated: 2026-08-28
---

## What Happened

Writing the BUG-201 doc-contract guard in `partials/tests/forge.test.sh`, this shape went
in — a `case` inside a `while` inside a command substitution:

```sh
MISSING=$(printf '%s\n' "$EMITTED" | while IFS= read -r cls; do
  case " $DOCUMENTED " in
    *" $cls "*) : ;;
    *) printf '%s ' "$cls" ;;
  esac
done)
```

`sh partials/tests/run.sh` died in its **bash** pass:

```
forge.test.sh: line 156: syntax error near unexpected token `;;'
```

and passed clean in its **zsh** pass. Reduced to a minimum and measured across every
shell on the machine:

| shell | result |
|---|---|
| `/bin/bash` 3.2.57 (macOS system bash) | **syntax error** |
| `/bin/sh` (bash 3.2 in posix mode) | **syntax error** |
| `/opt/homebrew/bin/bash` 5.3.15 | ok |
| `zsh` 5.9 | ok |
| `dash` | ok |

bash 3.2's parser reads the unbalanced `)` that closes a `case` **pattern** as the `)`
that closes the enclosing `$(`, then chokes on the `;;` it did not expect. It is fixed in
modern bash. macOS still ships 3.2.57 as `/bin/bash` and `/bin/sh` — the GPLv3 freeze —
so this is not a historical curiosity, it is the default shell on every Mac.

Note which way round the failure fell. Ubuntu CI runs bash 5 and would have gone green.
The only thing that caught it was running the harness under the **old** local bash.

## Lesson

**A `case` statement inside `$( )` is not portable to bash 3.2.** Three ways out, all
verified on 3.2.57:

1. **Don't put `case` in a command substitution.** Reach for a tool instead — the fix
   here computes a set difference with `comm` over two sorted lists, which is shorter
   than the loop it replaced.
2. **Parenthesize the patterns**: `(a) … ;;` instead of `a) … ;;`. The leading `(`
   balances the parser.
3. **Move the `case` into a function** and call the function from `$( )`.

The general form of the lesson is bigger than the bug: **compatibility is set by the
oldest interpreter in your user population, and CI usually runs one of the newest.** A
green CI badge is evidence about Ubuntu's bash 5, not about the `/bin/bash` on the laptop
of whoever runs the toolkit next. When a project declares a portability contract — here
BR-9's "runs under sh/bash/zsh" — the contract is only as real as the matrix that
actually exercises it.

Which is why `partials/tests/run.sh` exists and why it re-execs itself under each shell
rather than trusting one pass: this defect was **invisible to the zsh pass**, and zsh is
the shell the macOS Claude Code executor uses. A single-shell runner would have shipped a
test file that the project's own primary development platform cannot parse.

## Why It Matters

The failure is a **parse** error, not a runtime one, so it is total: the file does not
partially run, it does not run at all. Everything after the offending line silently stops
being tested. In this instance the harness aborted mid-suite and still printed a healthy
wall of `PASS` lines from the assertions that had already run — reading the tail of that
output, or grepping it for `FAIL`, showed a clean bill of health. The abort was only
visible in `run.sh`'s exit code and in the absence of one `ALL CASES PASS` line.

So the cost is not "a shell some people use is unhappy". It is a test suite that reports
success while having stopped early, on the platform the project is primarily developed on.

## Applies When

- Writing shell that must run under more than one shell, or on macOS at all.
- Any `case` inside `$( )`, `` ` ` ``, a subshell, or a pipeline stage — especially in
  test harnesses, where this construct is common and the blast radius is silent
  under-testing.
- Reading a green CI run as evidence of portability: name the shell and version CI
  actually used before believing it.
- Judging a test suite by its `PASS` lines: a parse-aborted suite still prints the ones it
  reached. Check the exit code and assert on a terminal "all cases ran" marker.
