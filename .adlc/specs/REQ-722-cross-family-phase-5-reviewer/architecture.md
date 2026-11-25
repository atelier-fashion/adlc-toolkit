# REQ-722 Architecture — A cross-family reviewer on the Phase-5 panel

## Approach

The reviewer is a **shell partial that calls `adlc-read`, with every decision
made in stdlib Python**. It is not an agent dispatch. The REQ-417 pre-pass is the
precedent, but it is not copied. That pre-pass validates the delegate's citations
in prose the model carries out (`proceed/SKILL.md` Phase 5 step 6), so nothing can
test them. Here the model's job is to run one fence and act on what it prints. The
partial fixes the order of the steps, and Python owns everything with a right
answer:

1. Each touched repo runs one fence. It sources `partials/cross-family-review.sh`
   and calls `adlc_cross_family_review <repo-id> <worktree> <base> <spec> <state>`.
2. The partial resolves both families and the delegation gate, then asks
   `cross_family.py decide` for the run/skip verdict. On a skip it records the
   reason, prints one stderr line and returns 0. No delegate call happens.
3. On a run, it builds one corpus file in a `mktemp` file with an `EXIT` trap:
   the repo's diff against `origin/<integrationBranch>` (LESSON-391) with wide
   context, the changed-files list, and the spec's BR and AC lines. It redacts the
   file with the five-arm chain and fails closed. It then calls `adlc-read` once
   with a fixed question that asks for a line grammar.
4. `cross_family.py validate` parses the output, post-validates every line (BR-6)
   and prints the validated findings as JSON. `run_outcome.py
   record-cross-family` then writes the `crossFamilyReview` record for the repo,
   at the event (LESSON-626).
5. The fence prints the findings inside an `<cross-family-findings>` block. The
   orchestrator adds them to Step B consolidation as `source: ["cross-family"]`.
   No panel member is dispatched with them (BR-7).

The workflow engine does the same through one new leaf agent that runs the same
partial and returns its JSON under a closed schema (BR-12). Both engines produce
records through the same two Python entry points, so they cannot drift.

## Components

### `tools/delegate/model_family.py` (new, stdlib only)

- The closed enum is defined once, here:
  `MODEL_FAMILIES = ("anthropic", "openai", "moonshot", "google", "meta", "other", "unknown")`.
- `parse_family(value)` returns the value for a member, or raises on anything else.
- `families_differ(a, b)` is true only when neither is `unknown` and `a != b`.
- Both the delegate config loader and the harness adapter loader import it. It
  has no PyYAML import, so the system `python3` can load it (ASSUME-003).

### Delegate config `family` key (`tools/delegate/_machine_config.py`, `_common.py`, `adlc-read`)

- `family` joins `DELEGATE_KEYS`.
- `validate_delegate_section` gives it its own branch, which is
  `parse_family` on a string. The generic `isinstance(str)` branch would accept
  any value (LESSON-614).
- An absent key resolves to `unknown`. The existing four keys keep their meaning
  byte for byte (BR-10).
- `Provider` gains a `family` slot, and `--version` prints a `family:` line only
  when a config file exists. That keeps the exact-line no-config tests in
  `test_version.py` unchanged.
- `adlc-read --print-family` prints the resolved family and exits 0. It is the
  only way the shell learns the reviewer family. The config file is read by the
  Python that owns it (REQ-603), never by a shell parse.

### Harness adapter `model_family` key (`tools/adlc/harness_adapter.py`, `harness/*.yml`, `harness_cli.py`)

- A new optional top-level key, validated with `parse_family`. The adapter
  schema version is bumped, as the loader's version gate requires.
- Declared values:

  | Adapter | `model_family` | Why |
  |---|---|---|
  | `claude` | `anthropic` | Claude Code runs only Anthropic models (first-party, Bedrock or Vertex) |
  | `codex` | `openai` | the exec route runs Codex's default model, and `--model` is an operator flag |
  | `copilot` | `unknown` | serves Anthropic and OpenAI models in one session (BR-2) |
  | `cursor` | `unknown` | same reason |
  | `antigravity` | `unknown` | can run more than one family |

- `adlc harness family` prints the implementer family for the current process.
  The resolution order is fixed:
  1. Under the exec engine (`ADLC_EXEC_RUN` set), the run record's `harness`
     field, which the engine wrote and the session cannot change, mapped through
     that adapter's `model_family`.
  2. Otherwise, `CLAUDECODE=1` means the `claude` adapter. This was observed set
     in a Claude Code 2.1 shell during design. `tools/adlc/checks.py` marks it
     unverified, so the task records the version it was checked on.
  3. Otherwise `unknown`.

  The model's own claim about which model it is never counts (LESSON-626).

### `tools/delegate/cross_family.py` (new, stdlib only)

The pure core, testable without a shell. It has one argparse subcommand per job:

- **`decide`** takes `--subagent`, `--gate-rc`, `--implementer`, `--reviewer` and
  prints `run` or `skip <reason>`. The first match wins, and the order is the
  contract:
  1. `subagent-mode`
  2. `delegation-disabled` (gate rc 1, which covers env, config, not opted in
     and unset)
  3. `no-binary` (gate rc 2)
  4. `family-unknown`
  5. `same-family`

  The gate's own six-value enum is not extended; it is mapped here. Its test
  pins that enum (`test_print_gate.py:147`).
- **`validate`** reads the delegate's output, the changed-files list, the
  worktree root and the spec. It prints `{"findings": [...], "dropped": N}` or
  exits 3, which the partial records as `invalid-output`. The line grammar is
  ADR-4, and the per-field checks are BR-6.
- **`check-decline`** decides whether a `declineReason` qualifies under BR-8. It
  must contain at least one citation: a `path:line` or `path:start-end` naming a
  tracked file with the line in range, under the pre-pass charset with no `..`
  segment, or a `test:<path>::<name>` naming a test defined in a tracked test file at
  HEAD, found by reading the file, never by running a test runner (a Phase-5 security
  fix: a runner would execute the tree under review, LESSON-718). REQ-723 BR-5 reuses
  this check.
- **`check-dispositions --state`** lists every `cross-family` finding with no
  disposition, or with a `declined` disposition whose reason fails
  `check-decline`. It exits 1 when there is any. Phase 6's precondition runs it
  (BR-8).
- **`pr-section --state`** renders the PR body's `## Cross-family review`
  section from state: per repo `ran` or `skipped <reason>` with both families,
  and the declined findings under their own heading. It is deterministic, so a
  skip reason or a single-family panel cannot be left out of the PR (BR-5).

### `partials/cross-family-review.sh` (new, POSIX sh, sourced)

`adlc_cross_family_review` runs these steps in order:

1. Run the gate (`partials/delegate-gate.sh`), `adlc-read --print-family`,
   `adlc harness family` and `decide`.
2. On a skip, call `record-cross-family` and print one stderr line:
   `/proceed: cross-family review skipped for <repo>: <reason>`.
3. Run `mktemp "$TMPDIR/adlc-xfam.XXXXXX"` (not `-t`, LESSON-441) and set an `EXIT` trap.
4. Build the corpus with `git -C <wt> diff -U25 <base>...HEAD`, the
   `--name-only` list, and the spec's BR and AC lines.
5. Redact with the five-arm `sed` chain. A non-zero exit or a leftover `.bak`
   records `redaction-failed` with no call.
6. Call `"$ADLC_READ_BIN" --no-warn --paths "$CORPUS" --question "<fixed>"`. A
   non-zero exit records `api-error`. That covers BUG-213's `finish_reason`
   failure, since a truncated answer is never parsed (LESSON-625).
7. Run `validate`. Exit 3 records `invalid-output`.
8. Call `record-cross-family ran` with the counts, then print the findings
   block.

The call is spelled with `$CORPUS`, not `$TMPFILE`, so
`partials/tests/redact-fence.test.sh` still finds exactly one pre-pass fence.
Everything it executes comes from `$ADLC_TOOLKIT_ROOT`, never from the worktree
under review (LESSON-718). The partial is sourced in the fence that calls it
(`cross-fence-fn`).

### State and telemetry (`tools/delegate/run_outcome.py`, `tools/adlc/sprint_exec.py`, `check-run-outcomes.sh`)

- **`record-cross-family`** writes
  `crossFamilyReview.<repo> = {status, reason?, implementerFamily, reviewerFamily, findingCount, droppedCount, declinedCount}`.
  It goes through the existing `_update` and `write_state`, and validates
  `reason` against the closed vocabulary. The value is not redacted, because it
  is a constrained id (LESSON-744).
- **`normalize_findings`** keeps `source` (a list from the enum),
  `disposition` and `declineReason`. `declineReason` is free text, so it is
  redacted.
- **`record-verify`** carries `disposition` and `declineReason` forward by
  dedupe key when a later R3 re-records the list, so Step D's re-record cannot
  erase a decline.
- **`crossFamilyReview` joins `PRIMARY_OWNED`** in `sprint_exec.py`, so a
  close-out does not drop it.
- **The run-outcome record gains one optional `crossFamily` object** at the end
  of `KEYS`, holding per-repo status, reason and the finding, fix and decline
  counts. `check-run-outcomes.sh` keeps its 14 columns. It prints a separate
  `Cross-family:` summary block after the table, and only when some record has
  the object, so the output for a pre-REQ log is byte-identical (AC-15).

### Skill text (`proceed/SKILL.md`, new `proceed/phases-cross-family.md`, `phases-6-8-ship.md`, `phases-state.md`, `phases-telemetry.md`, `agents/pipeline-runner.md`)

`proceed/SKILL.md` is at 447 of its 500 lines, so the procedure lives in a
companion. Phase 5 gets five pointer lines:

- **Step A:** run the cross-family fence for each repo alongside the panel
  dispatch. The panel prompts are unchanged, and none receives the findings
  block (BR-7).
- **Step B:** add the block's findings with `source: ["cross-family"]`. Merging
  unions `source`, as `dimensions` does today.
- **Step C:** a `cross-family` finding is fixed, deferred under item 2, or
  declined with a reason that passes `check-decline`.
- **Step D:** the cross-family reviewer is not re-run (BR-1).
- **Subagent mode:** run the companion's record-only fence, which calls
  `record-cross-family skipped subagent-mode` per repo.

Phase 6 gains one precondition: `check-dispositions` must exit 0 before the PR
is created. Exit 1 sends the orchestrator back to Step C for the listed
findings, and no halt point is added. `test_phase7_text.py:411` keeps asserting
**four**.

The companion's fences say beside each one that none runs when the file is
read, and what each needs first (LESSON-899).

### Workflow engine (`workflows/adlc-sprint.workflow.js`, new `agents/cross-family-reviewer.md`)

- **`FINDINGS`** gains three optional fields:
  - `source`: an array of `['panel', 'cross-family']`, with `minItems: 1`;
  - `disposition`: one of `fixed`, `deferred`, `declined`;
  - `declineReason`.
- **`dedupeAndRank`** unions `source` on merge, with the same push, sort and
  dedupe as `dimensions` at line 482. The dedupe key does not change.
- **A new `CROSS_FAMILY` schema** has `status`, `reason`, both families,
  `findings` (items `FINDINGS.items`) and `dropped`. It is closed.
- **The leaf `cross-family-reviewer`** runs once per touched repo, beside
  `runPrePass`. It is not added to `panelMembers()`, whose six-member test stays
  as it is, and it is not given a `REVIEWER_DIMENSIONS` entry. Either change
  would make `fixedPairs` re-run it at Step D and violate BR-1.
- **A null leaf result** is recorded as `skipped` / `invalid-output`, never
  omitted (BR-12).
- **`agents/cross-family-reviewer.md`** has `tools: Bash`. Its whole job is to
  source the partial, run it, and return the JSON. It gets an entry in
  `agents_render.py` `_SHIPPED_DEFAULTS` and the canonical fallback paragraph.

## Key decisions

**ADR-1: Run the reviewer as a fence plus Python, not as an agent.** The reviewer
is another model's output, so no agent in this harness is needed to produce it.
An agent would be one more same-family reader between the delegate and
consolidation, which is the filtering BR-7 forbids. The fence also runs in solo
mode with no dispatch cost. The workflow engine needs a leaf only because its
script cannot run shell, so the leaf is a pass-through.

**ADR-2: Families are declared, resolved by the owner of each source, and
compared for equality.**
- The reviewer family comes from the config, read by the delegate's Python.
- The implementer family comes from the exec engine's run record, or a harness
  environment marker. The worktree under review cannot write either one.
- Any doubt resolves to `unknown`, which skips the review. A wrong `unknown`
  costs one cross-family review. A wrong family claim would label a
  single-family review as cross-family, which is the failure this REQ exists to
  prevent.
- Open Question (a) is resolved this way: Copilot, Cursor and Antigravity are
  `unknown` for the first release.
- An operator who points Claude Code at a non-Anthropic model through a proxy
  defeats the `claude` declaration. This is recorded as a known limit, not
  guarded against.

**ADR-3: Same endpoint and config block as `adlc-read`.** Open Question (b) is
resolved for the first release: no separate `review:` lane. A second block would
double the governed config surface that REQ-609 just closed (LESSON-614), before
BR-13's counts show that review quality on the bulk-read model is the limit. The
`family` key is defined so a later `review:` block can reuse it.

**ADR-4: The output contract is a tab-separated line grammar, not JSON.**
`adlc-read` returns plain text (`_common.py` `_strip_fences` only), and a
model's JSON fails as a whole. A line grammar fails one line at a time, which is
what BR-6's per-finding drop needs:

```
FINDING<TAB><severity><TAB><path><TAB><line><TAB><class><TAB><title>
RULE<TAB><BR-n|AC-n><TAB><met|partial|unmet><TAB><note>
```

- A `RULE ... unmet` line becomes a Major, must-fix finding of class
  `omitted-requirement` on the spec file.
- A `partial` line becomes a Minor finding.
- `met` lines are counted only.
- A rule id must exist in the spec. The spec path is the one exception to BR-6's
  changed-files membership, because an omitted rule has no line in the diff to
  cite.
- Titles and notes are free text. They are cut to the pre-pass description
  charset and 200 characters.
- Any other line is ignored and not counted, so a delegate's preamble cannot
  invalidate the review.

**ADR-5: Phase 6 refuses to start; no new halt point.** BR-8's "a finding is
never dropped" is enforced by `check-dispositions` before the PR is created.
Phase 5 already loops to fix, so a failing check returns the orchestrator to
Step C. This keeps the Autonomous Execution Contract at four halts, and
REQ-723's solo override is the only proposal that adds one.

**ADR-6: Keep redaction as the five-arm `sed` chain, with a parity test.** The
chain already lives inline in three places. Making it a shared partial would
change the pre-pass, which BR-11 rules out. The partial carries the chain once,
and a parity test runs it against `credential_redact.py` `INTAKE_PATTERN`, the
way REQ-648's `test_redaction_parity_with_emit_telemetry_sed_chain` does
(ASSUME-009). The pre-existing inline copies are left as they are.

## Pre-existing defects found during exploration (not fixed here)

- `proceed/SKILL.md` Phase 5's pre-pass diffs `main...HEAD`, not
  `origin/<integrationBranch>...HEAD` (a LESSON-391 violation).
- Its `mktemp` and `EXIT` trap exist in prose only; the fence uses `$TMPFILE`
  without creating it.
- The workflow `CANDIDATES.gateReason` enum is `['ok','no-binary','disabled-via-env']`,
  but `partials/delegate-gate.sh` also emits `disabled-via-config` and
  `not-opted-in`. Those results fail the schema and turn into null with no log
  line.
- `agents/delegate-pre-pass.md` names the redaction-failure reason
  `api-error` in its header and `redaction-failed` in its step.

The new reviewer copies none of these. They are BR-11's "pre-pass is unchanged"
surface, so fixing them is a separate bug.

## Lessons applied

- **LESSON-008:** the delegate's output is untrusted. It is validated per line
  in Python, wrapped in delimiters, and a temp file is used with one stderr line.
- **LESSON-330:** the reviewer marks each BR and AC, and an `unmet` mark becomes
  a must-fix finding.
- **LESSON-331:** `FINDINGS` and `CROSS_FAMILY` change in the same task as their
  emitter.
- **LESSON-391:** the diff is against `origin/<integrationBranch>`.
- **LESSON-614:** `family` gets its own enum branch in the strict loader, and the
  differential oracle's key set gains it.
- **LESSON-625:** a non-zero `adlc-read` exit, including truncation, is
  `api-error`, and partial output is never parsed.
- **LESSON-626:** families are bound to records the session cannot write, and
  the review record is written at the event.
- **LESSON-718:** the partial and Python run from the installed toolkit, never
  the reviewed tree.
- **LESSON-742:** `partials/tests/run.sh` and the fence census goldens run on
  the final tree.
- **LESSON-744:** `reason`, `source` and `class` are validated, not redacted.
  Only `declineReason` and titles are free text.
- **LESSON-899:** the companion's fences say beside each one when it runs.

## Implementation notes (deviations recorded at TASK-285)

- **No adapter schema bump (TASK-279).** `model_family` is accepted at every existing schema
  version. Moving the adapters to a new version would have made the doctor skip four adapters
  and stopped Copilot and Cursor loading, because schema 3 and later require
  `sandbox_can_reach_common_gitdir`.
- **The reviewer family is `unknown` under an environment override (TASK-278).** An
  `ADLC_DELEGATE_MODEL` or `ADLC_DELEGATE_BASE_URL` value the config file does not hold points
  the call at a model the declaration does not describe.
- **Step D confirmation (TASK-284, TASK-283).** The reviewer never re-runs (BR-1), so a fixed
  cross-family-only blocking finding counts as a `correctness` fix in its repo:
  `correctness-reviewer` re-checks it, and its report stands in for the finding. Without this
  the workflow engine would have kept a fixed finding blocking.
- **Exec runs (TASK-283).** `proceed/phases-cross-family.md` joins `exec_prompt.PIPELINE_SOURCES`,
  and `fence_census.py` gains the closed placeholders `<repo-id>` and `<declineReason>`, so every
  fence in the companion routes through the runner and an exec run records the review (BR-12).
- **mktemp (TASK-282)** uses `mktemp "$TMPDIR/adlc-xfam.XXXXXX"`, not `-t`, because BSD and GNU
  read `-t` differently (LESSON-441). Any failure building the corpus, not only a failed `sed`,
  records `redaction-failed`: nothing is sent in each case.
- **Known limits.** `check-dispositions` takes one worktree, so in a cross-repo run a sibling's
  cross-family finding can be fixed or deferred but not declined (the safe direction). An
  operator who points Claude Code at another family through a proxy defeats the `claude`
  declaration. With delegation off the reviewer family is recorded `unknown`, because
  `--print-family` runs only after the gate passes.

## Phase-5 review changes (recorded at Phase 5)

- **Dispositions.** `check-dispositions` accepts `deferred` only on a finding that is
  neither Critical nor must-fix, and R3 keeps `mustFix` so it can tell. A review that
  ran with findings, and has no cross-family entry in `verify`, is outstanding.
- **Decline citations are read, never run.** A `test:<path>::<name>` citation qualifies
  when a tracked test file defines `<name>` at HEAD (Python parsed with `ast`, files
  over 1 MB not read). No test runner runs the tree under review (LESSON-718).
- **Redacting a decline reason.** A credential match is kept only inside a citation
  that checks out against the primary worktree at HEAD, so a credential shaped like a
  citation is still redacted; with no worktree, everything is redacted.
- **Multi-repo rule marks.** When more than one repo is touched (`touched: true`, or a
  `worktree` with no `touched` key, the workflow engine's shape), an `unmet` rule is a
  non-blocking Minor: one repo's diff cannot show another's work.
- **Step D confirmation.** Each blocking finding is handed to the reviewer that
  confirms it (`correctness` for a cross-family-only one, each panel dimension for a
  merged one), which re-raises it if it is still there. A cross-family copy retires
  only when every confirmer re-ran. `markWorkflowFixed` matches a cross-family entry by
  dedupe key only.
- **The workflow engine at Phase 6** records dispositions (`fixed`, or `deferred` for a
  non-blocking finding left unfixed), runs `check-dispositions` before it opens a PR,
  and writes the `pr-section` output into the body without reading it back. A refused
  check ends the run `blocked` with reason `cross-family-dispositions`, a value added to
  the run-outcome `BLOCKED_REASONS`. This is a deliberate difference from `/proceed`,
  which loops back to Step C: the engine has no decline path and a bounded fix loop,
  so it stops with the outstanding findings listed, which is the safe direction.
- **Relayed findings are re-validated** in JS (path rule shared with the pre-pass's
  `validateCitations` through `isSafePath`, unchanged in behaviour; severity, class,
  a sanitized title, `source` forced) and checked against the leaf's `findingCount`.
- **Free text** (titles, notes, decline reasons) is cut to `[A-Za-z0-9 .,:/_-]`.
- **Secret files** (keys, `.env*`, credential and Terraform variable files) are excluded
  from the corpus by case-insensitive pathspecs.
- **Implementer family.** The Claude Code arm needs both `CLAUDECODE=1` and
  `CLAUDE_CODE_ENTRYPOINT`, and is refused beside Codex's sandbox variables. A Codex or
  Cursor session started from a Claude Code shell that sets no child marker of its own
  can still read `anthropic`; that is a recorded residual.
- **One repo-id charset**, `[A-Za-z0-9_][A-Za-z0-9._-]{0,63}`, in the partial, the
  engine, the exec placeholder and `run_outcome`, with a parity test.
- **Known limits added.** The leaf relay is a same-family model: a leaf that rewrites
  both the findings and the count goes unnoticed. A delegate that wrote part of the
  diff (through `adlc-write`) is not seen by the implementer-family rule.

## Operator decisions at Phase 5 (2026-11-25)

The Phase-5 reflector raised three questions; the operator accepted the recommended
answer to each.

1. **Rule marks with no valid finding (BR-6, AC-8).** Output whose FINDING lines all
   fail but whose RULE lines are valid is recorded `ran`, not `invalid-output`. The rule
   marks are output, and an `unmet` mark becomes a finding of its own.
2. **A delegate that wrote part of the diff (BR-3).** When Phase 4 used `adlc-write`,
   the implementer family is still taken from the harness. Tracking which model wrote
   each line is out of scope; this is a recorded limit (see "Known limits added").
3. **How strong a decline citation is (BR-8).** A citation must name a real line of a
   tracked file, or a test a tracked test file defines, but not one shown to relate to
   the finding. That is accepted until REQ-723's arbiter, which judges declines on
   evidence, lands.
