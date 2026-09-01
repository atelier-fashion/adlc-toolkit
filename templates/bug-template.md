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
---

<!--
Both fields above are optional and additive: a bug file carrying neither parses and
processes unchanged, and every consumer treats absent as `attribution: none` with an
empty list. The reverse edge (REQ → its incidents) is NEVER written into a REQ spec —
it is derived at read time by scanning these frontmatter blocks, because a stored
reverse edge breaks silently when an artifact is moved or renumbered (REQ-593 BR-4).
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

## Files Changed

- `path/to/file.js` — description
