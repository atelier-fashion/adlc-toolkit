---
id: BUG-xxx
title: "Bug Title"
status: open
severity: critical | high | medium | low
created: YYYY-MM-DD
updated: YYYY-MM-DD
component: ""       # narrow area, e.g., "API/auth", "iOS/SwiftUI", "adlc/spec"
domain: ""          # broad area, e.g., "auth", "payments", "ui"
stack: []           # tech layers touched, e.g., ["express", "firestore"]
concerns: []        # cross-cutting dimensions, e.g., ["security", "performance", "a11y"]
tags: []            # free-form keywords, e.g., ["password-reset", "tokens"]
introduced_by: []   # OPTIONAL. REQ id(s) whose merge introduced the defective behavior,
                    # e.g. ["REQ-483"]. Derived by /bugfix from `git blame` on the
                    # root-cause lines; an array because a defect can genuinely emerge
                    # from the interaction of several merged REQs. An empty array is a
                    # meaningful "no attribution", not a missing value.
attribution: none   # OPTIONAL. derived | manual | none — how introduced_by was populated.
                    # `derived` = /bugfix read it from a commit trailer; `manual` = a human
                    # set it; `none` = no candidate survived validation (the benign path).
regression_tests: []    # OPTIONAL. Repo-relative path(s) of the test file(s) that pin this
                        # bug, each file citing the bug id, e.g. ["tests/test_reset.py"].
                        # A test in a sibling repo is prefixed with that repo's id from
                        # .adlc/config.yml, as `<repo-id>:<path>`: ["api:tests/test_reset.py"].
                        # Flow list on this one line only: the frontmatter readers drop or
                        # misread a block list.
regression_waiver: ""   # OPTIONAL. One line saying why no test can reproduce this bug.
                        # Always double-quoted: a plain value is cut at the first ` #`.
                        # Never set both fields: a bug has its tests or a waiver. /bugfix
                        # writes one of the two when the project sets
                        # `bugfix.regression_test: required` in .adlc/config.yml.
---

<!--
`introduced_by` and `attribution` are optional and additive: a bug file carrying neither
parses and processes unchanged, and every consumer treats absent as `attribution: none`
with an empty list. The reverse edge (REQ → its incidents) is NEVER written into a REQ
spec — it is derived at read time by scanning these frontmatter blocks, because a stored
reverse edge breaks silently when an artifact is moved or renumbered (REQ-593 BR-4).

`regression_tests` and `regression_waiver` are optional and additive too (REQ-691). A bug
file carrying neither parses and processes unchanged, and absent, an empty list and an
empty string all mean the same thing: legacy, no regression test recorded and none waived.
The regression check (`adlc regression-check check`) reports a resolved legacy bug but
never fails it. It passes a bug whose listed tests exist, are tracked by git and cite the
bug id, accepts a non-blank waiver, and fails anything else, including both fields set.
-->


## Description

What's broken.

## Reproduction Steps

1. Step 1
2. Step 2

## Expected Behavior

What should happen.

## Actual Behavior

What happens instead.

## Environment

- Platform:
- Version:

## Root Cause

(filled during investigation)

## Resolution

(filled after fix)

## Regression Test

(filled by /bugfix when the project sets `bugfix.regression_test: required`; stays empty
when regression tests are off for the project)

- Test path(s): `path/to/test_file` — each one cites this bug's id
- Command run: `<the command that ran the regression test(s)>`
- Without the fix: fails — `<the first failing assertion line>`
- With the fix: passes

Or, when no test can reproduce the bug:

- Waived: <the one-line reason recorded in regression_waiver> — why no test can reach the
  defect

## Files Changed

- `path/to/file.js` — description
