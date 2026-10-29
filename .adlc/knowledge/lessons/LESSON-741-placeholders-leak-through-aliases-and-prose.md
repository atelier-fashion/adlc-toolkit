---
id: LESSON-741
title: "A placeholder hides a name only if nothing else in the same text names the same thing — aliases, product names, crate names and same-record prose all reverse it"
component: "tools/dataset/scrub"
domain: "privacy"
stack: ["python"]
concerns: ["privacy", "data-governance"]
tags: ["redaction", "placeholder", "pseudonymization", "denylist", "aliases"]
req: REQ-671
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-671 verify: the security re-check found crates/tetond/ published a few lines from consumer-repo-6 in BUG-224, BUG-228 and BUG-230, and the correctness re-check found REQ-262's **infrastructure** list header beside consumer-repo-5; fixed by DenyList aliases and record-level forcing in tools/dataset/scrub.py, then re-verified"
confidence: high
enforcement: test:tools/dataset/tests/test_dataset_scrub.py
generalizes: []
supersedes: []
---

## What Happened

REQ-671 maps each private repo to `consumer-repo-N`. Three reviews in a row found the
mapping reversible inside the output itself:

- The product name "Teton Code" stayed public while `teton-code` became
  `consumer-repo-6`, and 27 records showed both. The maintainer chose to scrub the
  product name too.
- After that, the daemon crate `tetond` still appeared in file paths next to the
  placeholder, because the alias `Teton` only matched as a whole word.
- A `repo-context` name kept as plain prose (`**infrastructure** (26 files)`) sat in the
  same record as `consumer-repo-5 (26, simplest)`.

## Lesson

Treat a placeholder as broken whenever any other token in the same published unit points
at the same thing.

- **List aliases with the name.** That means product, client and binary names, and
  crates, matched with separator variants (`-`, `_`, a space, nothing, typographic
  hyphens).
- **Force at record scope, not line scope.** Once a record contains the placeholder,
  replace every remaining occurrence of the name in that record, including plain prose.
- **Check the pair in the residue pass.** A name and its own placeholder in one record
  is a hit.
- **Don't call it anonymization.** A placeholder mapping in a public DenyList hides
  names from the dataset, but anyone with the repo can still recover the mapping.

## Why It Matters

Pseudonymization fails silently: every string-level check passes, and the reader puts
the two together. Each instance here passed the tests and the first review.

## Applies When

You replace identifiers with stable placeholders in text that will be published or
shared. That includes repo and customer names, people and hostnames.
