---
id: LESSON-846
title: "With git stubbed, the id allocator cannot find the main worktree and walks every repo under `/`: a test that reaches it sets ADLC_REPOS_ROOT"
component: "adlc/partials/id-alloc"
domain: "adlc"
stack: ["sh", "python", "git"]
concerns: ["testing", "performance"]
tags: ["id-alloc", "repos-root", "recording-stubs", "test-isolation", "adlc-repos-root"]
req: REQ-682
created: 2026-11-09
updated: 2026-11-09
kind: domain
evidence: "REQ-682 TASK-247: test_exec_reach.py::test_real_tree_reach_matches_golden took 127.5s, 124s of it in wrapup/SKILL.md#8 (adlc_alloc_id lesson), which printed `LESSON high-water derived from 0 participating repo(s) under '/'`; with ADLC_REPOS_ROOT set to the test's tmp_path the test took 3.9s."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-682's dynamic reach audit runs every runner fence with recording stubs for `git`, `gh`,
`az` and `curl` first on `PATH`. The close-out's lesson-allocation fence calls
`adlc_alloc_id`, which derives the repo set to scan from the main worktree's parent. With `git`
stubbed, that lookup returns nothing, the root fell back to `/`, and the allocator walked the
whole filesystem for participating repos: two minutes for one fence, and a scan of the
operator's disk from inside a test.

## Lesson

A stubbed `git` changes more than what a test records: every partial that asks git where it is
falls back. Before stubbing it, find the partials that resolve a location through git (the id
allocator and recheck resolve the main worktree, then its parent) and pin the location the
fallback would otherwise widen: `ADLC_REPOS_ROOT=<tmp>` for the allocator. Treat a slow stubbed
test as a sign a fallback reached somewhere it should not.

## Why It Matters

An unbounded walk is slow, and it makes a sandboxed test read the operator's real directories,
which the conftest's throwaway `HOME` does not prevent.

## Applies When

Writing a test that runs `adlc_alloc_id`, `adlc_recheck_id`, or any fence or partial that
reaches them, with `git` stubbed or outside a real repository.
