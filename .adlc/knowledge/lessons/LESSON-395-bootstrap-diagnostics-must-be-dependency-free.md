---
id: LESSON-395
title: "A bootstrap diagnostic cannot depend on anything it diagnoses — adlc doctor is pure stdlib because it runs before the machine is set up"
component: "adlc/toolkit"
domain: "adlc"
stack: ["python"]
concerns: ["onboarding", "portability"]
tags: ["doctor", "bootstrap", "stdlib", "dependencies", "preflight", "install"]
req: REQ-519
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

REQ-519's `adlc doctor` exists to tell a fresh machine what's missing — which
means it must run *on* a fresh machine. An early design sketch had doctor
import from the delegation venv's installed packages; but the venv only
exists after the (opt-in) delegation install, so doctor would crash on
exactly the machines it serves. ADR-1 made doctor pure Python stdlib, probing
everything else (gh, az, venv, shims, counters) as external state via
subprocess/filesystem checks.

## Lesson

Anything whose job is "check whether X is set up" must have a dependency
closure that excludes X — transitively. The constraint recurs for every
future bootstrap-adjacent tool: installers, doctors, `adlc renumber` on a
machine without the venv, pre-flight probes in skills. The test for it is
brutal and cheap: run the diagnostic in a sandbox HOME with nothing installed
and assert it *reports* the gaps rather than crashing on them.

## Why It Matters

A diagnostic that requires setup to diagnose setup inverts its own purpose,
and the failure is maximally hostile to the exact audience the portability
initiative targets: the new adopter on a clean machine, who gets a traceback
instead of a checklist.
