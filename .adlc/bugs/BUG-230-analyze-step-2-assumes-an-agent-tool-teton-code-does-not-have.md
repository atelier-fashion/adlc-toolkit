---
id: BUG-230
title: "/analyze Step 2 assumes an agent-dispatch tool Teton Code does not have, and Step 2a's hygiene shell would pin"
status: in-review
severity: medium
created: 2026-09-26
updated: 2026-09-28
component: "adlc/analyze"
domain: "skills"
stack: ["markdown", "sh"]
concerns: ["portability", "developer-experience"]
tags: ["teton-code", "analyze", "subagents", "harness-agnostic", "shell-provenance", "session-pinned", "bug-228"]
introduced_by: []
attribution: none
---

## Description

Found while verifying BUG-228. `/analyze` Step 2 says "In a single message,
launch the 4 audit agents" (`code-quality-auditor`, `convention-auditor`,
`security-auditor`, `test-auditor`, defined under `~/.claude/agents/`). Teton
Code's tool set is `docs`, `edit`, `glob`, `grep`, `mcp`, `projects`, `read`,
`shell`, `skill` and `web`
(`crates/tetond/src/harness/tools/`). It has no agent-dispatch tool and no
`~/.claude/agents` registry, so Step 2 cannot run as written, and the skill
gives no alternative. `/proceed` already has one for its own agent phases:
"Subagent mode … run the … checklists sequentially in your own context using
the criteria from the agent definitions".

Step 2a (repo hygiene) is written as bash with `$(…)`, quoted `--format='…'`
strings, `awk` programs and pipes. On Teton each of those classifies
`unknown_shell` and pins the session to the local tier (the BUG-220/BUG-228
class), so the hygiene pass would kill the turn the same way Step 1.5 did.

## Reproduction Steps

1. In a Teton Code session rooted at a project with `.adlc/`, run `/analyze`.
2. After Step 1 (and the BUG-228 skip of 1.5/1.6), the model reaches Step 2.

## Expected Behavior

On a harness without agent dispatch, the skill tells the model to run the four
audit checklists one at a time in its own context, reading the checklists from
the agent definitions. On a provenance-classifying harness, Step 2a's checks
either use pin-free spellings or are skipped and named as skipped.

## Actual Behavior

In session `sess-cy6w6jagfw5b0tynjda7x150t8` (2026-09-26) the turn ended right
after Step 1's reads, without starting Step 2. That particular stop was
Teton-side (teton-code BUG-229: the call spent its 1,024-token cap reasoning).
But even with that fixed, Step 2 has no path the model can follow on Teton, and
Step 2a's shell would pin.

## Environment

- Teton Code v0.1.36; adlc-toolkit `main` at `5fdb5b1`

## Root Cause

`/analyze` from Step 1.8 onward assumes Claude Code's harness in three ways.

1. **Agent dispatch.** Step 2 names four agents and gives no alternative. The
   obvious fallback, "read the checklists from the agent definitions" (what
   `/proceed`'s subagent mode says), does not work on Teton either: `read.rs`
   jails every read to the session root, so `~/.claude/agents/*.md` is
   refused in any consumer project.
2. **Unclassifiable hygiene shell.** Step 2a used `CUTOFF=$(date …)`,
   `--format='%(…)'`, `awk` programs, pipes and `2>/dev/null ||` chains. Run
   through Teton's real classifier (a scratch test in `shell_provenance.rs`),
   `CUTOFF=$(…)` is `Unknown` ("command substitution"), and even the
   quote-free `--format=%cs` is `Unknown` ("sets an environment variable",
   because any `=` counts as an assignment).
3. **Steps 1.8 and 1.9** expand `$DELEGATE_TOOLS` and run
   `tools/lint-skills/check.sh` by path. Both are `Unknown` by design (the
   probe confirmed `names its program by path`).

Steps 1.8 and 1.9 were not in the original report. They are the same class in
the same skill, so they are fixed here too.

`git blame` over Step 2/2a returns REQ-417 and REQ-427. Neither is recorded:
two candidates means the operator chooses (REQ-593 BR-3), and neither REQ
introduced a Teton-specific defect.

## Resolution

- **Step 2** gains a "No agent-dispatch tool" path. The model runs the four
  audits itself, one dimension at a time, and is told not to end the turn
  after the scope reads. It uses the agent files where it can reach them and
  a condensed four-dimension checklist inline where it can't. It searches with
  the harness's own `grep`/`glob` tools, not the test auditor's `find -name
  '…'`, which would pin.
- **Step 2a** is rewritten, for every harness, in spellings the real
  classifier returns `rooted` for. The probe ran each one against Teton's
  `classify` with the built-in boundaries:
  - `git rev-parse --abbrev-ref origin/HEAD` for the default branch
  - `git log --no-walk --branches|--remotes --decorate --date short` for
    stale branches, with the model doing the 90-day comparison
  - `git branch [-r] --merged <default>` for merged branches
  - `git diff-tree -r --no-commit-id <empty-tree> HEAD` for duplicates, with
    the model grouping by blob hash (the old `git ls-files | xargs cksum`
    grouping)

  The three old spellings came back `unknown` in the same run, which shows the
  probe distinguishes the two.
- **Steps 1.8 and 1.9** skip on a provenance-classifying harness and report
  the dimension as "unavailable on this harness".
- Step 2's stale reference to "Step 1.7" now names Step 1.6, the candidate
  pre-pass it means.
- New `lint-skills` check `provenance-safe-fence`: a fence whose first line
  is `# provenance-safe` must keep every line inside the grammar (no refused
  characters, no `=`, no by-path program, recognised verbs only; placeholders
  like `<default>` allowed). Putting `--format=%cs` back into the real
  `/analyze` produces exactly one finding (`analyze/SKILL.md:287`).

**Follow-up (verification finding, 2026-09-28).** The first Teton run after
#176 (`sess-ya02n239sw6gkf69w8c5kbc9wr`) reached Step 2 and ran the audit in
context through `glob`/`grep`/`read`. It ran Step 2a's new commands verbatim
(`rev-parse`, `log --no-walk --branches|--remotes`, `branch --merged main`),
and none of them pinned. Its own ad-hoc
`… 2>&1 | grep Date: | sort -u | head -40` did not pin either. Then it
improvised `cargo test --workspace`, which is opaque (`session_pinned`: "runs
an interpreter, build tool or network client") and hit the 30 s timeout.
Claude Code's audit agents are bounded by their tool restrictions, but a model
auditing in its own context is not, and the path never said the audit was
read-only. The no-agent path now forbids test runners, build tools, package
managers and interpreters, and says to report run-dependent findings as
candidates with the command for the user.

## Files Changed

- `analyze/SKILL.md`: Step 1.8/1.9 harness skip, Step 2's no-agent path and condensed checklist, Step 2a rewritten provenance-safe, Step 1.7 → 1.6
- `tools/lint-skills/check.py`: `check_provenance_safe_fence`
- `tools/lint-skills/README.md`: check 11
- `tools/lint-skills/tests/test_check.py` and `tests/fixtures/provenance-safe-{ok,bad}.md`: one clean case, and five lines that must each fire
- `.adlc/context/conventions.md`: the fence rule and the no-agent-tool obligation, added to the preamble-grammar paragraph
