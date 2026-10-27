---
id: LESSON-716
title: "A validator for a format another reader consumes must parse the way that reader does — enumerate last-wins keys, key spellings and continuations, and fail closed on anything it cannot see"
component: "adlc/partials"
domain: "adlc"
stack: ["sh", "markdown", "yaml"]
concerns: ["correctness", "security", "silent-failure", "structural-enforcement"]
tags: ["frontmatter", "validator", "yaml", "duplicate-keys", "fail-closed", "lesson-check", "REQ-646"]
req: REQ-646
created: 2026-10-27
updated: 2026-10-27
kind: "domain"
evidence: "REQ-646 Phase-5 security High (a repeated evidence key with a multi-line value carrying a secret and a home path returned rc 0) and correctness M1 (supersedes:[LESSON-034] with no blank was ignored by the check but matched by the lookup); fixed in partials/lesson-check.sh and pinned by partials/tests/lesson-check.test.sh key_needs_blank_after_colon; PR #189 at 0310579"
confidence: "high"
enforcement: "test:partials/tests/lesson-check.test.sh"
generalizes: [LESSON-571, LESSON-626]
supersedes: []
---

## What Happened

REQ-646 shipped `adlc_lesson_check`, a POSIX-sh validator for lesson frontmatter
that `/spec`, `/review` and `/architect` read as YAML. The first implementation
read each key's **first** occurrence; YAML readers keep the **last**. The Phase-5
security audit built a lesson with `evidence: BUG-123 ok` followed by a second
`evidence: >` block carrying `sk-…` and `/Users/brett/x` — rc 0, and the value a
reader would keep had never been scanned. The same shape recurred three more times
in the same review: a key spelled `evidence :` or `"evidence":` was invisible to
the duplicate count; an unindented flow continuation (`[REQ-123,` ↵ `ghp_…]`)
was never scanned; and `supersedes:[LESSON-034]` with no blank after the colon
was *ignored* by the validator while the `/review` reverse lookup *matched* it —
so a lesson that passed the check could switch off another lesson's escalation.

Each fix was the same move: define the key by the reader's grammar (exactly
`key:` plus a blank, once), reject every spelling variant and every continuation
the one-line reader cannot see, and scan every raw frontmatter line rather than
only recognised keys. The re-verify pass then found the next variant of the same
class, because the first fix had enumerated *some* reader rules, not the reader.

## Lesson

1. **Model the reader, not the format.** Before writing a validator for data a
   different program consumes, write down how *that* program parses it —
   duplicate keys (last wins), accepted key spellings, quoting, continuations,
   comment handling — and make the validator either implement those rules or
   reject the input when it cannot. A validator that reads a value the consumer
   will not read validates nothing.
2. **Fail closed on the unparseable, never fall through.** A line the validator
   does not recognise as a key is not "not a key"; it is a line the consumer may
   read differently. Reject it with the field named, so the repair loop can fix
   it, instead of letting it pass unseen.
3. **Scan the raw lines, then parse.** Run the dangerous-content checks (secrets,
   home paths) over every frontmatter line *before* key recognition, so a
   misspelt or duplicated key cannot carry a payload past the scan.
4. **Pin each reader rule with a positive and a negative case** in the same
   harness (LESSON-440), and when a review finds one instance of the class, hunt
   the siblings in the same pass — the second review found three.

## Why It Matters

The validator is the structural guard REQ-646 exists for (LESSON-012). A gap of
this class is silent in both directions: a secret or an identifying path is
committed and pushed with a green check, and a reader-visible `supersedes` can
disable a safety behaviour in `/review`. Both were reachable from the untrusted
delegate draft (LESSON-008). The fix cost one re-verify loop; found later, it
would have cost a leaked path in a shared lessons corpus.

## Applies When

- Writing any shell or script validator for YAML/TOML/JSON frontmatter, config
  files, or marker blocks that another tool parses (`/spec` retrieval, the lint,
  a workflow schema).
- Reviewing a validator: ask "what does the *consumer* do with a duplicate key,
  a quoted key, a continuation line, a comment?" for each, and look for the
  validator's answer.
- Extending `adlc_lesson_check` or writing its sibling for bugs/specs: keep the
  "reject what you cannot parse" posture rather than adding tolerant branches.
