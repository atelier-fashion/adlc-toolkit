---
id: TASK-022
title: "analyze/SKILL.md: add Step 1.5 (Kimi pre-read with command -v fallback)"
status: draft
parent: REQ-414
created: 2026-05-13
updated: 2026-05-13
dependencies: []
---

## Description

Insert a new Step 1.5 in `analyze/SKILL.md` between "Step 1: Determine Scope" and "Step 2:
Launch Audit Agents". The step performs a bulk pre-read of top-level project shape files
(README, `.adlc/context/*`, top-level config like `package.json`/`Cargo.toml`/etc.), gated
behind `command -v ask-kimi` AND `ADLC_DISABLE_KIMI != "1"`. The product of the step is a
one-paragraph "project shape" summary that the 4 audit agents in Step 2 receive as
additional context. When the gate fails, Claude reads the same shape files into its own
context (identical downstream behavior).

The step MUST emit exactly one stderr log line per invocation stating which path was taken.

## Files to Create/Modify

- `analyze/SKILL.md` (MODIFY) — insert a new `### Step 1.5: Optional pre-read via ask-kimi`
  section between the existing Step 1 and Step 2. The new section must:
  1. State the gate condition (verbatim shape from REQ-414 BR-1):
     ```sh
     if command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]; then
       # delegated path
     else
       # fallback path
     fi
     ```
  2. On gate pass:
     - Identify the shape-file set: `README.md`, `.adlc/context/project-overview.md`,
       `.adlc/context/architecture.md`, `.adlc/context/conventions.md`, plus any top-level
       manifest in this list that actually exists: `package.json`, `Cargo.toml`, `pyproject.toml`,
       `go.mod`, `Gemfile`. Filter to existing files only.
     - Invoke `ask-kimi --no-warn --paths <files...> --question "Summarize this project's
       shape in one paragraph: language, frameworks, layout convention, primary risk areas.
       300 words max."` (the `--no-warn` is for non-interactive call sites; the user
       installed the tooling knowingly).
     - Capture stdout as the project-shape summary string.
     - Emit stderr: `/analyze: delegating bulk pre-read to kimi (read N shape files)`.
     - If `ask-kimi` exits non-zero, emit `/analyze: ask-kimi failed — falling back to
       Claude direct read` and fall through to the fallback branch.
  3. On gate fail (no ask-kimi OR `ADLC_DISABLE_KIMI=1` OR delegated call errored):
     - Claude uses the Read tool on the same shape-file set and forms the same one-paragraph
       summary internally.
     - Emit stderr: `/analyze: ask-kimi unavailable — Claude is reading shape files directly`
       (or `... disabled via ADLC_DISABLE_KIMI` when that's the cause).
  4. Pass the resulting summary as an additional context paragraph to each of the 4 audit
     agents launched in Step 2 (one extra paragraph in the dispatch prompt).
  5. Post-validate (BR-3): if Kimi's summary cites a specific file path, REQ id, or LESSON id,
     verify each exists on disk (`test -f` / `ls .adlc/specs/REQ-XXX-*/` / `ls .adlc/knowledge/lessons/LESSON-XXX-*`)
     before propagating. Drop or rewrite citations that fail validation. The step
     documentation must spell this out as an explicit instruction.

## Acceptance Criteria

- [ ] `analyze/SKILL.md` contains a `### Step 1.5: Optional pre-read via ask-kimi` section
      between the existing Step 1 and Step 2 (verified by `grep -n "Step 1.5" analyze/SKILL.md`
      returning a single line whose number is between Step 1's and Step 2's).
- [ ] The gate uses the BR-1 exact form `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]`
      (verified by `grep -F 'ADLC_DISABLE_KIMI' analyze/SKILL.md`).
- [ ] The step documents BOTH the delegated and fallback paths, the stderr log line for each,
      and the post-validation rule.
- [ ] No other section of `analyze/SKILL.md` is modified except inserting Step 1.5 (verified by
      a focused diff on Step 1 and Step 2 — only the surrounding text moves).
- [ ] `grep -F 'ask-kimi' analyze/SKILL.md` matches at least once.
- [ ] The skill is still valid markdown (no broken section numbering, no orphan code fences) —
      verified by reading the full file end-to-end.
- [ ] No other skill files modified: `git diff --name-only` after this task lists only
      `analyze/SKILL.md` and the TASK-022 file under tasks/.

## Technical Notes

- This is a documentation/instruction change to a markdown skill. There is no Python or shell
  code being executed by the skill itself — the gate is a literal `if … then … else … fi`
  spelled out in the instructions for Claude to follow at invocation time.
- The shape-file list is intentionally short and stable. Do NOT make it auto-discover every
  file in the repo — the win is bounded ("read these N files for me") not "summarize the whole
  codebase."
- The new step must not exceed ~40 lines of markdown. Skills accrete; keep the surface tight.
- Verify by mentally walking through both paths for the adlc-toolkit repo: shape files
  resolve to README.md + .adlc/context/project-overview.md + architecture.md + conventions.md
  (no package.json / Cargo.toml — only the .adlc trio + README).
- Do NOT modify any other skill in this task (BR-7).
