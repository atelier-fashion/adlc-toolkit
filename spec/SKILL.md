---
name: spec
description: Write requirement specs from feature requests
argument-hint: Feature description or request [--lite|--full]
---

# /spec — Requirement Specification

You are writing a requirement spec following the spec-driven ADLC process.

## Ethos

!`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo No ethos found — run /init, or /adlc:init on the plugin install, to vendor .adlc/ETHOS.md`

## Context

Run this block first, with your shell tool, and read its output before you continue. Each read prints a notice instead of failing when its file is absent.

```sh
# adlc-context
echo '--- ADLC context'
cat .adlc/context/project-overview.md 2>/dev/null || echo 'No project overview found'
echo '--- Requirement template'
cat .adlc/templates/requirement-template.md 2>/dev/null || echo 'No requirement template found — run /init (/adlc:init on the plugin install) to vendor .adlc/templates'
echo '--- Taxonomy'
cat .adlc/context/taxonomy.md 2>/dev/null || echo 'No taxonomy found — consider running /init (/adlc:init on the plugin install) to scaffold one'
```

## Input

The feature request is the argument: whatever follows `/spec` in the invocation (on Claude Code it can also arrive as an `ARGUMENTS:` line appended to this text). With none, ask the user what to build.

**Lane flags — read and strip these before anything else** (REQ-652 BR-4). The argument may carry `--lite` or `--full`, each a standalone token, to force the REQ's lane instead of letting Step 1.7 triage it. Read them from the argument above and remove every occurrence of both tokens, before the Prerequisites check and before Step 1.4's intake gate:

- **Both present** — stop with `/spec: --lite and --full are mutually exclusive — pass at most one` and do nothing else: no intake, no retrieval, and no Step 2. An id allocated for a request that then errors is burned, because `adlc_alloc_id` advances a machine-global counter and pushes a remote reservation ref.
- **One present** — remember which. Step 1.7 records it instead of triaging.
- **Neither** — Step 1.7 triages.

From here on, "the feature request" means the argument with those tokens removed, and every fence below that passes the argument receives the stripped text: where the argument appears inline in a fence, delete the flag tokens from it before running the fence. `adlc_intake_detect` reads its argument raw, so a leftover flag would count as request text, and `--lite notes.txt` would no longer resolve as a readable file path. `--intake` is not a lane flag; it stays. This is the model reading the argument, as with `/sprint --workflow` and `/wrapup --close-out` — no shell parses the lane flags, and `partials/intake.sh` knows nothing about them.

## Prerequisites

Before proceeding, verify that `.adlc/context/project-overview.md` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` (`/adlc:init` on the plugin install) first to set up the project context."

## Instructions

### Step 1: Understand the Request
1. Read `.adlc/context/project-overview.md` for grounding context (skip if already in conversation)
2. Read `.adlc/context/architecture.md` for existing patterns (skip if already in conversation)
3. If the feature request is vague or ambiguous, ask clarifying questions before proceeding. Wait for answers. **When Step 1.4's intake gate activates, that step supersedes this item** — ambiguity is then handled by the structured gap list rather than by ad-hoc questions here. This item stays in force for the ordinary short-request path, where there is not enough source material to check against the template.

### Step 1.4: Unstructured-Source Intake

Requirements do not always arrive as a coherent feature request. They arrive as meeting notes, a chat transcript, a ticket dump, a voice-note transcription, or three paragraphs of stakeholder prose. This step accepts that input and produces two things: the distilled feature request Step 1.5 will tag, and an explicit, classified **gap list** naming what the source does not answer.

The gap list is the point. A spec written from a transcript will always contain assumptions; the failure mode is not making them, it is making them invisibly.

**This step runs before Step 1.5** because Step 1.5 derives the retrieval query from the request, and a distilled statement is better tag input than a raw transcript. It runs **before Step 2** because an interactive blocking-gap halt must not burn a REQ id — `adlc_alloc_id` mutates a shared machine-global counter and pushes a remote reservation ref.

1. **Activation gate (BR-1).** Intake activates only when the input is unstructured. Source the partial and call the detector in the same fenced block (BR-10 — the `cross-fence-fn` rule). The detector gets the feature request with `--lite` and `--full` already stripped (**Input**), here and in step 2's fence: substitute it for `<request>`, quotes included, as one single-quoted literal with every `'` in it written `'\''` (conventions.md "Bash in skills", "Substituting a value into a fence"). Never double-quote it: a backtick or `$` in the request would run.

   ```sh
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
   adlc_intake_detect '<request>'; gate=$?
   echo "intake_gate=$gate  reason=${ADLC_INTAKE_REASON:-none}  kind=${ADLC_INTAKE_KIND:-none}  inline=${ADLC_INTAKE_INLINE:-0}"
   # This fence is a GATE PROBE only — step 2 re-derives everything in its own shell.
   # For an inline source, detect materializes a temp dir; discard this probe's copy
   # here or every intake run leaks one. Deletion guards live in the partial, never
   # at the call site.
   adlc_intake_cleanup "" "$ADLC_INTAKE_PATH"
   exit 0
   ```

   `adlc_intake_detect` returns **1** for an ordinary feature request — none of BR-1's three triggers (an explicit `--intake` flag, an argument resolving to a readable file path, or an argument exceeding 25 lines) fired. **When it returns 1, skip the entire rest of Step 1.4 and go straight to Step 1.5.** No intake runs, no gap list is produced, no `## Provenance` section is written, and no stderr line is emitted (AC-1). This is the common path and it must stay exactly as fast and as quiet as it is today.

   It returns **0** when intake should run, having exported `ADLC_INTAKE_REASON` (which trigger fired), `ADLC_INTAKE_KIND` (`transcript` | `notes` | `ticket` | `prose`), `ADLC_INTAKE_PATH`, and `ADLC_INTAKE_INLINE`.

2. **Segment the source before delegating (BR-12).** Segmentation is what makes a partial delegate summary *detectable*. Without it a truncated read yields zero gaps precisely because the unread remainder is invisible, and BR-11's benign path would certify the result as complete.

   Segmentation and credential redaction happen in **one** fenced block, and that block re-runs the detector rather than relying on step 1's exports. This is not redundancy: each fenced block is a separate shell invocation, so nothing — not even an exported variable — survives from step 1's block. Re-deriving is the only correct option, which is why the detector is cheap and idempotent.

   ```sh
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
   adlc_intake_detect '<request>' || exit 0
   adlc_intake_segment "$ADLC_INTAKE_PATH" || exit $?
   adlc_intake_redact "$ADLC_INTAKE_CORPUS" || exit $?
   echo "INTAKE_CORPUS=$ADLC_INTAKE_CORPUS"
   echo "INTAKE_SOURCE=$ADLC_INTAKE_SOURCE"
   echo "INTAKE_SEGMENTS=$ADLC_INTAKE_SEGMENTS"
   echo "INTAKE_LINES=$ADLC_INTAKE_LINES"
   echo "INTAKE_INLINE=$ADLC_INTAKE_INLINE"
   ```

   `INTAKE_INLINE=1` means the source was pasted rather than a file on disk, and `adlc_intake_detect` materialized it into a private temp dir so the file-based steps below work uniformly. It matters at cleanup (step 7): a materialized temp dir is ours to delete, a user's source file never is.

   Return codes from `adlc_intake_segment`: **0** = segmented; **2** = source unreadable; **3** = **over budget**. On rc=3 the partial has already printed a refusal naming the actual line count and the 8000-line / 40-segment budget. **Halt. Do not write a spec** (AC-10). Tell the operator to split the source and run intake on each part. Never truncate: reading the first 8000 lines silently would recreate the exact invisible-compression failure this step exists to eliminate.

   The corpus embeds only the source's **basename** (BR-7); full local paths stay on the machine. Redaction runs before anything leaves the machine, applying the same 5-pattern chain `/proceed` Phase 5 uses on its verify diff.

   **Thread the echoed values forward as literals.** Later fenced blocks cannot read them as variables — substitute the actual printed values into the commands below, the same way the telemetry `flag` path is threaded through Step 1.6. Writing `"$ADLC_INTAKE_CORPUS"` in a later block would silently expand to an empty string.

3. **Read the source body — gated delegation, hard fallback (BR-5).** Read `spec/references/intake-source-read.md` and follow it before you continue. It holds this step in full: the telemetry flag, the delegate gate, the delegated read with its coverage reconciliation and citation checks, the fallback read, and the telemetry emit, all working from the literals step 2 echoed. Nothing in this file replaces it.

4. **Identify gaps against the template's sections.** Get the checklist — derived from the requirement template, never hardcoded, so a future template section is gap-checked automatically:

   ```sh
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
   adlc_intake_sections
   ```

   <!-- intake-gap-rules: read verbatim by space/build.mjs (REQ-670); keep the markers -->

   For **each** section returned, ask what the source material does not answer, and write the gap as a **specific unanswered question**, never a category label. "Who is allowed to archive a project — any member, or only the owner?" is a gap. "Permissions unclear" is not; it names a topic instead of a question, and nobody can answer it.

   A section with everything it needs produces no gap. A complete, unambiguous source produces **zero gaps, no halt, and no Open Questions** (BR-11).

5. **Classify every gap (BR-2).** Each gap is exactly one of:

   | Severity | Test | Disposition |
   |---|---|---|
   | `blocking` | A faithful spec **cannot** be written without the answer — an undefined entity, a missing permission model, two source statements that contradict | halt (interactive) or Open Questions (non-interactive) |
   | `assumption` | The spec **can** proceed under a stated assumption a reviewer can later challenge | Assumptions section |

   Classification is per-gap and **must be justified in one sentence**. The justification is what stops `blocking` from becoming a reflex and `assumption` from becoming a dumping ground.

   <!-- /intake-gap-rules -->

6. **Disposition by mode (BR-3, BR-4).** Non-interactive is detected by the **same conditions Step 1.5 item 4 already lists** — do not restate them here; one definition, referenced twice. Of those conditions exactly one is reachable today: dispatch into a subagent context that cannot receive further user input. `/spec` is human-invoked — `/proceed` refuses to create a spec (`proceed/SKILL.md` "Arguments" and "What This Skill Does NOT Do") and `/sprint` requires the spec to already exist on the integration branch — so no pipeline calls `/spec` at present. The rule is written to the general condition so it holds unchanged if that ever becomes reachable.

   **Interactive mode** — blocking gaps **halt** before the spec file is written (ETHOS #1: stop and clarify rather than guess). Present them as a numbered list and wait:

   ```
   Intake found <N> blocking gap(s). The spec cannot be written faithfully without these:

     1. [System Model] Who is allowed to archive a project — any member, or only the owner?
     2. [Business Rules] Does archiving cascade to child items, or leave them active?

   Answer these, or say "assume" with your intent and they will be recorded as stated assumptions.
   ```

   Assumption gaps never halt in either mode.

   **Non-interactive mode** — **never halt** (AC-4). Write blocking gaps into `## Open Questions`, and emit exactly one stderr line naming the count:

   ```
   /spec: intake found <N> blocking gap(s) — written to Open Questions, not answered (non-interactive mode)
   ```

7. **Carry the result into Step 3, and clean up.** Retain the distilled feature request (it replaces the argument as the input Step 1.5 tags and Step 3 writes from), the classified gap list with dispositions, and the provenance triple — source **basename**, `kind`, and intake date. Step 3 persists all three.

   Then remove the temp files, substituting the literals echoed in step 2. The corpus holds a redacted copy of the source and there is no `trap` that can span fenced blocks, so this is the only cleanup:

   ```sh
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
   # Both arguments are the LITERALS echoed in step 2. adlc_intake_cleanup removes the
   # corpus, and removes the source dir ONLY when the source was the inline file intake
   # itself materialized — a user-supplied source file is theirs and is never deleted.
   adlc_intake_cleanup <INTAKE_CORPUS literal> <INTAKE_SOURCE literal>
   ```

### Step 1.5: Derive Query Tags for Retrieval

Before retrieval fires, derive a structured query from the feature request. This query drives both context loading (Step 1.6) and the self-tagging of the new REQ (Step 3).

1. Read the feature request (the argument) alongside any grounding context already in conversation. Extract likely area signals:
   - **component** — which narrow area this touches (e.g., `API/auth`, `iOS/SwiftUI`, `adlc/spec`)
   - **domain** — broader problem domain (e.g., `auth`, `payments`, `ui`, `adlc`)
   - **stack** — tech layers implicated (e.g., `express`, `firestore`, `swiftui`, `markdown`)
   - **concerns** — cross-cutting dimensions (e.g., `security`, `perf`, `a11y`, `retrieval`)
   - **tags** — free-form keywords from the feature description (e.g., `password-reset`, `pagination`, `caching`)
2. Construct the query object:
   ```
   query = {
     component: "<proposed>",
     domain: "<proposed>",
     stack: [<proposed>],
     concerns: [<proposed>],
     tags: [<proposed>]
   }
   ```
3. **Interactive mode** (manual `/spec` invocation): surface the proposed query to the user and wait for confirmation or edits:
   ```
   Proposed retrieval query for this feature:
     component: <value>
     domain:    <value>
     stack:     [<values>]
     concerns:  [<values>]
     tags:      [<values>]
   Confirm or edit any field before retrieval fires.
   ```
4. **Non-interactive / pipeline mode** — detect this when ANY of:
   - The argument already contains explicit tag values (e.g., a caller passed `component: X` or `tags: [...]` in the prompt)
   - The invocation prompt explicitly says "invoked from /proceed" or "pipeline mode" or supplies an inherited query object
   - Running inside a subagent context that cannot receive further user input (e.g., dispatched via the Agent tool)

   In any of these cases: do NOT block for confirmation. Use caller-supplied tag values verbatim; for any unspecified dimension, use the proposed value from sub-step 2. Proceed directly to Step 1.6.
5. Retain the confirmed `query` object. It is reused by Step 1.6 (retrieval) and Step 3 (self-tagging the new REQ's frontmatter).

### Step 1.6: Unified Retrieval Across Corpora

Run a weighted-score retrieval over three corpora using the query from Step 1.5. This is the only retrieval behavior — the prior 3-tier lesson grep is removed.

1. **Enumerate candidate files** with three Grep passes (paths relative to project root):
   - `.adlc/knowledge/lessons/*.md` — no status filter, all lessons are candidates
   - `.adlc/specs/*/requirement.md` — **exclusion filter (BUG-194)**: admit every spec EXCEPT those whose frontmatter `status` is one of `draft`, `superseded`, `cancelled`, `rejected`. A spec with a missing or unparseable `status` is **admitted** (it is dropped later by sub-step 2 only if the whole frontmatter block is malformed).
   - `.adlc/bugs/*.md` — include only where frontmatter `status` is `resolved` or `closed`

   The spec filter is an **exclusion list, not an allowlist**. This direction is
   load-bearing, not stylistic: the terminal status every shipped REQ lands in is
   `complete` (written by `/wrapup` Step 4.1 and `/proceed` Phase 6-8), and
   consumer repos additionally carry the legacy synonyms `done`, `completed`, and
   `deployed`. An allowlist has to enumerate all of those correctly or it silently
   discards the corpus — which is exactly what BUG-194 was: the original
   `approved` | `in-progress` | `deployed` allowlist admitted 0 of 42 toolkit
   specs and 11 of 543 ecosystem-wide, because two of its three values are
   vocabulary no toolkit skill has ever written. An exclusion list fails toward
   recall: an unrecognized or newly-invented status is retrieved (cheap — one
   extra scored candidate) rather than silently dropped (expensive — invisible
   corpus loss).

   Admitted (non-exhaustive, for orientation): `complete`, `deployed`, `done`,
   `completed`, `approved`, `in-progress`, `in-review`.
   Excluded, and why: `draft` (not yet validated — not prior art),
   `superseded` / `cancelled` / `rejected` (withdrawn — citing them would
   propagate decisions that were explicitly reversed).

   The exclusion set below is the machine-readable source of truth for this
   filter. `tools/lint-skills`'s `retrieval-status-parity` check reads it and
   fails if any status the lifecycle skills *write* appears in it (BUG-194's
   recurrence guard — LESSON-012: structural enforcement, not a prose promise).
   Keep the block and the prose above in sync when changing either.

<!-- retrieval-status: spec-exclude -->
- `draft` — not yet validated; not prior art
- `superseded` — replaced by a later REQ; citing it propagates a reversed decision
- `cancelled` — abandoned before shipping
- `rejected` — explicitly declined
<!-- /retrieval-status -->

   If any directory is empty or missing, skip it and continue (cold-start path).

1a. **Status-filter shrink diagnostic (BUG-194 — do not skip).** After the spec
   pass, compare the number of `.adlc/specs/*/requirement.md` files that exist on
   disk against the number that survived the exclusion filter. If the directory
   held **one or more** spec files and **zero** survived, this is not a cold start
   — it is a filter/vocabulary mismatch. Emit to stderr:

   ```
   /spec: WARNING — spec corpus has <N> requirement.md files but 0 passed the status filter (statuses seen: <comma-separated distinct values>). Retrieval is running on lessons+bugs only. This is a filter/vocabulary mismatch, not a cold start — see BUG-194.
   ```

   Then continue (this is a warning, never a halt). Carry the fact forward: the
   `## Retrieved Context` section in Step 3 must say `Spec corpus suppressed by
   status filter — see stderr warning (BUG-194)` rather than the plain
   no-context line, so the degradation is visible in the artifact and not only in
   the terminal. This diagnostic exists because the cold-start message in
   sub-step 8 is otherwise byte-identical for "no specs exist" and "every spec
   was filtered out" — the failure mode BUG-194 hid behind for four months
   (LESSON-012: a silent path needs a structural signal, not a prose promise).

2. **Read the frontmatter of every candidate** using Read with `limit: 30` (enough to cover full frontmatter block including any leading HTML comments, e.g., the lesson template's naming-convention comment). Parse these fields: `component`, `domain`, `stack`, `concerns`, `tags`, `updated`, `created`, `status`, `supersedes`. `supersedes` is parsed for presentation only — sub-steps 3–6 never read it (REQ-646 BR-7). `confidence` is not parsed: nothing in this step presents or scores it. If the frontmatter is malformed (missing `---` delimiters, unparseable YAML), skip that doc and continue — do not crash.

3. **Compute a weighted score per candidate** using the following rule:
   - `+3` if `doc.component == query.component`
   - `+2` if `doc.domain == query.domain`
   - `+2 × |doc.concerns ∩ query.concerns|`
   - `+1 × |doc.stack ∩ query.stack|`
   - `+1 × |doc.tags ∩ query.tags|`
   - `+1` foundational floor **only for lesson documents** with none of the five tag fields populated. Specs and bugs with zero tag overlap score `0`.

4. **Filter** out every doc with final score `0`.

5. **Sort** using a strict lexicographic key `(score DESC, effective_date DESC, corpus_priority ASC, id ASC)`:
   - `effective_date` per doc is the first non-empty value in this chain: `updated` → `created` → file mtime → epoch-minimum (if all are absent)
   - `corpus_priority` maps `lesson=0`, `bug=1`, `spec=2`
   - Interpretation: highest score first; among equal scores, newest `effective_date` wins; among equal scores **and** equal dates, corpus priority `lesson > bug > spec` applies; final tiebreak is alphabetical `id`
   - Missing dates never cause retrieval failures — they are treated as oldest and lose date tiebreaks

6. **Take the top 15 globally** across all corpora. There are no per-corpus quotas (no minimum-lesson floor, no maximum-bug cap). If fewer than 15 candidates survive filtering, take what is available.

7. **Body-read of top-15 docs** — gated delegation, hard fallback. Read `spec/references/retrieval-body-read.md` and follow it before you continue. It holds this sub-step in full: the telemetry flag, the delegate gate, the delegated read with its coverage reconciliation and citation checks, the fallback read, and the telemetry emit. Nothing in this file replaces it.

7a. **Superseded annotation (REQ-646 BR-7, ADR-6 — presentation only).** For each
   retrieved **lesson** in the top 15 (specs and bugs carry no `supersedes`; skip
   this sub-step when no lesson was retrieved), ask whether another lesson names it
   in `supersedes`. The superseding lesson is usually *not* in the top 15, so the
   `supersedes` parsed in sub-step 2 cannot answer this — run one corpus-wide
   reverse lookup per retrieved lesson. Substitute the lesson's id for `<id>` only
   after it matches `^LESSON-[0-9]{3,6}$` — an id that does not match is skipped,
   never substituted — and the `case` re-checks it before anything uses it:

   ```sh
   ID='<id>'
   case "$ID" in
     LESSON-[0-9][0-9][0-9]|LESSON-[0-9][0-9][0-9][0-9]|LESSON-[0-9][0-9][0-9][0-9][0-9]|LESSON-[0-9][0-9][0-9][0-9][0-9][0-9])
       LC_ALL=C find .adlc/knowledge/lessons -maxdepth 1 -type f -name 'LESSON-*.md' -exec awk -v id="$ID" 'FNR==1{s=0;skip=0;c=0;sub(/^\357\273\277/,"")} {sub(/\r$/,"")} skip{next} s==0&&/^[ \t]*$/{next} s==0&&/^<!--/{c=1} c{ if(/-->/){c=0}; next } s==0&&!/^---$/{skip=1;next} s<2&&/^---$/{s++;next} s==1&&$(0)~("^supersedes:[ \t][^#]*" id "([^0-9]|$)"){print FILENAME;skip=1}' {} + 2>/dev/null ;;
     *) echo "superseded lookup: $ID is not a LESSON-nnn id — skipped" >&2 ;;
   esac
   ```

   Each printed path is a superseding lesson; its id is the `LESSON-<digits>`
   prefix of the basename (ignore a hit on the lesson's own file). Record
   `superseded by LESSON-yyy` next to the retrieved lesson — every hit,
   comma-separated. No output means not superseded. The id reaches `awk` as data
   (`-v`), so the `case` guards the only place it is substituted. The program is
   single-quoted and reads only the frontmatter block, found the way
   `adlc_lesson_check` finds it: a leading BOM and each line's trailing CR are
   dropped, blank lines and HTML comments are skipped, and the block opens only
   when the first other line is `---` — a file that opens with anything else, such
   as a legacy lesson whose `---` lines are horizontal rules in its body, is
   skipped whole. The match needs a blank after `supersedes:` (the one key
   spelling the check accepts), and `[^#]*` stops at a trailing `# comment`, so
   neither a body line nor a comment that mentions the id is a hit. `2>/dev/null`
   keeps a missing lessons directory quiet — no output, so not superseded.
   `-exec … {} +` runs nothing when no file matches, where GNU `xargs` would run
   its command once on empty input; the quoted `-name` never hands the shell an
   unmatched glob (zsh aborts on one — LESSON-335); and `([^0-9]|$)` stops
   `LESSON-40` matching `LESSON-404` without a word-boundary escape, which BSD
   tools silently ignore (LESSON-013).

   **This changes nothing about retrieval.** A superseded lesson keeps its score,
   its rank, and its place in the top 15; sub-steps 3–6 are not re-run, and neither
   `supersedes` nor `confidence` feeds the score. Weighting or filtering by either
   is deferred until the corpus carries the fields (LESSON-571: a scoring change
   must be designed against the writer vocabulary it reads).

8. **Surface the retrieval summary** to the user before authoring continues. This is always shown — there is no verbose flag gate:
   ```
   Retrieved context for this REQ:
     LESSON-034 (lesson, score 5, superseded by LESSON-040): Silent failure remediation
     BUG-012    (bug,    score 5): Auth rate-limit bypass
     REQ-019    (spec,   score 3): Prior login redesign
     ... (etc.)
   ```
   The `, superseded by LESSON-yyy` suffix appears only on a lesson sub-step 7a
   found superseded; every other line keeps the plain `(corpus, score)` form. The
   score shown is the one sub-steps 3–6 computed — the annotation never changes it.

9. **Cold-start path**: if every corpus is empty, or all candidates filter out to zero, skip retrieval and record this explicitly when Step 3 writes the `## Retrieved Context` section. Proceed to authoring without retrieved bodies. **A true cold start requires the corpora to be empty or every candidate to lose on *score*.** If the spec corpus had files on disk and lost them all to the *status filter*, that is the BUG-194 mismatch, not a cold start — sub-step 1a's warning fires and Step 3 records the suppressed-corpus line instead of the cold-start line.

### Step 1.7: Triage the Lane

Every new REQ gets exactly one lane, `lite` or `full`, which Step 3 writes to its frontmatter (REQ-652 BR-1). `/proceed` reads it. A lite REQ skips spec validation, architecture, task breakdown, architecture validation, the reflector and the five-agent panel; it gets one review pass instead, plus a mechanical lane check of the real diff before the PR. **Never ask the operator to choose**, in interactive or non-interactive mode. The lane is triage's call, or the flag's.

This step runs after Step 1.6 because the last criterion below is judged against what retrieval returned, and before Step 2 so a lane is settled before any id is allocated (REQ-652 ADR-2). Triage reads the feature request, or Step 1.4's distilled request when intake ran.

1. **Forced lane.** If **Input** found `--lite` or `--full`, skip the judgment. The lane is the flag's, `lane_reason` is `"forced by --lite"` or `"forced by --full"`, and `lane_forced` is `true`. Go to Step 2. A forced lite REQ is still subject to `/proceed`'s lane check: a solo run halts there and asks the operator, and an unattended sprint runner escalates.

2. **Otherwise, triage against REQ-652 BR-2.** The REQ goes to the full lane if triage finds evidence that **any** of these full-lane triggers holds:
   1. it changes a domain schema, an API contract, a validator or a data model
   2. it changes auth, security, secrets, deploy, CI or infrastructure
   3. it touches more than one deployable or more than one repo. A cross-repo REQ is always full
   4. it adds or upgrades a dependency
   5. its footprint is more than `max_files` source files. `max_files` is 3 unless `.adlc/config.yml` sets `lanes.lite.max_files`; read that file with the Read tool when it exists, never with a shell YAML parse. Files the lane check does not count (tests, `.adlc/`, `CHANGELOG*`, and any `lanes.lite.count_exclude` glob; the full list is in the toolkit's `partials/lane-check.md`) do not count here either. Changed lines are not counted at all
   6. it reverses a decision recorded in an existing REQ or lesson for the same component, judged against the context Step 1.6 retrieved

   When none holds, the lane is `lite`. Name the files the change will most likely touch before judging criteria 1, 2 and 5. A project's `lanes.lite.blocked_paths` in `.adlc/config.yml` lists where its schemas, contracts and infrastructure live, so a likely file under one of those globs is evidence for criterion 1 or 2.

3. **Uncertain means lite** (REQ-652 BR-3). When you cannot tell whether a criterion holds, choose `lite` and say so in `lane_reason`, naming the criterion you could not settle. A wrong lite start costs one escalation: `/proceed`'s lane check reads the real diff, and a change that crossed a line escalates to the full lane with the spec and the code kept. A wrong full start costs the whole full pipeline.

4. **Write the reason.** `lane_reason` is one line. For `full`, it names the criterion that fired and the evidence, e.g. `"adds a field to the Page data model in packages/domain"`. For `lite`, it says why none fired, e.g. `"one component, copy only: no schema, config or dependency change"`, and says which criterion was uncertain when one was. `lane_forced` is `false`. When an escalation later shows the triage was wrong, `/wrapup` writes a lesson naming this reason (REQ-652 BR-14), so make it specific enough to be tuned from.

Retain the lane, `lane_reason` and `lane_forced` for Step 3 and Step 4.

**A missing `lane` means `full`** (REQ-652 BR-12). Every reader treats a spec without the field as a full-lane REQ, so every spec written before this step existed keeps its behavior. Only `lite` and `full` are lane values; never write the field empty.

### Step 2: Determine the Next REQ ID
1. Use the **global** atomic counter file `${ADLC_HOME:-$HOME/.claude}/.global-next-req` (shared across all repos for unique IDs) — but the counter is now a **cache, not the authority**: the remote is the source of truth (REQ-518). Allocation derives the remote high-water, takes `max(remote, local)`, allocates `max + 1`, and fast-forwards the local counter — all inside the existing `mkdir` lock with its symlink/TOCTOU guards intact.
2. Allocate via the shared `partials/id-alloc.sh` helper (BR-5 — one parameterized helper replaces the three near-identical inline blocks; the lock block + its REQ-416/LESSON-014 rationale live in the partial). Source it and call `adlc_alloc_id` **in the same fenced block** (the cross-fence-fn rule — see conventions.md "Bash in skills"):
   ```bash
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-alloc.sh"; fi
   REQ_NUM=$(adlc_alloc_id req)
   # `exit 1` inside adlc_alloc_id's subshell terminates only the subshell — REQ_NUM
   # would be silently empty. Guard the parent context (REQ-416 verify D-pass).
   [ -n "$REQ_NUM" ] || { echo "ERROR: failed to allocate REQ number — aborting before writing malformed spec" >&2; exit 1; }
   # If ADLC_ALLOC_DEGRADED=1 was set (remote unreachable), the helper already warned on
   # stderr — record "id allocated without remote verification — verify before PR" in the
   # spec's Assumptions section (BR-3). Never block spec-writing on network availability.
   ```
   `adlc_alloc_id req` handles the absent-counter bootstrap scan internally (highest `REQ-xxx` under `$ADLC_REPOS_ROOT`, BSD-safe), the `mkdir` lock that serializes concurrent `/sprint` sessions, and the remote high-water max. Single-machine behavior is unchanged: when the remote has no higher allocation, the same id is produced as before (BR-7).

### Step 3: Create the Requirement Spec
1. Create directory: `.adlc/specs/REQ-xxx-feature-slug/`
2. Create `requirement.md` using the template from `.adlc/templates/requirement-template.md`
3. Fill in all sections:
   - **Frontmatter**: id, title, status (`draft`), `deployable` (carry the template default unless the feature is explicitly non-deployable — e.g., iOS-only or docs-only), created date, updated date, AND the five query tags from Step 1.5 — `component`, `domain`, `stack`, `concerns`, `tags`. This self-tagging makes the new REQ retrievable for future `/spec` invocations (per REQ-258 BR-7). Then the three lane fields from Step 1.7, after `tags`:
     ```yaml
     lane: "lite"
     lane_reason: "one component, copy only: no schema, config or dependency change"
     lane_forced: false
     ```
     A forced lane reads `lane: "full"`, `lane_reason: "forced by --full"`, `lane_forced: true`. **Quote every lane string value**, even one that looks safe. An unquoted `: ` inside `lane_reason` makes the frontmatter unparseable, and Step 1.6 skips a spec whose frontmatter does not parse, so the REQ silently drops out of retrieval. `lane_forced` is a bare boolean. Do not write `lane_escalated`; `/proceed` sets it when it escalates a REQ.
   - **Description**: What the feature does and why — be specific and grounded in the project context
   - **System Model**: Structured data model — Entities (fields, types, constraints), Events (triggers, payloads), Permissions (actions, roles). Remove sub-sections that don't apply to this feature.
   - **Business Rules**: Explicit, testable constraints governing behavior (e.g., "Only item owner can delete"). Numbered BR-1, BR-2, etc.
   - **Acceptance Criteria**: Concrete, testable criteria as checkboxes
   - **External Dependencies**: Any new APIs, services, or libraries needed
   - **Assumptions**: Things assumed to be true that could affect the design. **If Step 1.4 ran**, every `assumption`-severity gap is written here — see sub-step 5.
   - **Open Questions**: Questions that need answers before implementation. **If Step 1.4 ran in non-interactive mode**, every unanswered `blocking` gap is written here — see sub-step 5.
   - **Out of Scope**: Items explicitly excluded to prevent scope creep
   - **Retrieved Context** (NEW, always present): append a `## Retrieved Context` section at the end of the spec listing every retrieved source from the retrieval summary produced in Step 1.6 in the form `ID (corpus, score): title` — a lesson Step 1.6 sub-step 7a found superseded carries the same parenthetical as the summary, `ID (corpus, score, superseded by LESSON-yyy): title` (e.g. `LESSON-034 (lesson, score 5, superseded by LESSON-040): Silent failure remediation`), with its score unchanged. If no context was retrieved (cold-start path — either the corpus is empty or no documents scored above zero), write exactly: `No prior context retrieved — no tagged documents matched this area.` If instead Step 1.6 sub-step 1a fired (spec files existed on disk but none survived the status filter), write exactly: `Spec corpus suppressed by status filter — see stderr warning (BUG-194).` and, when lessons or bugs still matched, list them beneath it. Never emit the cold-start line for a status-filter suppression — collapsing the two is the defect BUG-194 fixed.
4. **Inline citations**: when a retrieved doc directly informed a Business Rule, Assumption, or Acceptance Criterion, add an inline citation in the form `(informed by BUG-012)` or `(informed by REQ-019, LESSON-034)` at the end of that line. Citations are required when the retrieved doc is load-bearing for the rule; optional when the doc was background reading only.

5. **Persist the intake result — ONLY if Step 1.4 ran** (REQ-594). If intake did not activate, skip this sub-step entirely: write no `## Provenance` heading, no placeholder, and no empty section. A spec written without intake is exactly the shape it is today (BR-8, BR-11).

   **a. Append `## Provenance`** after `## Out of Scope`, recording what the spec was derived from and what the source did not answer:

   ```markdown
   ## Provenance

   - Source: `standup-2026-08-27.txt` (kind: transcript)
   - Intake date: 2026-08-27

   | Section | Severity | Gap | Disposition |
   |---|---|---|---|
   | System Model | blocking | Who is allowed to archive a project — any member, or only the owner? | answered |
   | Business Rules | assumption | Does archiving cascade to child items, or leave them active? | assumed |
   | Acceptance Criteria | blocking | What should the UI show while an archive is in flight? | open |
   ```

   Record the source **basename only** — never a full local path (BR-7). This table is the complete gap list with every entry classified and attributed to a named section, which is what makes the intake result auditable in one place.

   **b. Mirror gaps into the working sections.** Provenance is the audit record; Assumptions and Open Questions are the surfaces the rest of the pipeline already reads. Writing gaps in both places is deliberate — do not collapse the duplication.

   - Every `assumed` gap → a `## Assumptions` entry containing the gap question **verbatim**:
     ```
     - Does archiving cascade to child items, or leave them active? — assumed: archiving is shallow; child items stay active. (intake gap: Business Rules)
     ```
     Verbatim matters: the gap text is what a reviewer greps for to confirm nothing was quietly reworded between the gap list and the spec. Put commentary around the question, never inside it.
   - Every `open` gap (blocking, unanswered — non-interactive mode only) → a `## Open Questions` entry, also verbatim:
     ```
     - [ ] What should the UI show while an archive is in flight? (intake gap: Acceptance Criteria — blocking, unanswered at intake)
     ```
   - `answered` gaps (blocking, resolved by the operator in interactive mode) appear in Provenance only. Their answers are already reflected in the spec body.

   **c. Zero gaps is the benign path (BR-11).** A complete, unambiguous source adds no Assumptions entries and no Open Questions entries. The only difference from a non-intake spec is the `## Provenance` section, whose table is then empty apart from a `_No gaps identified._` line.

### Step 4: Present for Review
1. Display the full requirement spec to the user
2. Show the lane and its reason on one line, and whether triage or a flag chose it:
   ```
   Lane: lite (triaged) — one component, copy only: no schema, config or dependency change
   Lane: full (forced by --full)
   ```
3. Highlight any assumptions or open questions that need input
4. Remind the user of the next step. For a full-lane REQ, run `/validate` before advancing to `/architect`. For a lite-lane REQ, run `/proceed REQ-xxx`, which skips validation and architecture; `/proceed --full REQ-xxx` escalates it by hand.

## Quality Checklist
- [ ] Acceptance criteria are specific and testable (not vague)
- [ ] Description explains the "why" not just the "what"
- [ ] Assumptions are explicitly stated
- [ ] Out of scope items prevent scope creep
- [ ] No implementation details leaked into the requirement (that's for architecture phase)
- [ ] Retrieved Context section present
- [ ] Frontmatter carries a quoted `lane` (`"lite"` or `"full"`), a quoted one-line `lane_reason`, and `lane_forced`, chosen by Step 1.7 without asking the operator
