---
id: LESSON-904
title: "A message that quotes a name the project chose can be moved to any class by that name: match the part no name can hold, and try that arm before the arms a name can reach"
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash", "python"]
concerns: ["correctness", "api-contract", "silent-failure", "testing"]
tags: ["error-classification", "forge-adapter", "pattern-matching", "substring-match", "branch-name", "case-order", "pr-create", "duplicate-pr"]
bug: BUG-292
created: 2026-11-23
updated: 2026-11-23
kind: domain
evidence: "BUG-292, fix 78500a2. partials/tests/forge.test.sh §4e on a0eeab8: `_adlc_forge_classify` on gh's refusal `a pull request for branch \"fix/credentials-not-found\" into branch \"release/blocked\" already exists:` printed auth-missing, and with the head `feat/REQ-12-branch-protection-policy`, or the URL of a repository named policy-engine, printed merge-blocked-by-policy; the same sentence with the head `feat/x` printed network. All four print pr-already-exists on 78500a2, where the arm is the first in the case. tools/adlc/tests/test_bug292_forge_pr_already_exists.py::test_bug292_each_forges_refusal_has_the_class failed in 8 of 8 cases before and passes after."
confidence: high
enforcement: test:partials/tests/forge.test.sh
generalizes: []
supersedes: []
---

## What Happened

`_adlc_forge_classify` turns a backend's stderr into an error class with a `case` over
substrings, tried in a fixed order, most specific first. BUG-292 added a class for a forge's
refusal of a second PR for one head and base. The obvious place for the new arm was the
documented one: after `auth-missing`, `pr-not-found` and the policy arms, before the default.

The refusal is `a pull request for branch "<head>" into branch "<base>" already exists:`
followed by the PR's URL. It quotes two branch names and a repository name. The earlier arms
match ordinary words anywhere in the message: `credentials`, `authentication`, `not found`,
`policy`, `blocked`. So with the arm in its documented place, a head named
`fix/credentials-not-found` made the refusal `auth-missing`, and a repository named
`policy-engine` made it `merge-blocked-by-policy`. The test that pins the plain sentence would
have passed. Only the cases written with awkward names failed.

## Lesson

A classifier that matches substrings of a whole message treats every word in it as the
backend's. When the message quotes a name someone else chose (a branch, a repository, a file, a
title, a URL), that name is input, and it can carry any word an arm is waiting for.

1. **Ask of each message which parts are quoted.** If it echoes a ref, a path or a URL, it can
   be reclassified by whoever names things, with no intent needed: `feat/…-policy` is an
   ordinary branch name.
2. **Match on what a name cannot hold.** A ref holds no space, so `a pull request for branch `
   cannot come from a branch name. An error code (`TF401179`) is better still. The signature
   then cannot be forged by the quoted part.
3. **Try that arm before every arm a name can reach.** "Most specific first" orders arms by how
   narrow their pattern is. That is the wrong order for a message that carries quoted names:
   its arm goes first, and the reason is written beside it, or the next editor moves it back.
4. **Pin it with names chosen to collide.** One case per class the quoted name could reach, in
   the same table as the plain sentence. A fixture with a head called `feat/x` proves nothing
   about order.

The arms already in the classifier are not all safe by this rule. `no pull requests found for
branch "<name>"` quotes a branch and is matched after `auth-missing`; BUG-292 names it and
leaves it, since it has not been met in use.

## Why It Matters

The wrong class is not noise. `auth-missing` sends an operator to their login, and
`merge-blocked-by-policy` sends them to get a review or wait for checks. Both are confident and
both are wrong, for a refusal that means "the PR you want is already open". It would have
shown only in a project whose branch or repository happened to carry the word, which is the
project least able to see why.

## Applies When

Adding or reordering an arm in `_adlc_forge_classify` or any classifier that substring-matches
a tool's output; classifying a message that echoes a branch, a path, a URL or any other name
the caller chose; writing the fixture table for such a classifier; reviewing a "most specific
first" pattern list.
