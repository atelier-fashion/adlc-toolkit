---
id: LESSON-754
title: "A harness that runs a skill's fence must substitute its argument placeholders and copy every directory the fence reads, or a fence that skips bad input passes while doing nothing"
component: "adlc/partials/tests"
domain: "adlc"
stack: ["sh", "markdown", "python"]
concerns: ["testing", "silent-failure", "structural-enforcement"]
tags: ["fence-extraction", "placeholder", "plugin-route", "init", "test-harness", "vacuous-pass", "toolkit-copy"]
req: REQ-657
created: 2026-10-30
updated: 2026-10-30
kind: process
evidence: "REQ-657 Phase 5: partials/tests/plugin-route.test.sh case_init_copy_fences_same_tree failed with 'plugin route did not vendor .claude/settings.json' after /init Step 8 became a render fence carrying the '<harnesses>' placeholder; the harness ran the fence raw, the placeholder fell into the 'not a harness name' skip arm, and the step still exited 0. It passed once the harness substituted '' for the placeholder and its ToolkitRoot copy included harness/ (108db1f)."
confidence: high
enforcement: "test:partials/tests/plugin-route.test.sh"
generalizes: []
supersedes: []
---

## What Happened

REQ-657 turned `/init` Step 8 from a `cp` of a static template into a loop over a
`'<harnesses>'` placeholder that the model replaces with the `--harness` value. A
shell harness extracts that fence from `init/SKILL.md` and runs it on a simulated
plugin route. It ran the text as written: the literal placeholder failed the
fence's own name check, the loop skipped it, and the fence exited 0 having rendered
nothing. Only the downstream "did it vendor .claude/settings.json" assertion caught
it, and the harness's toolkit copy also lacked the new `harness/` directory the
render reads.

## Lesson

When a fence gains a value placeholder, every harness that extracts and executes
that fence has to perform the substitution the model performs (here, `''` for an
absent flag), in the same change. And when a fence starts reading a new toolkit
directory, every harness that builds a toolkit copy has to copy it. A fence that
skips or defaults on input it does not recognise exits 0 either way, so assert on
what the fence produced, never on its exit status alone.

## Applies When

Adding a `'<placeholder>'` to a skill fence, or making a fence read a toolkit
directory it did not read before, in a repo whose test harnesses extract skill
fences and run them (grep the tests for the skill's path and step heading).
