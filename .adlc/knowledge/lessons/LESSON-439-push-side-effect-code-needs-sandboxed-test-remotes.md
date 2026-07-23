---
id: LESSON-439
title: "Code whose happy path pushes to origin needs sandbox-remote test isolation — an un-cd'd test case will push to the real remote"
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "git"]
concerns: ["testing", "safety"]
tags: ["test-isolation", "side-effects", "bare-remote", "fixtures", "push", "sandbox"]
req: REQ-546
created: 2026-07-23
updated: 2026-07-23
---

## What Happened

Before REQ-546, `adlc_alloc_id` was read-only toward the network (ls-remote,
gh api reads), so a test case that forgot to isolate its cwd merely read the
real remote. The reservation mechanism changed the contract: allocation now
**pushes** to the cwd-resolved `origin`. Any test in the partials harness
that exercised allocation without first `cd`-ing into a sandbox repo would
have pushed real reservation refs to the toolkit's actual GitHub remote when
run via `run.sh`. The test matrix was built so every case constructs its own
throwaway clone wired to a **local bare repository as `origin`** (file-path
remote), runs the allocation inside it, and asserts against that bare
remote's refs — plus `GIT_TERMINAL_PROMPT=0` so no case can hang on
credentials. Policy cases install a denying pre-receive hook on the local
bare remote; race cases run two clones against one bare remote.

## Lesson

The moment a function gains a push side effect, its entire existing test
suite inherits a new hazard: environment-relative state (cwd, resolved
`origin`) now determines whether tests mutate production. Treat "unit under
test writes to a remote" as a fixture-design requirement — every case gets
its own local bare remote and its own cwd sandbox, asserted against the bare
side — and audit PRE-EXISTING cases at the moment the side effect is
introduced, not just the new ones. Local bare remotes also make the
hard-to-reach failure modes (hook denial, creation races) cheaply
constructible, which is what made the LESSON-438 marker-pinning tests
possible.

## Why It Matters

A test suite that pushes to the real remote pollutes the very namespace the
mechanism manages (phantom reservations burning real id numbers), does so
only on machines with push credentials — i.e., the maintainer's — and looks
green while doing it. Side-effect leaks from tests are silent until the
production surface shows unexplained artifacts.

## Applies When

- Adding a push/write side effect to any previously read-only shell or
  Python path that tests exercise.
- Designing partials-harness cases for network-adjacent code: default to a
  per-case sandbox cwd + local bare `origin`, never the checkout's own repo.
