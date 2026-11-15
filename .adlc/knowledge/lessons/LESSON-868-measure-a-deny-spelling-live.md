---
id: LESSON-868
title: "Measure a deny rule's spelling against the harness, and model a deny only where it was seen to refuse: a model that assumes a deny catches a form fails open"
component: "adlc/tools/adlc/exec-matcher"
domain: "adlc"
stack: ["python", "yaml"]
concerns: ["security", "correctness", "testing"]
tags: ["exec-engine", "deny", "wildcard", "glob", "git-c", "matcher-model", "live-run", "claude-code"]
req: BUG-269
created: 2026-11-15
updated: 2026-11-15
kind: domain
evidence: "BUG-269: on claude 2.1.316 under the engine's isolation flags, with a Bash(git -C:*) allow, the engine deny Bash(git -C * push --force:*) let `git -C <repo> push --force` push its ref (live rows l4, w4, w6), while Bash(git -C * push --force*) refused it bare and with arguments (y1, y2). The only prior test, test_exec_matcher.py::test_wildcard_rule_text, checked the toolkit's own regex, and exec_matcher._deny_views stripped `git -C <path>`, so admits() called the policy sound. test_a_deny_does_not_see_through_git_c and test_wildcard_rule_text fail on 2cecd6c and pass on 723a33c."
confidence: high
enforcement: test:tools/adlc/tests/test_exec_matcher.py
generalizes: [LESSON-716]
supersedes: []
---

## What Happened

REQ-659 added `git -C * push --force` and `-f` to the claude adapter's exec denies, and the engine rendered them as `Bash(git -C * push --force:*)`. claude 2.1.316 matches nothing with a rule that holds an inner `*` and also ends in `:*`, so both denies were inert from the start. REQ-682's matcher model compiled the glob anyway. Before judging a deny, it also stripped `git -C <path>`, which Claude does not do. The only test of the spelling ran the toolkit's own regex, so it passed. The defect stayed latent only because no allow in either tier matches `git -C`.

## Lesson

**A rule's spelling is a claim about the harness's parser.** Measure it with one live launch under the engine's real flags before you rely on it: allow the command, deny it in the new spelling, and look for the side effect. A unit test against the toolkit's own model of the matcher proves only that the model agrees with itself.

**A model used to audit admission must refuse only where the harness was seen to refuse.** For an admission check, assuming a deny catches a wrapped form (`git -C`, an env prefix, a glob) is the unsafe direction: the audit then passes a policy the harness would run. Keep the generous views for a finder like `deny_hits`, whose job is to spot a move in any spelling. Never use them in `admits`.

On claude 2.1.316, spell a glob deny with its own trailing `*` (`X*`), not `X:*` and not `X *`, which misses the bare command.

## Why It Matters

A deny that matches nothing still looks right in the adapter, in the rendered argv and in a model-backed test. Its absence shows up only on the day an allow is added that it was meant to back.

## Applies When

Adding or changing a deny or allow spelling for an agent harness, above all one with a glob, a wrapper (`git -C`, `env`, `sh -c`) or a suffix such as `:*`. Also when extending a model of a harness's matcher that an audit relies on.
