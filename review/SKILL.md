---
name: review
description: Multi-agent code review covering correctness, quality, architecture, test coverage, and security
argument-hint: Optional file paths, branch name, or REQ/TASK ID to scope the review
---

# /review — Multi-Agent Code Review

You are performing a thorough code review of recent changes using multiple specialized review agents.

This skill is the **pre-push ADLC review gate**. It runs 5 specialized review agents in parallel, covering the same dimensions the CI `llm-review` workflow would cover if it ran (correctness, conventions, test coverage, security) plus an architecture dimension the CI workflow doesn't have. Running this before pushing means the ADLC gate catches issues regardless of whether the CI layer is available — CI-layer LLM reviews can be blocked (billing, infra, outages) and must not become the sole safety net.

## Ethos

!`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo No ethos found — run /init to vendor .adlc/ETHOS.md`

## Context

- Current branch: !`git branch --show-current || echo Not a git repo`
- Committed changes vs main: !`git diff-tree --stat -r main HEAD || echo No diff available`
- Uncommitted changes: !`git status --short`

**Context files loaded on demand**: `.adlc/context/conventions.md` and recent lessons are loaded by Step 1 below — **skip the Reads if they are already in the current conversation** (e.g., when invoked from `/proceed`, which preloads `conventions.md` at Phase 0).

## Input

Scope: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/context/conventions.md` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first to set up conventions."

## Instructions

### Step 1: Determine Review Scope and Load Context
1. If given specific file paths, review those files
2. If given a branch name, review all changes on that branch vs `main`
3. If given a REQ/TASK ID, find the associated branch and review its changes
4. If no argument, review all uncommitted changes + commits on the current branch vs `main`
5. Get the full diff: `git diff main...HEAD` (or `git diff` for uncommitted changes)
6. **Conventions**: if `.adlc/context/conventions.md` is NOT already in your conversation context, Read it now. Otherwise skip — it's already loaded.
7. **Relevant lessons** (mirrors the spirit of `llm-review.yml`, but relevance-ranked instead of time-ranked):
   a. Derive the set of touched **components** from the diff. Components are inferred from file paths — e.g. `api/auth/*` → `API/auth`, `app/Sources/Views/*.swift` → `iOS/SwiftUI`, `infrastructure/terraform/*` → `infra/terraform`. Produce a short list of plausible `component` values and a broader list of `domain` values (e.g. `API`, `iOS`, `infra`).
   b. Glob `.adlc/knowledge/lessons/*.md` and read each file's frontmatter (`domain`, `component`, `tags`, `confidence`, `supersedes`). Keep lessons where `component` matches any touched component exactly, OR where `domain` matches any touched domain AND `component` is a prefix of a touched component, OR where any tag matches a touched component/domain. This is the **relevance set**. `confidence` and `supersedes` play no part in relevance — record them next to each lesson's id for Step 4. A lesson's own `supersedes` names what *it* replaces; whether *it* has been replaced is Step 4's reverse lookup, run only for lessons a finding matched.
   c. If the relevance set has fewer than 5 entries, top it up with the most recently modified lessons from `.adlc/knowledge/lessons/` (the previous time-based heuristic) until the set has up to 10 entries. This keeps small or cross-cutting diffs from losing context entirely.
   d. Cap the final list at 15 lessons. Read their bodies in full.
   e. Pass the content of every selected lesson as context to every review agent in Step 3. When a finding later matches one of these lessons, cite its `id` explicitly (Step 4 uses this to elevate severity).
   f. **Lesson files this diff changes.** From the item 5 diff, list the `.adlc/knowledge/lessons/LESSON-*.md` paths it adds or modifies (`--name-only` on the same diff, plus untracked lesson files when the scope includes uncommitted changes). Step 4 ignores the `confidence` and `supersedes` those files carry: a change under review must not switch off its own escalation.
   **Fallback**: if any lesson has no `component` / `domain` / `tags` frontmatter (legacy file), fall back to reading its title + first paragraph and include it only if the title contains any touched domain or component substring. Do not skip it silently — it may be load-bearing.

### Step 2: Read All Changed Files
Read the complete current version of every changed file (not just the diff) to understand full context.

### Step 3: Launch Review Agents
Launch **5 formal review agents in parallel** using the Agent tool. Each agent is defined in `~/.claude/agents/` with its full checklist, model selection, and tool restrictions. Running in parallel minimizes wall-clock time.

1. **correctness-reviewer** agent — provide it the list of changed files, the full diff, `conventions.md` content, and recent lessons. Focus: logic errors, null risks, race conditions, edge cases, concurrency bugs. Tell it: "Report findings only. Do not apply fixes."
2. **quality-reviewer** agent — same inputs. Focus: naming, convention compliance, code duplication, complexity, maintainability. Tell it: "Report findings only. Do not apply fixes."
3. **architecture-reviewer** agent — same inputs plus `architecture.md` content. Focus: layering, separation of concerns, API contracts, module boundaries, scope discipline. Tell it: "Report findings only. Do not apply fixes."
4. **test-auditor** agent — same inputs. Focus: test coverage gaps for the changed code, mock completeness, edge case coverage, test isolation, determinism. Tell it: "Audit test coverage only for the diff under review. Report findings only. Do not apply fixes."
5. **security-auditor** agent — same inputs. Focus: input validation, authentication/authorization gaps, data exposure (PII, secrets), injection risks, dependency issues, rate limiting. Tell it: "Audit security posture only for the diff under review. Report findings only. Do not apply fixes."

Each agent returns structured findings with severity (Critical/Major/Minor/Nit), file path, line number, and suggested fix.

**Gate rule** (mirrors `llm-review.yml`): if ANY agent reports a `Critical` finding, the review gate FAILS and the changes are not ready to merge. Fix critical findings before proceeding to push. Major findings should typically be fixed before merge but can be escalated to the user for judgment calls.

### Step 4: Consolidate Findings
1. Collect results from all 5 agents
2. Deduplicate overlapping findings
3. Categorize by severity:
   - **Critical**: Must fix before merge (bugs, security, data loss, test gaps that hide regressions)
   - **Major**: Should fix before merge (convention violations, missing tests, architectural smells)
   - **Minor**: Nice to fix (style, naming, minor improvements)
   - **Nit**: Optional suggestions
4. Cross-reference findings against the loaded recent lessons — if a finding matches a known pitfall, escalate its severity by one level (e.g., a Minor finding that matches a prior LESSON becomes a Major). Flag this explicitly in the report.
   **Escalation is gated on the matched lesson's standing** (REQ-646 BR-6). It fires unless the matched lesson has `confidence: low` or another lesson supersedes it (the lookup below). Only the value `low` counts: `medium`, `high`, an empty value and any value outside the enum all behave as absent. A matched lesson with absent `confidence` escalates as today — legacy lessons predate the field, and absence is not `low`. Otherwise the finding keeps its severity, still cites the lesson id, and the report carries the matching annotation verbatim:
   - `confidence: low` → `(matched LESSON-xxx, confidence low — not escalated)`
   - named in another lesson's `supersedes` → `(matched LESSON-xxx, superseded by LESSON-yyy — not escalated)`

   When both apply, use the superseded annotation — it names the lesson to read instead. This does not switch escalation off wholesale: a lesson backed by a finding-plus-fix or a reproduce-plus-fix is `medium`/`high` and still escalates (the capture prompt's contrast rule, REQ-646 BR-4).

   **Superseded lookup** (REQ-646 ADR-6) — run it here, lazily: only for a lesson a finding matched, never for all 15 selected in Step 1. The superseding lesson is usually *not* in the selected set, so loaded frontmatter cannot answer this; run one corpus-wide reverse lookup per matched lesson. Substitute the lesson's id for `<id>` only after it matches `^LESSON-[0-9]{3,6}$` — an id that does not match is skipped, never substituted — and the `case` re-checks it before anything uses it:

   ```sh
   ID='<id>'
   case "$ID" in
     LESSON-[0-9][0-9][0-9]|LESSON-[0-9][0-9][0-9][0-9]|LESSON-[0-9][0-9][0-9][0-9][0-9]|LESSON-[0-9][0-9][0-9][0-9][0-9][0-9])
       find .adlc/knowledge/lessons -maxdepth 1 -type f -name 'LESSON-*.md' -exec awk -v id="$ID" 'FNR==1{s=0;skip=0;c=0;sub(/^\357\273\277/,"")} {sub(/\r$/,"")} skip{next} s==0&&/^[ \t]*$/{next} s==0&&/^<!--/{c=1} c{ if(/-->/){c=0}; next } s==0&&!/^---$/{skip=1;next} s<2&&/^---$/{s++;next} s==1&&$(0)~("^supersedes:[ \t][^#]*" id "([^0-9]|$)"){print FILENAME;skip=1}' {} + 2>/dev/null ;;
     *) echo "superseded lookup: $ID is not a LESSON-nnn id — skipped" >&2 ;;
   esac
   ```

   Each printed path is a superseding lesson; its id is the `LESSON-<digits>` prefix of the basename. Ignore a hit on the lesson's own file, and a hit on a file Step 1 item 7f listed. Every remaining hit is a `superseded by` id, comma-separated; no output means not superseded. The id reaches `awk` as data (`-v`), so the `case` guards the only place it is substituted. The program is single-quoted and reads only the frontmatter block, found the way `adlc_lesson_check` finds it: a leading BOM and each line's trailing CR are dropped, blank lines and HTML comments are skipped, and the block opens only when the first other line is `---` — a file that opens with anything else, such as a legacy lesson whose `---` lines are horizontal rules in its body, is skipped whole. The match needs a blank after `supersedes:` (the one key spelling the check accepts), and `[^#]*` stops at a trailing `# comment`, so neither a body line nor a comment that mentions the id is a hit. `2>/dev/null` keeps a missing lessons directory quiet — no output, so not superseded. `-exec … {} +` runs nothing when no file matches, where GNU `xargs` would run its command once on empty input; the quoted `-name` never hands the shell an unmatched glob (zsh aborts on one — LESSON-335); and `([^0-9]|$)` stops `LESSON-40` matching `LESSON-404` without a word-boundary escape, which BSD tools silently ignore (LESSON-013). On a provenance-classifying harness (BUG-228), use Claude's own Grep tool with the regex `^supersedes:[ \t][^#]*LESSON-<id>([^0-9]|$)`, `<id>` there being the digits alone (path `.adlc/knowledge/lessons`, glob `LESSON-*.md`, with line numbers), and keep only the hits inside their file's frontmatter block — the block that opens at the file's first non-blank, non-comment line.

   **A lesson file this diff changes carries no standing** (Step 1 item 7f). If the matched lesson's own file is on that list, treat its `confidence` as absent; a superseding hit on that list does not count. When that is what kept an exemption from applying, the finding escalates as today and the report says so: `(matched LESSON-xxx, exemption ignored — lesson changed in this diff)`.

### Step 5: Present Review
Display findings organized by file, then by severity within each file. Include a dimension summary at the top so the user can see which of the 5 dimensions have issues at a glance:

```
## Dimension Summary

| Dimension | Critical | Major | Minor | Nit | Gate |
|---|---|---|---|---|---|
| Correctness | 0 | 1 | 2 | 0 | PASS |
| Quality | 0 | 0 | 3 | 1 | PASS |
| Architecture | 0 | 2 | 0 | 0 | PASS |
| Test Coverage | 0 | 0 | 1 | 0 | PASS |
| Security | 0 | 0 | 0 | 0 | PASS |

**Overall gate: PASS / FAIL**

## file/path.js

### Critical
- Line XX: description of issue

### Major
- Line XX: description of issue
```

### Step 6: Summary
1. Overall gate: PASS (ready to merge) / FAIL (fix criticals first) / RESHAPE (significant rework needed)
2. Count of issues by severity and by dimension
3. Top 3 most important things to address
4. Any findings that matched recent lessons (elevated-severity items), and the matches Step 4 did not escalate, each with its `(matched LESSON-xxx, … — not escalated)` annotation, plus any match whose exemption Step 4 ignored because the diff changes the lesson file, with its `(matched LESSON-xxx, exemption ignored — lesson changed in this diff)` annotation
5. If changes look good, say so clearly — an empty review is a valid result for small, well-scoped changes
