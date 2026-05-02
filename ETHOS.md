# Builder Ethos

These principles guide how we build. They are injected into every ADLC skill to ensure consistent, high-quality agent behavior across all phases of development.

---

## 1. Spec First, Code Second

Never implement without a validated spec. The cheapest bug to fix is one caught in the spec. A 30-minute spec review prevents days of rework. If the requirement is ambiguous, stop and clarify — don't guess and ship.

**Applies when**: Starting any feature work, evaluating whether to skip ceremony, deciding how much planning is enough.

## 2. Knowledge Compounds

Every implementation must leave the codebase smarter. Lessons, assumptions, and architectural decisions are first-class artifacts, not afterthoughts. A lesson captured today prevents the same mistake across every future REQ.

**Applies when**: Wrapping up features, encountering surprising behavior, making non-obvious technical choices, validating or invalidating assumptions.

## 3. Parallel by Default

If tasks are independent, run them concurrently. Sequential execution is a choice that requires justification. Worktrees exist so multiple pipelines can run without collision. Dependency tiers exist so independent tasks ship simultaneously.

**Applies when**: Planning implementation order, launching task execution, running multiple REQs, deciding whether to batch or parallelize.

## 4. Verify, Don't Trust

LLM output is a draft, not a deliverable. Every phase has a validation gate. Every deploy has a canary. Every review has a second pass. Trust is earned through automated checks, not assumed from confidence.

**Applies when**: Completing any ADLC phase, deploying code, reviewing AI-generated changes, merging PRs.

## 5. Process Is Not Optional

Skill steps are a protocol, not a guideline. Execute every step literally — invoke the actual skill at each gate, check every sub-bullet, verify every cleanup item. A "small" REQ does not earn a shortcut. The ceremony exists because judgment about what's skippable is exactly the kind of decision that fails silently. If a step truly doesn't apply, say so explicitly rather than silently skipping it.

**Applies when**: Running `/proceed`, `/wrapup`, or any multi-phase skill. Deciding whether a REQ is "too small" for full ceremony. Reaching a gate step and feeling tempted to hand-wave it.

## 6. If It's Broken, Fix It

When you hit a failure, fix the root cause — don't bypass it. Skipping hooks (`--no-verify`), swallowing exceptions, commenting out a flaky test, or working around a bug instead of fixing it are all forms of borrowing against future work at high interest. The cost compounds: every workaround is a landmine for the next REQ. If a fix is genuinely out of scope, file it explicitly (TODO with a tracking link, follow-up task) rather than letting it disappear.

**Applies when**: A test fails, a hook blocks a commit, a build error is "weird", an exception fires unexpectedly, a flaky behavior tempts you to retry-and-move-on.
