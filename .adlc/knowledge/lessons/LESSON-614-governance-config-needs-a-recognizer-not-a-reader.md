---
id: LESSON-614
title: "A governance config needs a recognizer, not a reader — and a differential oracle, not one author's corpus"
component: "tools/delegate"
domain: "adlc"
stack: [python, yaml, shell]
concerns: [security, correctness, data-governance, fail-closed, test-coverage]
tags: [parser, strict-schema, yaml, safe-load, differential-oracle, fail-open, mutation-testing]
req: REQ-609
created: 2026-09-02
updated: 2026-09-02
---

## What Happened

REQ-603 made `parse_delegate_config` — a hand-written flat reader for one
`delegate:` block — the sole authority over whether a developer's source files
are sent to a third-party API. Four adversarial passes then found nine distinct
fail-opens in it: a comment on the section header, a BOM, a tab-indented header,
a nested mapping hoisting `enabled: true` over a written `false`, a second
`delegate:` block, a directory at the path. Each yielded `{}`, indistinguishable
from *no config*, and legacy-key continuity then granted against an explicit
opt-out. A rewrite under a tests-first, mutation-proven discipline added six
more fail-opens in the same afternoon; two reviewers found shapes the author had
not imagined within the hour. REQ-609 replaced the reader with `yaml.safe_load`
behind a closed schema, a `SafeLoader` that refuses duplicate keys, aliases and
merge keys, and a differential oracle over a seeded and a generated corpus.

## Lesson

A reader that **skips** what it does not understand cannot be patched into one
that **refuses**: every branch added for a reviewed shape leaves the unreviewed
shapes open. When a file decides a security or data-governance outcome, parse
it with a real grammar and validate against a schema that names every allowed
key and type — "written" and "read" must be the same thing. Then test it against
a **second implementation** (here `yaml.safe_load` plus an independent
duplicate/alias detector over `yaml.compose`/`yaml.parse`) over a corpus a
generator produced, so the suite is no longer bounded by one author's
imagination. Mutation testing proves the tests you wrote; it cannot reach the
inputs you did not think of. "It's only three scalar fields" is not a reason to
hand-parse: field count is irrelevant once the field gates exfiltration.

## Why It Matters

The fail-opens were pre-existing on `main` for months and passed every suite.
Each one turned an operator's written `enabled: false` into transmission.
The recognizer closed them by construction, and the oracle caught two more
classes during review (PyYAML constructor exceptions escaping a "never raises"
contract; a merge key supplying `enabled` without the word appearing under
`delegate:`) that no hand-enumerated corpus contained.

## Applies When

Any hand-rolled parser or "minimal reader" sits on a security, governance, or
billing decision; any justification of the form "we only need N fields, a full
parser is overkill"; any review that finds a fail-open in a reader and proposes
a branch to fix it; any suite whose corpus was written entirely by the
implementation's author.
