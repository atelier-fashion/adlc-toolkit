---
id: ASSUME-030
title: "Under `claude -p` an allow is checked against each statement of a compound command, and no allow admits `.` or `source`"
status: validated
req: REQ-682
created: 2026-11-09
resolved: 2026-11-09
---

## Assumption

The installed `claude` checks each statement of a compound command (`;`, `&&`, `||`, a
newline, `if … fi`) against the allow rules on its own, and denies the whole command when any
statement is not admitted. An absolute-path prefix rule admits that one executable with
trailing arguments, and nothing else.

## Context

REQ-682 had to choose how a skill fence runs under `/sprint --exec`. A narrow allow route works
only if Claude splits a compound command; a route that sources partials works only if a prefix
rule can admit `.`. Neither was measured (REQ-682 spec, Assumptions).

## Resolution

Validated on `claude` 2.1.316 under BUG-260's isolation flags, 2026-11-09 (REQ-682
architecture, "Evidence first"): rows 2, 3 and 8 show the second statement of `;`, `&&`, a
newline and an `if` body judged on its own; rows 11 to 13 show `Bash(<path>/runner:*)` admit
`<path>/runner a` and refuse `<path>/runner-evil` and an env prefix; rows 14 and 15 show an env
prefix stripped for a deny and refused for an allow. Rows 9 and 10 refute the other half of the
question: `.` is refused ("evaluates arguments as shell code") even under a matching allow, so no
allow can admit a partial-sourcing fence. The live rows `compound-tail` (an admitted fence-run
call with `; git push origin HEAD:main` appended: denied, remote main unmoved), `source-traversal`
and `source-model-written` in `tools/adlc/tests/e2e/claude-exec-live.sh` reproduce it through the
engine's own argv. `tools/adlc/exec_matcher.py` holds the measured rules, pinned row by row by
`tools/adlc/tests/test_exec_matcher.py`.
