---
name: reflect
description: Post-implementation self-review — catch issues before /review
argument-hint: Optional REQ-xxx ID or branch name to scope the reflection
---

# /reflect — Post-Implementation Reflection

You are performing a self-review of recently implemented code to catch issues before the formal `/review` step. This is a fast, honest assessment of your own work.

## Ethos

!`cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Recent changes: !`git diff main --stat 2>/dev/null || echo "No diff available"`

**Context files loaded on demand**: `.adlc/context/conventions.md` and `.adlc/context/architecture.md` are loaded by Step 1 below — **skip the Read if they are already in the current conversation** (e.g., when invoked from `/proceed`, which preloads them at Phase 0).

## Input

Scope: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/context/conventions.md` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first to set up conventions."

## Instructions

### Step 1: Determine Scope
1. If given a REQ ID, find the associated branch and review its changes
2. If given a branch name, review all changes on that branch vs `main`
3. If no argument, review all changes on the current branch vs `main`
4. Get the full diff: `git diff main...HEAD`
5. **Context files**: if `.adlc/context/conventions.md` and `.adlc/context/architecture.md` are NOT already in your conversation context, Read them now. Otherwise skip — they're already loaded.

### Step 2: Read All Changed Files
Read the complete current version of every changed file (not just the diff) to understand full context.

### Step 2.5: Check Lessons Learned
**Grep first, read only matches**: use the Grep tool on `.adlc/knowledge/lessons/` with patterns like `component:.*<affected-area>` or `domain:.*<domain>` matching the files changed in this implementation (e.g., if touching `api/src/services/auth`, grep for `component:.*API/auth` or `domain:.*API`). Then Read ONLY the matched files. Do NOT read all lessons. Check whether any known pitfalls apply to the current changes. Flag any matches as findings in Step 4.

### Step 3: Self-Review Checklist
Evaluate the implementation against each category. Be honest — the goal is to catch problems now rather than in `/review`.

#### Correctness
- [ ] Does the code do what the requirement/task specifies?
- [ ] Are all acceptance criteria met?
- [ ] Are edge cases handled (empty inputs, nulls, boundaries)?
- [ ] Are error paths handled properly?
- [ ] Any race conditions or async issues?

#### Convention Compliance
- [ ] Follows naming conventions (camelCase JS, PascalCase Swift types, kebab-case URLs)
- [ ] Uses `logger` not `console.log`
- [ ] Config values in `config.js`, not hardcoded
- [ ] API responses follow `{ error, message }` format for errors
- [ ] CodingKeys for snake_case API to camelCase Swift mapping
- [ ] MVVM with @Observable pattern on iOS side

#### Architecture
- [ ] Proper layering: routes -> services -> repositories
- [ ] No business logic in route handlers
- [ ] No direct Firestore access from routes
- [ ] ViewModels receive dependencies via init (DI), not singletons
- [ ] Barrel re-exports maintained if files were split

#### Testing
- [ ] New code has corresponding tests
- [ ] Tests cover error/failure paths, not just happy paths
- [ ] Mock files include all new exports
- [ ] No brittle assertions (exact string matching on prompts, etc.)
- [ ] Tests are deterministic (no flaky timing, no external dependencies)

#### Completeness
- [ ] No TODOs or FIXMEs left behind
- [ ] No commented-out code
- [ ] No debug logging accidentally left in
- [ ] All import paths resolve correctly
- [ ] If files were added, they're included in the Xcode project (iOS)

### Step 4: Report Findings
Present findings in two sections:

#### Issues Found
List each issue with:
- **Severity**: Critical / Major / Minor
- **File**: file path and line number
- **Issue**: what's wrong
- **Fix**: what to do about it

#### Clean Areas
Briefly note areas that look good (1-2 sentences) so the user knows what was checked.

### Step 5: Questions for the User
Review the implementation holistically and surface any questions or uncertainties, such as:
- **Ambiguous requirements**: Anything in the spec that could be interpreted multiple ways — how did you interpret it, and is that correct?
- **Design tradeoffs**: Decisions where there were multiple reasonable approaches — should the user weigh in?
- **Assumptions made**: Any assumptions baked into the implementation that weren't explicitly stated in the requirement
- **Edge cases deferred**: Scenarios you noticed but chose not to handle — should they be addressed?
- **UX/behavioral questions**: "When X happens, should the app do Y or Z?"

Present these as a numbered list. If there are no questions, state that explicitly. Do not proceed past this step until the user has answered — their responses may change what needs to be fixed.

### Step 6: Fix or Defer
1. If Critical issues are found, fix them immediately
2. If Major issues are found, ask the user whether to fix now or note for `/review`
3. Minor issues can be listed for the user to decide
4. After fixes, re-run tests to verify nothing broke

### Step 7: Recommend Next Action
- If no issues or only minor ones: "Ready for `/review`"
- If fixes were applied: "Fixes applied. Re-run `/reflect` to verify, or proceed to `/review`"
- If blockers remain: "Address these issues before `/review`"
