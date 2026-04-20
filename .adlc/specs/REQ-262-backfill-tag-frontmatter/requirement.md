---
id: REQ-262
title: "Backfill tag frontmatter across 4 consumer repos"
status: complete
deployable: false
created: 2026-04-20
updated: 2026-04-20
component: "adlc/backfill"
domain: "adlc"
stack: ["markdown", "bash", "claude-skills"]
concerns: ["knowledge-compounding", "retrieval", "data-migration", "developer-experience"]
tags: ["backfill", "tagging", "legacy-migration", "multi-repo", "retrieval-enablement"]
---

## Description

Retroactively populate the unified retrieval tag frontmatter (`component`, `domain`, `stack`, `concerns`, `tags`) on ~468 existing artifacts across four consumer repos so the new `/spec` retriever (shipped in REQ-258, toolkit PR #12) produces meaningful results against pre-existing `.adlc/` corpora. Without backfill, every `/spec` invocation in these repos falls through to the cold-start path; the retriever cannot reach content the repos have already accumulated.

**Why this REQ exists.** REQ-258 shipped the retriever and schema but kept migration explicitly out of scope (lazy migration policy: authors retag on next touch). In practice, waiting for organic retagging means the retriever is functionally cold-start for months or longer in the highest-value repos. The user has authorized a bulk backfill to front-load the value.

**Why four repos, not one.** The original scoping sized atelier-fashion at ~290 files. A cross-repo survey (REQ-258 §7.5 follow-up) revealed 468 in-scope files distributed across four consumer repos: atelier-fashion (306), atelier-web (82), admin-api (54), infrastructure (26). Any repo left un-backfilled degrades its own `/spec` invocations without benefiting from the retriever REQ-258 shipped.

**What "in scope" means here.** Only corpora the REQ-258 retriever reads: `.adlc/knowledge/lessons/`, `.adlc/specs/*/requirement.md`, `.adlc/bugs/*.md`. The `.adlc/knowledge/decisions/` and `.adlc/knowledge/assumptions/` directories are explicitly NOT retrieved by REQ-258 (see REQ-258 Out of Scope), so they are deferred to a separate follow-up REQ if/when those corpora become retrievable.

## System Model

_This is an operational/data-migration REQ. The "entities" are the existing markdown files being backfilled; the "events" are the tagging and commit operations._

### Entities (files to backfill)

| Corpus | Location (relative to repo root) | atelier-fashion | atelier-web | admin-api | infrastructure | Lesson format |
|--------|---------------------------------|----|----|----|----|----|
| Lessons | `.adlc/knowledge/lessons/*.md` | 136 | 36 | 27 | 13 | see below |
| Specs | `.adlc/specs/*/requirement.md` | 160 | 45 | 27 | 13 | YAML |
| Bugs | `.adlc/bugs/*.md` | 10 | 1 | 0 | 0 | YAML |
| **Subtotal per repo** | | **306** | **82** | **54** | **26** | |

**Total in-scope: 468 files.** Format split:
- **Tier 1 (clean YAML frontmatter — just add tag fields)**: 305 files — all specs, all bugs, lessons in atelier-web and infrastructure.
- **Tier 3 (legacy non-frontmatter lesson format — wrap body in YAML + tag)**: 163 files — lessons in atelier-fashion (136) and admin-api (27).

### Tag schema applied to each file

Per REQ-258 BR-7 and the templates already refreshed in the consumer repos (PRs #488, #54, #58, #35, all merged), each backfilled file receives these frontmatter fields:

| Field | Type | Semantics |
|---|---|---|
| `component` | string (single) | narrow area, e.g. `"API/auth"`, `"iOS/SwiftUI"`, `"infra/terraform"` |
| `domain` | string (single) | broad area, e.g. `"auth"`, `"payments"`, `"ui"`, `"adlc"` |
| `stack` | string[] | tech layers touched, e.g. `["express", "firestore"]` |
| `concerns` | string[] | cross-cutting dimensions, e.g. `["security", "performance", "a11y"]` |
| `tags` | string[] | free-form keywords from the doc's content |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `file_read` | Agent reads doc body to infer tag values | doc path + current frontmatter + first N lines of body |
| `tags_proposed` | Agent proposes values for 5 dimensions | query object |
| `frontmatter_updated` | Tags written to file | modified file |
| `corpus_commit` | All files in one corpus-tier of one repo committed | single commit per tier per repo |
| `repo_pr_opened` | All tiers of one repo committed and pushed | one PR per repo |
| `repo_pr_merged` | Review + merge | repo main advances |

## Business Rules

_User-locked decisions from the REQ-258 planning conversation. These are non-negotiable._

- [ ] BR-1: **Per-corpus commits.** Each corpus tier in each repo gets its own commit. Commit messages: `chore(adlc): backfill tags for <corpus> [REQ-262]`. Example: one commit for atelier-fashion specs, one for atelier-fashion bugs, one for atelier-fashion lessons.
- [ ] BR-2: **Conservative tagging.** When the agent cannot infer a tag value with high confidence from the file's content, leave that field empty (`""` for scalars, `[]` for arrays) rather than guess. False positives pollute retrieval; empty fields fall through to cold-start or foundational-floor semantics which are safe.
- [ ] BR-3: **Legacy lesson conversion — insert-only, don't restructure.** Legacy lessons (those without YAML frontmatter) are backfilled by PREPENDING a `---` frontmatter block at the top of the file, not by restructuring existing body content. The body stays byte-for-byte unchanged below the inserted frontmatter. (Legacy lessons in atelier-fashion and admin-api were authored as plain markdown starting with `# Title`; the fix is to wrap them, not rewrite them.)
- [ ] BR-4: **All 4 repos in scope**, in the suggested order: atelier-web (82, simplest — pure YAML, low complexity) → infrastructure (26, simplest) → admin-api (54, includes Tier 3) → atelier-fashion (306, highest volume + Tier 3). Rationale: validate workflow on easy repos first; tackle atelier-fashion after the pattern is proven.
- [ ] BR-5: **Assumption and decision corpora are explicitly out of scope.** `.adlc/knowledge/assumptions/` (6 files in atelier-fashion) and `.adlc/knowledge/decisions/` (2 files in atelier-fashion) are NOT backfilled by this REQ because REQ-258's retriever does not read them. A separate REQ handles those corpora when/if they become retrievable.
- [ ] BR-6: **One PR per repo.** Each repo gets a single PR containing all tier commits for that repo. Four PRs total. Do NOT combine multiple repos into one PR.
- [ ] BR-7: **Preserve existing frontmatter.** Only ADD the 5 tag fields. Do NOT modify existing fields (`id`, `title`, `status`, `severity`, `created`, `req`, etc.). Do NOT re-order existing fields. Insertion point for new fields: immediately before the closing `---` of the frontmatter block.
- [ ] BR-8: **Use project-local taxonomy.** Before tagging each repo, read that repo's `.adlc/context/taxonomy.md` (scaffolded by the REQ-258 schema-refresh PRs, now merged). Propose tag values consistent with the taxonomy's canonical vocabulary. If a file's subject isn't clearly covered by the taxonomy, use `tags` (free-form) rather than force-fit a `component` or `domain`.
- [ ] BR-9: **Spot-check per tier.** Before committing a tier, read 3 random files in that tier and confirm the proposed tags are reasonable. If multiple tags are obviously wrong, pause and recalibrate the tagging prompt before continuing.
- [ ] BR-10: **Cold-start-safe outputs.** Files with no clear area signal get empty tag fields. Specs/bugs with no tags will score 0 in retrieval and filter out — that's correct behavior. Lessons with no tags get the foundational floor (+1) per REQ-258 BR-1, surfacing them only as last-resort cross-cutting context.
- [ ] BR-11: **No re-ordering of template fields.** Files created from pre-schema templates may have field orders that differ from the current templates. Preserve whatever order exists; the REQ-258 retriever parses by field name, not position.
- [ ] BR-12: **`updated` date is updated.** For every backfilled file, set `updated:` to the backfill date (`2026-04-20` or whenever the commit lands). `created:` is preserved unchanged. This lets the REQ-258 tiebreak (effective_date DESC) treat freshly backfilled files appropriately.

## Acceptance Criteria

- [ ] AC-1: All 468 in-scope files contain the 5 tag frontmatter fields (`component`, `domain`, `stack`, `concerns`, `tags`). Verifiable by grep: every target file matches `^(component|domain|stack|concerns|tags):` five times in the frontmatter block.
- [ ] AC-2: No legacy lesson is left without a YAML frontmatter block. After backfill, every `.adlc/knowledge/lessons/*.md` file starts with `---` on line 1 (or line 1-after-a-preserved-html-comment-header per the lesson template's filename-convention note).
- [ ] AC-3: Per-corpus commit discipline is observed — `git log` in each repo shows discrete commits titled `chore(adlc): backfill tags for <corpus> [REQ-262]` (one per corpus per repo).
- [ ] AC-4: All 4 repos have one open-and-merged PR titled `chore(adlc): backfill tag frontmatter [REQ-262]` (or similar) with per-corpus commits visible in the history.
- [ ] AC-5: Running `/spec "test feature"` in any of the 4 repos with a reasonable tag query (e.g. `component: API/auth`) produces a non-empty Retrieved Context section listing actual backfilled documents. Verifiable via one dogfood invocation per repo.
- [ ] AC-6: Sample verification — pick 5 random backfilled files per repo and confirm the tag values look correct for the content (not false positives, not wildly off-area). Human spot-check at PR review time satisfies this AC.
- [ ] AC-7: Assumption and decision corpora in atelier-fashion are UNCHANGED by this backfill (BR-5 enforcement). `git diff` should show no modifications to `.adlc/knowledge/assumptions/*.md` or `.adlc/knowledge/decisions/*.md`.
- [ ] AC-8: Each repo's PR is merged, feature branches deleted remotely and locally.

## External Dependencies

- **REQ-258 must be merged into toolkit main** ✅ done (PR #12, ac2da85)
- **Consumer repos must have the refreshed templates + taxonomy.md** ✅ done (PRs #488, #54, #58, #35, all merged)
- No libraries, services, or APIs.

## Assumptions

- The agent executing the backfill can infer reasonable tag values from each file's body content. For lessons and specs this is usually clear (title + context); for older bug reports it may require reading the Root Cause section. Conservative tagging (BR-2) handles ambiguity safely.
- The `.adlc/context/taxonomy.md` files in consumer repos (copied from the canonical stub) contain representative values but may not be exhaustive. Authors extend taxonomies as needed; the backfill agent may propose new values that aren't yet in the taxonomy if justified.
- Git operations are safe — no merge conflicts expected since all 4 schema-refresh PRs already merged on top of their main branches.
- Backfill work happens in a fresh conversation session (not the REQ-258 session that shipped the schema) to keep context budget healthy for the 468-file pass.

## Open Questions

- [ ] OQ-1: Should the agent write `updated:` dates backward to preserve temporal ordering in retrieval (e.g. use the file's `created:` date), or forward to today's date (BR-12 default)? Current answer in BR-12 is "today" — but this penalizes older-but-still-relevant docs in tiebreaks. Alternative: leave `updated:` unchanged from its pre-backfill value, only fill it in when absent. Resolution: use BR-12 default for v1; revisit if tiebreak outcomes look wrong.
- [ ] OQ-2: atelier-fashion has 136 legacy lessons (Tier 3, format conversion) — should these be batched into a single lessons commit, or split into sub-batches by content area for reviewability? BR-1 says "per-corpus commits" which implies one commit; a 136-file single commit is reviewable as a pattern (same frontmatter-prepend applied uniformly) but a diff is unwieldy. Resolution: one commit per tier per repo is sufficient; GitHub PR diff view + structured commit message make the review tractable.
- [ ] OQ-3: Should the backfill PRs target separate branches per corpus, or one branch with multiple commits per repo? The four schema-refresh PRs used one branch with one commit per repo; this backfill will have multiple commits per repo. Resolution: one branch per repo, multiple commits stacked (per BR-1, BR-6). PR diff shows commits grouped, reviewer can scroll commit-by-commit.

## Out of Scope

- Backfilling `.adlc/knowledge/assumptions/` (6 files, atelier-fashion only) and `.adlc/knowledge/decisions/` (2 files, atelier-fashion only). Deferred to a follow-up REQ when those corpora become retrievable.
- Extending the REQ-258 retriever to cover assumption/decision corpora — separate REQ.
- Building the `/retag` skill promised in REQ-258's Out of Scope — this backfill is a one-shot manual pass; the `/retag` skill remains a separate follow-up for future on-demand retagging needs.
- Customizing consumer-project taxonomy.md files with project-specific values beyond the canonical stub — separate work item, can happen after the backfill lands.
- Restructuring legacy lesson body content (per BR-3 — insert-only). Any lessons with unclear structure remain as they are in the body; only the frontmatter is added.
- Running `/init` on additional consumer repos not yet surveyed.

## Next Session Runbook

_This REQ is also the handoff document for executing the backfill in a fresh session. When starting the backfill, read REQ-262 first, then follow this runbook._

### Preconditions to verify at session start

```bash
# 1. Toolkit REQ-258 is live
cat ~/.claude/skills/spec/SKILL.md | head -20
# Expect: line 9 says "You are writing a requirement spec following the spec-driven ADLC process." (no "Atelier Fashion" hardcode)
# Expect: line ~19 says "Taxonomy: !`cat .adlc/context/taxonomy.md..."

# 2. All 4 consumer repos have taxonomy.md
for R in atelier-fashion admin-api atelier-web infrastructure; do
  echo "--- $R ---"
  ls -la ~/Documents/GitHub/$R/.adlc/context/taxonomy.md 2>/dev/null || echo "MISSING"
done
# Expect: all 4 present

# 3. Templates refreshed in all 4 repos
for R in atelier-fashion admin-api atelier-web infrastructure; do
  echo "--- $R ---"
  grep -c "^component:\|^domain:\|^stack:\|^concerns:\|^tags:" ~/Documents/GitHub/$R/.adlc/templates/requirement-template.md
done
# Expect: 5 in each (the 5 new fields)
```

If any precondition fails, STOP and surface to the user — the backfill depends on them.

### Suggested work order (lowest-risk first)

Execute in this sequence to validate the pattern on simple repos before the complex ones:

1. **atelier-web** (82 files, all YAML, 3 tiers)
2. **infrastructure** (26 files, all YAML, 2 tiers — no bugs corpus)
3. **admin-api** (54 files, includes 27 Tier-3 legacy lessons, 2 tiers — no bugs corpus)
4. **atelier-fashion** (306 files, includes 136 Tier-3 legacy lessons, 3 tiers)

### Per-repo workflow

```
1. git checkout main && git pull --ff-only
2. git checkout -b chore/req-262-tag-backfill
3. Read .adlc/context/taxonomy.md for project vocabulary
4. For each corpus in {specs, bugs, lessons}:
   a. List files in that corpus
   b. For each file:
      - Read full body (not just frontmatter)
      - Infer tag values from content per BR-2 (conservative)
      - If Tier 3 (legacy lesson): prepend YAML frontmatter block per BR-3
      - If Tier 1 (YAML): insert 5 new tag fields before closing ---, preserving existing fields (BR-7)
      - Update `updated:` date per BR-12
   c. Spot-check 3 random files (BR-9)
   d. git add <corpus-files>
   e. git commit -m "chore(adlc): backfill tags for <corpus> [REQ-262]"
5. git push -u origin chore/req-262-tag-backfill
6. gh pr create --title "chore(adlc): backfill tag frontmatter [REQ-262]" --body <see template>
7. After PR merges: git checkout main && git pull && git branch -D chore/req-262-tag-backfill
```

### Parallelism strategy

- **Within a repo**: stay sequential per corpus to keep commits atomic. Subagents CAN be used per file for tag proposal, but the parent must commit atomically per tier.
- **Across repos**: sequential is safer. Running 4 repos in parallel risks context contamination (agent mixing taxonomies). If time pressure demands it, use 4 separate Claude Code sessions, one per repo.

### Commit message template (per corpus per repo)

```
chore(adlc): backfill tags for <corpus> [REQ-262]

Adds unified retrieval tag frontmatter (component, domain, stack,
concerns, tags) to N files in .adlc/<corpus>/.

Applies BR-2 (conservative tagging — empty over false positive),
BR-3 (insert-only, no body restructure for legacy lessons),
BR-7 (preserve existing frontmatter, only append new fields),
BR-12 (updated: today's date).

Part of REQ-262. Toolkit REQ: adlc-toolkit#12.
```

### PR body template (per repo)

```markdown
## Summary

Backfill unified retrieval tag frontmatter across all in-scope files in this repo's .adlc/ corpus, per [REQ-262](https://github.com/atelier-fashion/adlc-toolkit/blob/main/.adlc/specs/REQ-262-backfill-tag-frontmatter/requirement.md).

## Corpus backfilled
- `.adlc/knowledge/lessons/`: N files (tier: Y)
- `.adlc/specs/*/requirement.md`: M files (tier: 1)
- `.adlc/bugs/*.md`: K files (tier: 1)
- Total: X files

## Commits (per corpus — BR-1)
- <sha> specs
- <sha> bugs
- <sha> lessons

## Out of scope (preserved unchanged per BR-5, BR-7)
- Assumptions and decisions corpora (separate future REQ)
- Existing frontmatter fields other than the new 5
- Legacy lesson body content (BR-3: insert frontmatter only)

## Test plan
- [ ] Spot-check 5 random files per corpus for reasonable tag values
- [ ] Run `/spec "some test feature"` post-merge to confirm retrieval surfaces backfilled docs
- [ ] Confirm no decisions/assumptions files changed (`git diff --name-only` output)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

### When to escalate to the user

- More than 20% of files in a tier score "cannot infer" on `component`/`domain` — indicates taxonomy needs work, not backfill problem.
- Tier 3 conversion produces a non-trivial body diff (body changed, not just frontmatter prepended). Stop immediately, surface the diff.
- Any existing frontmatter field is modified by accident. Revert and re-approach per BR-7.
- A file contains secrets, credentials, or PII in its body or filename. Redact before committing, flag for user review.

### When to stop and verify

After each repo's PR is opened (before merge), pause and confirm with the user:
- Number of files backfilled matches expectation
- Sample tag values look reasonable
- No out-of-scope files modified

Merge only after user confirms. (User-directed — this REQ is high-volume data migration, not a feature ship.)

## Retrieved Context

No prior context retrieved — no tagged documents matched this area.

(Note: this REQ is drafted manually rather than via the live `/spec` skill, because the skill's retrieval corpus in the toolkit repo is still minimal — the toolkit tracks only REQ-258 and this REQ-262 in its own `.adlc/specs/`. If this REQ had been drafted via `/spec`, it would have retrieved REQ-258 as load-bearing context and cited it on BRs 1, 2, 3, 7, 12. REQ-258 is the sole upstream dependency and is linked above.)
