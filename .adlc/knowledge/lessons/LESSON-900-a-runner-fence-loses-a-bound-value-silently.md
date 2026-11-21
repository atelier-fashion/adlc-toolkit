---
id: LESSON-900
title: "A runner fence loses a bound value silently: `name=` or `for name` in a string unbinds it, and `${NAME:-default}` loses its default"
component: "adlc/tools/adlc/fence-census"
domain: "adlc"
stack: ["python", "shell", "markdown"]
concerns: ["security", "correctness", "developer-experience"]
tags: ["fence-census", "fence-run", "exec-engine", "free-vars", "transform", "bound-value", "skill-authoring"]
bug: BUG-288
created: 2026-11-21
updated: 2026-11-21
kind: domain
evidence: "BUG-288; tools/adlc/fence_census.py:323 (_VAR_RE), :324 (_ASSIGN_RE), :325 (_FOR_READ_RE). Measured on f53f322: free_vars of a two-line fence that reads \"$prNumber\" is ['prNumber']; with `echo \"set prNumber=<n> first\"` or `echo \"no PR for prNumber\"` as its first line it is [], and unmarked_pr_arguments then refuses the fence. transform('root=\"${PRIMARY_WORKTREE:-.}\"') gives root=\"${ADLC_ARG_PRIMARY_WORKTREE}\": the `:-.` is gone. A fence whose first line is `echo \"set REPO_ID=<id> first\"` still routes, binds no REPO_ID and runs `repo=\"$REPO_ID\"` as written."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

BUG-288 rewrote `/architect` Step 5's footprint fence to take three new values the fence
runner binds: `$prNumber`, `$REPO_ID` and `$PRIMARY_WORKTREE`. The census decides which
variables are bound with line-level patterns, and two of them matter to anyone who writes
a fence's messages and defaults.

`free_vars` counts a variable as the fence's own when `name=` follows whitespace anywhere on
a code line, or when the name follows `for` or `read`. It does not look at quoting, so an
`echo "set prNumber=<n> first"` or an `echo "no PR for prNumber"` is read as an assignment.
The variable then stops being a bound value. `transform` rewrites a whole `${NAME…}` to
`${ADLC_ARG_NAME}`, so `${PRIMARY_WORKTREE:-.}` loses its default and becomes an empty string
when the caller gives none.

## Lesson

In a fence the runner routes, keep a bound variable's name away from three spellings on
code lines, comments at line start aside:

- `NAME=` after a space, even inside a quoted message. Write "the PR number given (#$prNumber)",
  not "prNumber=$prNumber".
- `for NAME` and `read NAME`, even inside a quoted message.
- `${NAME:-default}`. Assign first and test after: `x="$NAME"; [ -n "$x" ] || x=default`.

After changing a fence, read its census record and check that `placeholders` names every
value the prose tells the caller to set. A missing name is this pitfall.

## Why It Matters

For a PR-marked variable the mistake fails closed: the forge call's argument is no longer a
marked variable, and the fence does not route. For any other variable it fails quietly: the
fence routes, the runner binds nothing, and the fence reads whatever the inherited
environment holds under that name, with no pattern check. A lost default is quieter still.
`find "$root/.adlc/specs"` with an empty `$root` would have looked in `/.adlc/specs`
and found no state file, so every run would have skipped as standalone.

## Applies When

Writing or editing a shell fence in a file of the exec set (`fence_census.EXEC_FILES`) that
reads a variable the caller sets, or adding a name to `VAR_PLACEHOLDERS`; reviewing a census
diff where a fence's `placeholders` list got shorter.
