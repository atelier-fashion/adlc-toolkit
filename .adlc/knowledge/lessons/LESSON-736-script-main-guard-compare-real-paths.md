---
id: LESSON-736
title: "An ES-module 'run when invoked directly' guard that compares path strings silently does nothing under a symlinked path, so a --check gate exits 0 having checked nothing"
component: "adlc/space"
domain: "adlc"
stack: ["javascript", "node"]
concerns: ["correctness", "false-negative", "release-gates"]
tags: ["esm-main-guard", "import-meta-url", "symlink", "realpath", "drift-check", "vacuous-pass"]
req: REQ-670
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-670 Phase 5 architecture review: space/build.mjs guarded main() with resolve(process.argv[1]) === fileURLToPath(import.meta.url). Run as node <copy under $TMPDIR>/space/build.mjs --check with VERSION changed, it exited 0 with no output (macOS /var is a symlink to /private/var); the same drift with --root exited 1 naming version. Fixed with realpathSync on both sides, pinned by space/tests/build.test.js test 'the CLI runs through a symlinked path and still fails on drift', merged in 2724699."
confidence: high
enforcement: "test:space/tests/build.test.js"
generalizes: []
supersedes: []
---

## What Happened

REQ-670's `space/build.mjs` is a release gate: `--check` must exit 1 when the
Space's generated data has drifted from the toolkit. Its "am I the entry point"
guard compared `path.resolve(process.argv[1])` with `fileURLToPath(import.meta.url)`.
Node reports `import.meta.url` as the real path, and `resolve` does not follow
symlinks. So when the script was invoked through a symlinked directory, the strings
differed, `main()` never ran, and the process exited 0. That covers macOS's `/var`
→ `/private/var`, a checkout under a symlinked home, and the toolkit's own symlink
install route. A drifted tree passed the gate. Every unit test imported `main()`
directly, so none of them could see it.

## Lesson

A CLI's own entry-point guard is part of its gate. Compare
`fs.realpathSync(process.argv[1])` with `fs.realpathSync(fileURLToPath(import.meta.url))`.
If resolving throws, fall back to the plain comparison rather than returning false.
Test the CLI by **spawning** it through a symlinked path against a mutated input, and
assert the non-zero exit. A gate that can exit 0 without running is a vacuous pass,
the same class the vacuous-verification rule blocks (REQ-595).

## Why It Matters

The failure is silent and lands on exactly the people who run the gate. A release
checklist that says "run `--check`" reports green while checking nothing. Unit tests
that call `main()` in-process never exercise the guard.

## Applies When

You write a Node ES-module script that runs only when invoked directly
(`import.meta.url` versus `process.argv[1]`), or any script whose "am I main" check
compares paths. It matters most when the script is a check or gate, and when it can
run from a temp directory, a worktree or a symlinked install.
