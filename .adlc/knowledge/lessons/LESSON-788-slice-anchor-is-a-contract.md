---
id: LESSON-788
title: "A test that evaluates a script between two markers makes those markers a contract: code added above one runs in the slice, with none of the script's earlier setup"
component: "adlc/install"
domain: "adlc"
stack: ["sh", "python"]
concerns: ["testing", "maintainability"]
tags: ["install-sh", "slice-test", "anchor", "set-u", "full-suite"]
req: REQ-663
created: 2026-11-01
updated: 2026-11-01
kind: domain
evidence: "REQ-663 final gate: tools/adlc/tests/test_config_scaffold_parity.py failed four cases with MIGRATE: unbound variable, because install.sh's migration dispatch sat above the slice's end anchor, the run section marker. Moving the block below that marker passed them, in commit 733514d. The focused runs before the gate had not included that file; test_install_shim.py, which ends its slice earlier, passed throughout."
confidence: high
enforcement: test:tools/adlc/tests/test_config_scaffold_parity.py
generalizes: []
supersedes: []
---

## What Happened

The migration needed the functions `install.sh` defines, so its dispatch went just before the main
body, under a section header of its own. `test_config_scaffold_parity.py` evaluates everything from
`note()` to the `# --- run ---` marker, so the new block ran inside that slice, where the argument
parsing above it never happened, and `set -u` stopped it. Only the full suite showed this, after
every focused run had passed.

## Lesson

Before adding code near a section marker in `install.sh`, grep the tests for that marker: a slice
test turns a comment into an interface. New top-level code that reads the script's own variables
goes below the slice's end anchor. After changing a script that tests slice, run the whole suite,
not the tests named after your feature.

## Why It Matters

The failure names a variable the slice never set, which reads like a bug in the test. And the
structural rules these suites hold only fire in a full run, so a focused green run proves little
about them.

## Applies When

Editing `install.sh` or any script evaluated by slice in a test, or adding top-level code beside a
`# --- section ---` marker.
