// workflows/adlc-sprint.workflow.js — the `adlc-sprint` Dynamic Workflows engine.
//
// This is a Claude Code DYNAMIC WORKFLOWS script, NOT a normal Node program. It
// runs inside the Workflow runtime, which has NO filesystem and NO shell: the
// script owns ONLY control flow (sequence, fan-out, loops, merge ordering) and
// dispatches `agent()` leaves to do every git / gh / file / state operation.
// "Orchestration is the script; agents are the hands." (REQ-474, ADR-3)
//
// Runtime globals available here (do NOT import them):
//   meta      — exported pure literal (declared first; see below).
//   agent(prompt, opts?) -> Promise<any>   — dispatch a leaf subagent. With
//               `opts.schema` it returns the VALIDATED object. `opts.agentType`
//               selects a predefined agent (e.g. 'feature-tracer'); `opts.phase`
//               groups progress; `opts.label`/`opts.model`/`opts.isolation`.
//   parallel(thunks) -> Promise<any[]>     — concurrent, barrier; a failed thunk
//               yields null (filter with `.filter(Boolean)`).
//   pipeline(items, ...stages) -> Promise<any[]> — each item flows through the
//               stages independently (no cross-item barrier). A stage callback
//               receives (prev, originalItem, index).
//   phase(title), log(msg), args (the input object), budget.
//
// FORBIDDEN at runtime (throw): Date.now(), Math.random(), new Date(), and any
// fs / shell / require of Node core modules. The ONLY require permitted is the
// sibling schemas module (resolved through the workflows path convention).
//
// Halt contract (load-bearing, ADR-6 / BR-4): a halt is a RETURNED value
// `{state:'blocked', ...}`, NEVER a thrown error. A throw drops the pipeline
// item to null and loses the question, so `runReq` must never let a halt escape
// as an exception. The discriminant field is `state` (the TERMINAL schema's
// name — schemas are the contract, ADR-7), NOT `terminal`. See `blocked()`.

const { REPOS, VERDICT, TASKS, FINDINGS, PRS, TERMINAL } = require('./schemas.js');

// ---------------------------------------------------------------------------
// meta — MUST be a pure literal and the first statement (no variables, calls,
// or interpolation). The runtime reads this statically to render the phase
// timeline. Phases mirror the per-REQ chain in architecture.md "Workflow script
// structure". (ADR-3)
// ---------------------------------------------------------------------------
export const meta = {
  name: 'adlc-sprint',
  description: 'Parallel ADLC pipeline: N REQs concurrently, each with its full internal fan-out restored (explore trio + parallel Phase-5 review panel). The workflow engine behind /sprint --workflow.',
  phases: [
    { title: 'Preflight — eligibility + max-5 bound' },
    { title: 'Phase 0 — worktree + state' },
    { title: 'Phase 1 — validate spec' },
    { title: 'Phase 2 — explore trio + architect/tasks' },
    { title: 'Phase 3 — validate arch + tasks' },
    { title: 'Phase 4 — implement (serial)' },
    { title: 'Phase 5 — review panel + consolidate' },
    { title: 'Phase 6 — open PR(s)' },
    { title: 'Phase 7 — PR cleanup + CI watch' },
    { title: 'Phase 8 — wrapup / merge' },
  ],
};

// ---------------------------------------------------------------------------
// Tunables — concurrency bound is the existing /sprint behavior (BR-12).
// ---------------------------------------------------------------------------
const MAX_CONCURRENT_REQS = 5; // applied AFTER eligibility (BR-12)
const MAX_GATE_ITERATIONS = 3; // ≤3 validate→fix loop per gate (BR-4)

// ELIGIBILITY_SCHEMA — the Preflight agent's structured return. Declared here,
// ABOVE the top-level Preflight block, because the module body runs top-to-
// bottom: a `const` referenced by top-level code must be initialized before
// that code runs (function declarations hoist, but `const` does not — a later
// declaration would be a temporal-dead-zone ReferenceError). This schema is
// LOCAL to the engine's control flow, not one of the 7 shared agent-output
// contracts in schemas.js. Pure literal; additionalProperties:false. (ADR-7)
const ELIGIBILITY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['reqs'],
  properties: {
    reqs: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'eligible'],
        properties: {
          id: { type: 'string' },
          eligible: { type: 'boolean' },
          reason: { type: 'string' },
          integrationBranch: { type: 'string' },
          touchedRepos: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
};

// MERGE_RESULT_SCHEMA / PR_VERIFY_SCHEMA — the Phase-8 IO leaves' structured
// returns. Declared HERE, above the top-level `await pipeline(...)`, for the same
// TDZ reason as ELIGIBILITY_SCHEMA: the top-level await suspends the module body,
// so any `const` a runReq() leaf reads must be initialized BEFORE that await runs
// — a later declaration would be a temporal-dead-zone ReferenceError. Both are
// LOCAL to the engine's control flow (not the 7 shared contracts in schemas.js).
// Pure literals; additionalProperties:false. (ADR-7, TDZ note in the header)
//
// MERGE_RESULT_SCHEMA: the single-repo self-merge agent's claim. `mergeConflict`
// drives the blocked halt; `merged` is the AGENT's (untrusted) claim — the script
// still re-verifies it via `gh pr view` (PR_VERIFY_SCHEMA) before accepting it.
const MERGE_RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['merged'],
  properties: {
    merged: { type: 'boolean' },        // agent's claim — re-verified by the script
    mergeConflict: { type: 'boolean' }, // true ⇒ halt blocked(merge-conflict)
    detail: { type: 'string' },
  },
};

// PR_VERIFY_SCHEMA: ground-truth merge state per PR (from `gh pr view --json
// state,mergedAt`). The script reads `state === 'MERGED'` (and mergedAt present)
// as the ONLY accepted proof of merge — claim ≠ truth (BR-6).
const PR_VERIFY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['prs'],
  properties: {
    prs: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['repo', 'url', 'state'],
        properties: {
          repo: { type: 'string' },
          url: { type: 'string' },
          state: { type: 'string' }, // OPEN | MERGED | CLOSED (gh literal)
          mergedAt: { type: 'string' },
        },
      },
    },
  },
};

// ===========================================================================
// Top-level orchestration: Preflight → per-REQ pipeline.
// ===========================================================================
//
// The Workflow runtime invokes the module body; this top-level block is the
// entrypoint. `args` carries the input object (System Model: WorkflowArgs):
//   args.reqs              — string[] of REQ ids to sprint.
//   args.integrationBranch — resolved integration branch hint (per repo the
//                            Phase-0 agent re-resolves; never hardcode 'main').
//   args.answers           — map<reqId,string>; {} on first run, carries user
//                            replies to halts on resume (ADR-6 / BR-5).

phase('Preflight — eligibility + max-5 bound');

// Preflight — ONE agent scores eligibility per REQ (BR-12, BUG-060). The agent
// does all the I/O the script cannot: reads each REQ's spec/state, checks the
// requirement is approved, resolves the integration branch (origin/<branch>,
// never hardcoded main), and reports a per-REQ eligibility record. The max-5
// bound is applied by the SCRIPT *after* eligibility so we never silently drop
// an eligible REQ before scoring it.
const ELIGIBILITY = await agent(
  preflightPrompt(args.reqs || []),
  {
    label: 'preflight-eligibility',
    schema: ELIGIBILITY_SCHEMA,
    // Inline-prompted DEFAULT workflow subagent (no agentType) — `agentType` is
    // reserved for true specialists (the explore trio, the 6 reviewers,
    // task-implementer, kimi-pre-pass). 'pipeline-runner' is the legacy
    // "run a whole /proceed" doer and would misbehave as a generic IO worker;
    // Preflight is read-only eligibility scoring, so use a default subagent
    // (full tools) driven entirely by the inline prompt. (ethos #6)
  },
);

// Keep only the eligible REQs, in the order the agent ranked them.
const eligible = (ELIGIBILITY.reqs || []).filter((r) => r.eligible);

// Apply the max-5 concurrency bound AFTER eligibility (BR-12). Log any
// truncation so a silent top-N coverage drop is never hidden (BR-12 / AC-8).
const todo = eligible.slice(0, MAX_CONCURRENT_REQS);
if (eligible.length > MAX_CONCURRENT_REQS) {
  const dropped = eligible.slice(MAX_CONCURRENT_REQS).map((r) => r.id);
  log(
    `Preflight: ${eligible.length} eligible REQs exceed the max-5 concurrency `
    + `bound; running the first ${MAX_CONCURRENT_REQS}, deferring `
    + `${dropped.length}: ${dropped.join(', ')}.`,
  );
}

// Surface ineligible REQs too, so the user sees why a requested REQ was skipped.
for (const r of (ELIGIBILITY.reqs || []).filter((x) => !x.eligible)) {
  log(`Preflight: skipping ${r.id} — ineligible (${r.reason || 'no reason given'}).`);
}

// Per-REQ pipeline: each REQ flows through `runReq` independently (no cross-REQ
// barrier inside the pipeline). Single-repo REQs self-merge in Phase 8; cross-repo
// REQs stop at `pr-ready` and are sequenced AFTER the pipeline by the ADR-12
// barrier below. A halt inside `runReq` is a RETURNED terminal value, so a blocked
// REQ never poisons its siblings. (ADR-6 / BR-4 / ADR-12)
const results = await pipeline(todo, (r) => runReq(r.id));

// Cross-REQ merge sequencing (ADR-12). The pipeline left every cross-repo REQ at
// `pr-ready`; merge them now. REQs that share a touched sibling repo MUST merge
// serially (a shared repo can take only one merge at a time without a rebase
// race); REQs that touch disjoint repos stay parallel. Single-repo REQs already
// merged in Phase 8 and are passed through untouched. This MERGES IN PLACE in the
// results array so the returned terminals reflect the post-barrier state.
const sequenced = await sequenceCrossRepoMerges(results, todo);

return { results: sequenced };

// ===========================================================================
// runReq(id) — the per-REQ chain. Phases 0–3 land here (TASK-057), Phase 4–5 in
// `implement`/`verify` (TASK-058), and Phases 6–8 in `openPRs`/`cleanupAndWatchCI`
// /`wrapupAndMerge` (TASK-059). Returns a TERMINAL value; never throws (ADR-6).
// ===========================================================================
async function runReq(id) {
  // Per-REQ progress grouping. CRITICAL: pass `phase: id` on every agent() call
  // for this REQ instead of calling the global `phase()` — multiple runReq()
  // instances run concurrently in the pipeline, so a global `phase()` here would
  // race across REQs. (TASK-057 AC: opts.phase = id) (ADR-3)
  const P = { phase: id };

  // -------------------------------------------------------------------------
  // Phase 0 — worktree + state. ONE agent does all the git/state I/O: it
  // resolves the integration branch, creates `.worktrees/<id>` from
  // `origin/<integrationBranch>` (NEVER a hardcoded main), records the ABSOLUTE
  // worktree path in pipeline-state.json.repos[*].worktree, and returns REPOS.
  // Idempotent: if the worktree already exists (resume), it reuses it rather
  // than recreating. (BR-2, ADR-4, REQ-263 absolute-path contract, BUG-060)
  // -------------------------------------------------------------------------
  const REPO_STATE = await agent(phase0Prompt(id), {
    ...P,
    label: `${id} phase0-worktree`,
    schema: REPOS,
    // Default workflow subagent (no agentType) — a generic git/state IO worker
    // driven by the inline prompt, NOT the legacy 'pipeline-runner'. (ethos #6)
  });
  const repos = REPO_STATE.repos || [];
  if (repos.length === 0) {
    // No worktree means no place to do work — fail (not a user-answerable halt).
    return failed(id, 'phase0-no-worktree', 'Phase 0 returned no repo records.');
  }
  // The primary worktree is where serial Phase-4 writes happen; every later
  // agent is told this absolute path (the REQ-263 dispatch-line contract).
  const primary = repos.find((r) => r.primary) || repos[0];
  const worktree = primary.worktree;

  // -------------------------------------------------------------------------
  // Phase 1 — validate the spec. `gate()` runs the ≤3 validate→fix loop and
  // returns a boolean; 3× failure → RETURN blocked (never throw). (BR-4)
  // -------------------------------------------------------------------------
  const specOk = await gate(
    id,
    P,
    worktree,
    {
      label: `${id} phase1-validate-spec`,
      fixLabel: `${id} phase1-fix-spec`,
      target: 'spec',
      validatePrompt: phase1ValidatePrompt(id, worktree),
      fixPrompt: phase1FixPrompt(id, worktree),
    },
  );
  if (specOk !== true) return specOk; // gate() returned a `blocked` terminal

  // -------------------------------------------------------------------------
  // Phase 2 — explore trio (parallel) → architect/tasks agent. The three
  // read-only explorers fan out via parallel() (ADR-5, BR-3); a failed thunk
  // yields null and is filtered. The architect then synthesizes the explore
  // reports into a tiered TASKS plan. (ADR-3)
  // -------------------------------------------------------------------------
  const explorers = ['feature-tracer', 'architecture-mapper', 'integration-explorer'];
  const exploreReports = (
    await parallel(
      explorers.map((a) => () =>
        agent(explorePrompt(id, worktree, a), {
          ...P,
          label: `${id} explore-${a}`,
          agentType: a,
        }),
      ),
    )
  ).filter(Boolean);

  const TASK_PLAN = await agent(architectPrompt(id, worktree, exploreReports), {
    ...P,
    label: `${id} phase2-architect`,
    schema: TASKS,
    // Default workflow subagent (no agentType) — the architect/synthesis role is
    // an inline-prompted generalist, not the legacy 'pipeline-runner'. (ethos #6)
  });
  const tasks = TASK_PLAN.tasks || [];

  // -------------------------------------------------------------------------
  // Phase 3 — validate the architecture + tasks. Same ≤3 gate as Phase 1.
  // (BR-4)
  // -------------------------------------------------------------------------
  const archOk = await gate(
    id,
    P,
    worktree,
    {
      label: `${id} phase3-validate-arch`,
      fixLabel: `${id} phase3-fix-arch`,
      target: 'arch',
      validatePrompt: phase3ValidatePrompt(id, worktree),
      fixPrompt: phase3FixPrompt(id, worktree),
    },
  );
  if (archOk !== true) return archOk; // gate() returned a `blocked` terminal

  // -------------------------------------------------------------------------
  // Phase 4 (serial implement) + Phase 5 (review panel) — TASK-058. Phase 5 can
  // RETURN a `blocked` terminal (a reflector userFacing question); that halt is
  // propagated here exactly like the gate halts above — never thrown. (ADR-6)
  // -------------------------------------------------------------------------
  await implement(id, P, worktree, tasks);           // Phase 4 — serial writer
  const verifyResult = await verify(id, P, worktree, repos); // Phase 5 — panel
  if (verifyResult !== true) return verifyResult;    // reflector-question halt
  const PR_STATE = await openPRs(id, P, worktree, repos); // Phase 6 — open PR(s)
  await cleanupAndWatchCI(id, P, worktree, PR_STATE);     // Phase 7 — sanity + CI
  const term = await wrapupAndMerge(id, P, worktree, repos, PR_STATE); // Phase 8

  return term; // a TERMINAL value (merged | pr-ready | blocked | failed)
}

// ===========================================================================
// gate(id, P, worktree, spec) — the ≤3 validate→fix loop shared by Phases 1
// and 3. Returns `true` on approval; on 3× failure RETURNS a `blocked`
// terminal value (the caller propagates it). NEVER throws. (BR-4, ADR-6)
//
//   spec = { label, fixLabel, target:'spec'|'arch', validatePrompt, fixPrompt }
// `label` groups the validate attempts; `fixLabel` groups the fix rounds — kept
// distinct so progress output never conflates a validate with its fix.
// ===========================================================================
async function gate(id, P, worktree, spec) {
  for (let i = 1; i <= MAX_GATE_ITERATIONS; i++) {
    // Validate agent — read-only verdict against the VERDICT schema.
    const verdict = await agent(spec.validatePrompt, {
      ...P,
      label: `${spec.label} (attempt ${i}/${MAX_GATE_ITERATIONS})`,
      schema: VERDICT,
      // Default workflow subagent (no agentType) — the validate role is an
      // inline-prompted /validate generalist, not 'pipeline-runner'. The FIX
      // below correctly uses the 'task-implementer' specialist. (ethos #6)
    });

    if (verdict.pass === true) return true;

    // Not approved. On the final attempt, do NOT fix again — halt instead so
    // the user can intervene. (BR-4: validation fails 3× → blocked)
    if (i === MAX_GATE_ITERATIONS) {
      return blocked(id, `${spec.target}-validation`, {
        reason: `${spec.target} validation failed ${MAX_GATE_ITERATIONS} times`,
        detail: verdict.detail || verdict.reason || '',
      });
    }

    // Dispatch a task-implementer fix agent, handing it the validator's reason
    // so the fix is targeted. The next loop iteration re-validates.
    await agent(spec.fixPrompt(verdict), {
      ...P,
      label: `${spec.fixLabel} (round ${i})`,
      agentType: 'task-implementer',
    });
  }
  // Unreachable (the loop returns on the final attempt), but keep the contract
  // explicit: a fall-through is a blocked halt, never an undefined return.
  return blocked(id, `${spec.target}-validation`, {
    reason: `${spec.target} validation exhausted retries`,
  });
}

// ===========================================================================
// Terminal-value constructors. Halts and failures are RETURNED, never thrown
// (ADR-6 / BR-4). Shapes conform to the TERMINAL schema (schemas.js).
// ===========================================================================

// blocked — a user-answerable halt. The TERMINAL contract names the discriminant
// `state` (NOT `terminal`); schemas are the source of truth, so the constructor
// emits `state`. `reason` is a short top-level slug string; `detail` is the
// CLOSED halt payload object (`{questions?, reason?, detail?}`) the orchestrator
// surfaces — on resume the answer is threaded via args.answers[id]. `id` lets the
// top-level merge-sequencing barrier correlate the halt back to its REQ. Keys
// that were not supplied are omitted so the value validates against the closed
// TERMINAL schema (no `detail: undefined` smuggled past additionalProperties:false).
// (ADR-6, ADR-7, ADR-12, BR-5)
function blocked(id, reason, detail) {
  return terminalValue('blocked', id, reason, detail);
}

// failed — a non-user-answerable terminal failure (e.g. no worktree). Distinct
// from `blocked`: there is no question for the user to answer. Same `state`
// discriminant + closed payload shape as `blocked`. (ADR-7)
function failed(id, reason, detail) {
  return terminalValue('failed', id, reason, detail);
}

// terminalValue — shared TERMINAL builder for the halt/failure constructors. The
// `detail` argument is normalized to the closed payload object: a plain string is
// wrapped as `{detail}` (so legacy two-string call sites still validate), an
// object is passed through, and a missing value omits the key entirely. Pure JS;
// no Date.now / Math.random / fs. (ADR-6, ADR-7)
function terminalValue(state, id, reason, detail) {
  const out = { state, id };
  if (reason !== undefined && reason !== null) out.reason = reason;
  if (detail !== undefined && detail !== null) {
    out.detail = typeof detail === 'string' ? { detail } : detail;
  }
  return out;
}

// ===========================================================================
// Prompt builders. The script has no shell/fs, so each prompt instructs the
// leaf agent on the exact commands to run and the structured data to return.
// Worktree paths obey the REQ-263 absolute-path / dispatch-line contract; the
// base is ALWAYS `origin/<integrationBranch>`, never a hardcoded `main`.
// (ADR-3, ADR-4, BR-2)
// ===========================================================================

function preflightPrompt(reqs) {
  return [
    'You are the Preflight eligibility scorer for an /sprint --workflow run.',
    `Candidate REQ ids: ${reqs.join(', ') || '(none)'}.`,
    '',
    'For EACH candidate REQ, run the necessary git/gh and file reads and report:',
    '  - id: the REQ id.',
    '  - eligible: true ONLY if its requirement.md status is "approved" (or',
    '    later) AND it has a tasks directory AND it is not already fully merged.',
    '  - reason: a short human-readable reason when NOT eligible.',
    '  - integrationBranch: the resolved integration branch for the primary',
    '    repo — "staging" in a two-branch repo, else "main". NEVER hardcode',
    '    "main"; resolve it from the repo. Worktrees later base on',
    '    origin/<integrationBranch>. (BUG-060, LESSON-036)',
    '  - touchedRepos: the repo ids this REQ touches (for later cross-repo',
    '    merge sequencing).',
    '',
    'Rank eligible REQs in a sensible order (e.g. fewest blockers first). Return',
    'ONLY the schema object — do not create worktrees or modify anything here.',
  ].join('\n');
}

function phase0Prompt(id) {
  return [
    `Phase 0 for ${id}: create (or reuse) the persistent per-REQ worktree and`,
    'record it in pipeline-state.json. This is the ONLY worktree used across',
    'Phases 0–8 (BR-2); do not use per-agent ephemeral worktrees.',
    '',
    'Steps:',
    `  1. Resolve the integration branch for each repo ${id} touches (two-branch`,
    '     repo → "staging", else "main"). NEVER hardcode "main". (BUG-060)',
    '  2. git fetch origin, then for each touched repo create the worktree at',
    `     <repoRoot>/.worktrees/${id} based on origin/<integrationBranch>`,
    '     (e.g. `git worktree add <abs-path> -b feat/<id>-... origin/<branch>`).',
    '     IDEMPOTENT: if that worktree already exists (resume), reuse it — do',
    '     NOT recreate or reset it. (AC-7)',
    '  3. Record the ABSOLUTE worktree path in',
    '     pipeline-state.json.repos[<repo>].worktree for every touched repo.',
    '     Absolute paths only — honor the REQ-263 dispatch-line contract.',
    '  4. Mark the primary repo (LESSON-002 cross-repo primary handling).',
    '',
    'Return the REPOS schema object: one entry per touched repo with repo,',
    'worktree (absolute), integrationBranch, primary, merged.',
  ].join('\n');
}

function phase1ValidatePrompt(id, worktree) {
  return [
    `Phase 1 for ${id}: validate the SPEC (requirement.md) in worktree`,
    `${worktree}. Run the equivalent of /validate on the requirement: confirm`,
    'BRs/ACs are testable, the System Model is coherent, and the spec is',
    'implementation-ready. Work entirely within the absolute worktree path.',
    '',
    'Return the VERDICT schema object: pass=true if the spec is ready; else',
    'pass=false with reason + detail describing exactly what must be fixed.',
  ].join('\n');
}

function phase1FixPrompt(id, worktree) {
  return (verdict) =>
    [
      `Phase 1 fix for ${id} in worktree ${worktree}: the spec validation`,
      'failed. Apply the minimal targeted edits to requirement.md to address',
      'the validator feedback, then stop (the script will re-validate).',
      '',
      `Validator reason: ${verdict.reason || '(none)'}`,
      `Validator detail: ${verdict.detail || '(none)'}`,
    ].join('\n');
}

function explorePrompt(id, worktree, agentType) {
  return [
    `Explore the codebase for ${id} (${agentType}) in worktree ${worktree}.`,
    'You are READ-ONLY. Produce your specialist exploration report to feed the',
    'architect — precedents, architecture map, or integration points per your',
    'role. Operate entirely within the absolute worktree path.',
  ].join('\n');
}

function architectPrompt(id, worktree, exploreReports) {
  return [
    `Phase 2 architect for ${id} in worktree ${worktree}: synthesize the`,
    'exploration reports below into a tiered task plan. Group tasks into',
    'dependency tiers; tasks within a tier MUST touch disjoint files (this is',
    'what makes serial-in-shared-worktree Phase 4 safe). Write the task files',
    'under the spec\'s tasks/ directory and return the TASKS schema object.',
    '',
    'Exploration reports (JSON):',
    JSON.stringify(exploreReports),
  ].join('\n');
}

function phase3ValidatePrompt(id, worktree) {
  return [
    `Phase 3 for ${id}: validate the ARCHITECTURE + TASKS in worktree`,
    `${worktree}. Run the equivalent of /validate on architecture.md and the`,
    'task breakdown: ADRs sound, tasks complete and correctly tiered, disjoint',
    'files within each tier, acceptance criteria testable.',
    '',
    'Return the VERDICT schema object: pass=true if ready for implementation;',
    'else pass=false with reason + detail.',
  ].join('\n');
}

function phase3FixPrompt(id, worktree) {
  return (verdict) =>
    [
      `Phase 3 fix for ${id} in worktree ${worktree}: the architecture/tasks`,
      'validation failed. Apply minimal targeted edits to architecture.md and/or',
      'the task files to address the feedback, then stop (the script re-validates).',
      '',
      `Validator reason: ${verdict.reason || '(none)'}`,
      `Validator detail: ${verdict.detail || '(none)'}`,
    ].join('\n');
}

// --- Phase 4 prompt builders (serial implement) -----------------------------

function implementPrompt(id, worktree, task) {
  return [
    `Phase 4 implement for ${id}: task ${task.id} — ${task.title || '(untitled)'}`,
    `in worktree ${worktree}.`,
    'You are the SOLE writer in this shared worktree right now (the engine runs',
    'Phase-4 tasks serially — never assume a concurrent writer). Implement this',
    'ONE task end-to-end: code + tests, following conventions.md and',
    'architecture.md, then run the test suite and ensure it passes. Commit your',
    'work in the worktree with the conventional message for this task. Operate',
    'entirely within the absolute worktree path.',
    task.repo ? `Target repo for this task: ${task.repo}.` : '',
  ].filter(Boolean).join('\n');
}

function phase4StatePrompt(id, worktree, task) {
  return [
    `Phase 4 state update for ${id} in worktree ${worktree}: record that task`,
    `${task.id} is complete. Append "${task.id}" to`,
    'pipeline-state.json.phase4.completedTasks (create the phase4 object if',
    'absent), remove it from failedTasks if present, and leave every other field',
    'untouched. This is a pure state write — do not modify code or run tests.',
  ].join('\n');
}

// --- Phase 5 prompt builders (review panel + consolidation) -----------------

function manifestPrompt(id, repos) {
  const repoList = (repos || []).map((r) => `${r.repo} @ ${r.worktree}`).join('; ');
  return [
    `Phase 5 cross-repo manifest for ${id}: summarize the change set this REQ`,
    'produced across every touched repo, so the architecture-reviewer can reason',
    'about cross-repo coupling. For EACH touched repo, run the equivalent of',
    '`git -C <worktree> diff --stat origin/<integrationBranch>...HEAD` and report',
    'the changed files / modules as a flat list.',
    '',
    `Touched repos (repo @ absolute-worktree): ${repoList || '(none)'}.`,
    '',
    'Return the TASKS schema object where each entry is one changed area: id (a',
    'short slug), title (what changed), and repo (the owning repo). Read-only —',
    'do not modify anything.',
  ].join('\n');
}

function reviewPrompt(id, worktree, member, repo, manifest) {
  const lines = [
    `Phase 5 review for ${id} (${member.dimension}) in worktree ${worktree},`,
    `repo ${repo}. You are READ-ONLY. Review the change set on this branch for`,
    `your ${member.dimension} dimension and Report findings ONLY — do not fix,`,
    'do not modify any file, do not open a PR.',
    '',
    'Return the FINDINGS schema object: dimension =',
    `"${member.dimension}", and a findings[] array. For each finding set`,
    'severity (Critical|Major|Minor|Nit), file, line?, title, detail?,',
    'suggestedFix?, mustFix (true ⇒ blocks merge), userFacing (reflector only:',
    'true ⇒ a question the human must answer before merge), lessonId?, and',
    'fromCandidate=false (v1 runs candidate-less — no pre-pass).',
  ];
  if (member.dimension === 'reflector') {
    lines.push(
      '',
      'As the reflector: if the change raises a decision only the human can make',
      '(a product/UX/scope question, an ambiguous requirement), emit it as a',
      'finding with userFacing=true and the question in `title`. The engine HALTS',
      'the REQ on any such finding so the user can answer.',
    );
  }
  if (member.dimension === 'architecture' && manifest) {
    lines.push(
      '',
      'Cross-repo change manifest (for cross-repo coupling analysis):',
      JSON.stringify(manifest),
    );
  }
  return lines.join('\n');
}

function fixFindingsPrompt(id, worktree, blocking) {
  return [
    `Phase 5 fix for ${id} in worktree ${worktree}: the review panel surfaced`,
    'blocking findings (Critical or mustFix). You are the SOLE writer (serial).',
    'Apply the minimal targeted fixes to resolve EVERY blocking finding below,',
    'keep the test suite green, and commit in the worktree. Then stop — the',
    'engine re-verifies the affected reviewer dimensions (≤1 loop).',
    '',
    'Blocking findings (JSON):',
    JSON.stringify(blocking || []),
  ].join('\n');
}

// --- Phase 6 prompt builder (open PR(s)) ------------------------------------

// openPRsPrompt — instruct ONE IO agent to push each touched repo's branch and
// open its PR against the RESOLVED integration branch (read from the repo record,
// NEVER a hardcoded "main" — BUG-060 / LESSON-036). One PR per touched repo. The
// agent returns the PRS schema object (repo + url [+ number]). (ADR-3, BR-2)
function openPRsPrompt(id, repos) {
  const repoList = (repos || [])
    .map((r) => `${r.repo} @ ${r.worktree} (base origin/${r.integrationBranch || '<resolve>'})`)
    .join('; ');
  return [
    `Phase 6 for ${id}: open the pull request(s) for this REQ. One PR per touched`,
    'repo, each based on that repo\'s RESOLVED integration branch — NEVER hardcode',
    '"main"; use the integrationBranch recorded in the repo record (two-branch repo',
    '→ "staging", else "main"). (BUG-060, LESSON-036)',
    '',
    'For EACH touched repo (repo @ absolute-worktree, base branch shown):',
    `  ${repoList || '(none)'}`,
    '',
    'Steps per repo, run entirely within the absolute worktree path:',
    '  1. Push the feature branch: `git -C <worktree> push -u origin HEAD`.',
    '  2. Open the PR against the integration branch:',
    '     `gh pr create --base <integrationBranch> --head <featureBranch>`',
    '     --fill (or a concise title/body summarizing the REQ). If a PR already',
    '     exists for this branch (resume), reuse it — do NOT open a duplicate.',
    '  3. Capture the PR url (and number if available).',
    '',
    'Return the PRS schema object: one entry per touched repo with repo, url, and',
    'number when known. Do not merge anything in this phase.',
  ].join('\n');
}

// --- Phase 7 prompt builder (PR cleanup + CI watch, NO re-review) -----------

// cleanupAndWatchCIPrompt — ONE IO agent runs the per-PR sanity check (diff is
// coherent, no stray/debug files, branch is the right base) and then BLOCKS until
// `gh pr checks` reports all required checks green for every PR. Explicitly NOT a
// re-review (Phase 5 already gated correctness); this is the operational CI wait.
function cleanupAndWatchCIPrompt(id, prs) {
  const prList = (prs || [])
    .map((p) => `${p.repo}: ${p.url}`)
    .join('; ');
  return [
    `Phase 7 for ${id}: PR cleanup + CI watch. This is NOT a code re-review`,
    '(Phase 5 already reviewed); it is the operational sanity check + CI gate.',
    '',
    `PRs to process (repo: url): ${prList || '(none)'}.`,
    '',
    'For EACH PR:',
    '  1. Sanity check: `gh pr view <url> --json files,baseRefName` — confirm the',
    '     diff is coherent (no stray build artifacts, debug logs, or unrelated',
    '     files) and the base branch is the intended integration branch.',
    '  2. Watch CI to completion: `gh pr checks <url> --watch` (or poll',
    '     `gh pr checks <url>` until no check is pending). Wait until every',
    '     REQUIRED check is green.',
    '',
    'Do NOT modify code and do NOT merge here. Report which PRs are green and any',
    'that failed CI (the script gates merge on this in Phase 8).',
  ].join('\n');
}

// --- Phase 8 prompt builders (wrapup / merge + gh re-verification) ----------

// mergePrompt — instruct the IO agent to self-merge a SINGLE-REPO REQ. Per the
// legacy topology (pipeline-runner.md Phase 8), `gh pr merge --delete-branch`
// MUST run from the PARENT repo path, not the worktree, because git refuses to
// delete a branch checked out by a worktree. After a successful merge the agent
// sets pipeline-state.json.repos[<repo>].merged = true immediately (resumable,
// no double-merge). The CRITICAL re-verification gate (gh pr view) is enforced by
// the SCRIPT in a SEPARATE leaf (see verifyMergedPrompt) — claim ≠ truth (BR-6).
function mergePrompt(id, repo, pr) {
  return [
    `Phase 8 merge for ${id}: this is a SINGLE-REPO REQ, so YOU own the merge.`,
    `Merge PR ${pr.url} (repo ${repo.repo}) into origin/${repo.integrationBranch || 'main'}.`,
    '',
    'Steps:',
    '  1. Confirm the PR is OPEN and MERGEABLE with CI green',
    `     (\`gh pr view ${pr.url} --json state,mergeStateStatus\`). If it is NOT`,
    '     mergeable due to a MERGE CONFLICT, STOP and report mergeConflict=true —',
    '     do NOT force anything.',
    `  2. Merge from the PARENT repo path (\`${repo.worktree}\`\'s repo root), NOT`,
    '     the worktree, because git refuses to delete a branch checked out by a',
    `     worktree: \`gh pr merge ${pr.url} --squash --delete-branch\`.`,
    '  3. Immediately set pipeline-state.json.repos[<repo>].merged = true.',
    '',
    'Report mergeConflict (true ONLY on a real merge conflict) and merged (true if',
    'you ran the merge command without error). The script independently re-verifies',
    'the merge with `gh pr view` — your claim is not accepted on its own.',
  ].join('\n');
}

// verifyMergedPrompt — the "claim ≠ truth" re-verification leaf (BR-6, ADR-7).
// For each PR the agent runs `gh pr view <url> --json state,mergedAt` and reports
// the GROUND TRUTH (state + whether mergedAt is set). The script decides merged /
// not-merged off THIS, never off the merge agent's self-claim.
function verifyMergedPrompt(id, prs) {
  const prList = (prs || []).map((p) => `${p.repo}: ${p.url}`).join('; ');
  return [
    `Phase 8 verification for ${id}: re-verify the TRUE merge state of each PR.`,
    'Do NOT merge or modify anything — this is a read-only ground-truth check that',
    'the script trusts over any earlier merge claim. (BR-6, Verify Don\'t Trust)',
    '',
    `For EACH PR (repo: url): ${prList || '(none)'}`,
    '  run `gh pr view <url> --json state,mergedAt` and report:',
    '    - repo, url',
    '    - state: the literal state string (OPEN | MERGED | CLOSED)',
    '    - mergedAt: the timestamp string if set, else omit it',
    '',
    'Return the PR_VERIFY schema object: one entry per PR.',
  ].join('\n');
}

// ===========================================================================
// Phase implementations — Phases 4–8. None of these throw: every phase RETURNS
// values (the halt contract — a halt is a returned `{state:'blocked'}`, never a
// throw, ADR-6). Phase 4–5 are TASK-058; Phase 6–8 + the cross-REQ merge barrier
// are TASK-059.
// ===========================================================================

// Phase 4 — serial implement in the single REQ worktree. (ADR-5, BR-3)
//
// Tasks flow in dependency-tier order; WITHIN the shared REQ worktree there is
// exactly ONE writer at a time — task-implementers run SERIALLY (no parallel()).
// This is the load-bearing safety property: a single git index, no concurrent
// file writes, so per-tier disjoint-file planning (Phase 2) plus serial
// execution keeps the shared worktree consistent. Per-task worktrees and
// intra-tier parallelism are explicitly out of scope for v1 (OQ-5). After each
// task an IO agent records progress into pipeline-state.json.phase4 (the script
// has no fs — every state write is an agent leaf, ADR-3).
async function implement(id, P, worktree, tasks) {
  // Sort into ascending dependency tiers. A missing `tier` sorts as tier 0 so a
  // flat (untiered) plan still runs in array order. Sorting is pure JS — the
  // script owns ordering; the agents own the writes. (ADR-3, ADR-5)
  const ordered = orderByTier(tasks);

  for (const task of ordered) {
    // ONE writer: await each task-implementer before dispatching the next. Using
    // a serial for-loop (NOT parallel()) is what prevents git-index contention
    // in the shared worktree. task-implementer is the unchanged specialist.
    await agent(implementPrompt(id, worktree, task), {
      ...P,
      label: `${id} phase4-${task.id}`,
      agentType: 'task-implementer',
    });

    // Record this task as completed in pipeline-state.json.phase4 via an IO
    // agent (the script cannot touch the filesystem). Done per-task so a resume
    // after a mid-tier interruption replays only the unfinished tasks.
    await agent(phase4StatePrompt(id, worktree, task), {
      ...P,
      label: `${id} phase4-state-${task.id}`,
      // Default subagent (no agentType) — a generic state-write IO worker.
    });
  }

  // Touched-repo change manifest is computed in Phase 5 (verify) from the
  // worktree, not here — no barrier, single read at panel time. (AC re: manifest)
  return { tasks: ordered.length };
}

// orderByTier — pure JS stable tier sort. Tasks without an explicit `tier` are
// treated as tier 0 (a flat plan keeps its array order). Stable so tasks within
// the same tier preserve the architect's intra-tier ordering. (ADR-5)
function orderByTier(tasks) {
  return (tasks || [])
    .map((t, i) => ({ t, i, tier: typeof t.tier === 'number' ? t.tier : 0 }))
    .sort((a, b) => (a.tier - b.tier) || (a.i - b.i))
    .map((x) => x.t);
}

// Phase 5 — parallel review panel + deterministic consolidation. (ADR-7, BR-7)
//
// Per touched repo the panel fans out: the reflector + the 5 reviewers run
// CONCURRENTLY (read-only, so safe — the only writer was Phase 4). Each returns
// a validated FINDINGS object. The mechanical consolidation — dedupe within a
// repo, cross-repo tagging, severity ranking, and the Critical/mustFix gate —
// runs as PURE JS in `dedupeAndRank()`; NO agent is in that loop (BR-7). A
// reflector `userFacing` finding is a user-answerable halt → RETURN blocked
// (never throw, ADR-6). v1 runs the panel candidate-less — the Kimi pre-pass is
// skipped and wired only by TASK-060 (BR-8).
//
// Returns `true` when the panel is clean / non-blocking (the REQ proceeds to
// Phase 6); returns a `{state:'blocked'}` value on a reflector question.
async function verify(id, P, worktree, repos) {
  // The PANEL: agentType + the dimension label it reports under (the FINDINGS
  // `dimension` enum is distinct from the agentType name). The reflector leads;
  // the 5 reviewers follow. (schemas.js PANEL_DIMENSIONS / REVIEWER_DIMENSIONS)
  const PANEL = panelMembers();

  // Cross-repo change manifest — computed ONCE by a single IO agent that reads
  // each touched repo's worktree diff (the script has no shell). Passed to the
  // architecture-reviewer so it can reason about cross-repo coupling; no barrier
  // beyond this single read. (AC: architecture-reviewer receives the manifest)
  const MANIFEST = await agent(manifestPrompt(id, repos), {
    ...P,
    label: `${id} phase5-manifest`,
    schema: TASKS, // reuse the lightweight {tasks:[{id,title,repo,...}]} shape as
    // a generic per-repo change list; the architecture-reviewer reads it as
    // prose context, not as a strict contract. (kept schema-validated, ADR-7)
  });

  // Run the full panel per touched repo. Each repo's reflector + 5 reviewers is
  // ONE parallel() fan-out (single barrier per repo). A failed thunk yields null
  // and is filtered — a dropped reviewer never poisons the consolidation.
  const findingsByRepo = {};
  for (const r of repos) {
    const repoWt = r.worktree || worktree;
    const panelFindings = (
      await parallel(
        PANEL.map((m) => () =>
          agent(reviewPrompt(id, repoWt, m, r.repo, m.dimension === 'architecture' ? MANIFEST : null), {
            ...P,
            label: `${id} phase5-${r.repo}-${m.dimension}`,
            schema: FINDINGS,
            agentType: m.agentType,
          }),
        ),
      )
    ).filter(Boolean);
    findingsByRepo[r.repo] = panelFindings;
  }

  // A reflector `userFacing` finding is a question for the user — HALT. Checked
  // BEFORE consolidation/fix so we never silently fix past an open question.
  // (BR-4 halt #2, System Model event halt:reflector-question)
  const questions = reflectorQuestions(findingsByRepo);
  if (questions.length > 0) {
    return blocked(id, 'reflector-questions', { questions });
  }

  // Deterministic consolidation: dedupe within repo, tag cross-repo issues, rank
  // by severity, and decide whether merge is blocked (any Critical or mustFix).
  let consolidated = dedupeAndRank(findingsByRepo);

  if (consolidated.blocks) {
    // Dispatch ONE serial fix pass in the shared worktree (one writer, ADR-5)
    // addressing the blocking findings, then conditionally RE-VERIFY only the
    // (repo,dimension) pairs that had fixes — and only the 5 REVIEWERS, never
    // the reflector (a reflector re-run could only surface a NEW question, which
    // is out of this ≤1 re-verify loop's contract). Bounded to ONE loop. (AC-5)
    await agent(fixFindingsPrompt(id, worktree, consolidated.blocking), {
      ...P,
      label: `${id} phase5-fix`,
      agentType: 'task-implementer',
    });

    // The (repo,dimension) pairs that were touched by the fix — recompute the
    // panel for exactly those, reviewers-only. `fixedPairs` is pure JS over the
    // blocking findings: every blocking finding's (repo,dimension) is a pair to
    // re-check. The reflector dimension is excluded by construction.
    const pairs = fixedPairs(consolidated.blocking);
    const reverified = {};
    for (const repoId of Object.keys(pairs)) {
      const r = repos.find((x) => x.repo === repoId) || {};
      const repoWt = r.worktree || worktree;
      const dims = pairs[repoId]; // reviewer dimensions only
      const members = PANEL.filter((m) => m.dimension !== 'reflector' && dims.includes(m.dimension));
      const re = (
        await parallel(
          members.map((m) => () =>
            agent(reviewPrompt(id, repoWt, m, repoId, m.dimension === 'architecture' ? MANIFEST : null), {
              ...P,
              label: `${id} phase5-reverify-${repoId}-${m.dimension}`,
              schema: FINDINGS,
              agentType: m.agentType,
            }),
          ),
        )
      ).filter(Boolean);
      reverified[repoId] = re;
    }

    // Merge the re-verified reviewer findings over the original panel result:
    // for a re-checked (repo,dimension) the fresh findings REPLACE the stale
    // ones; everything else (including the reflector's, untouched) is kept.
    const merged = mergeReverified(findingsByRepo, reverified);
    consolidated = dedupeAndRank(merged);
    // ≤1 loop: we do NOT re-fix here. If it still blocks, the gate stands and the
    // PR phase will carry the unresolved Critical/mustFix forward for the user.
  }

  // Surface the consolidated outcome for progress/journal visibility. The actual
  // merge-readiness gate is enforced downstream (Phase 8) off this same data;
  // here we only log and return the non-halt control signal.
  log(
    `${id} Phase 5: ${consolidated.findings.length} consolidated finding(s) `
    + `across ${repos.length} repo(s); blocks=${consolidated.blocks}.`,
  );
  return true;
}

// ===========================================================================
// dedupeAndRank(findingsByRepo) — PURE JS Phase-5 consolidation. (BR-7, ADR-7)
//
//   findingsByRepo: { [repoId]: FINDINGS[] }   // one FINDINGS per panel member
//
// Returns:
//   {
//     findings: ConsolidatedFinding[],  // deduped (within repo), severity-ranked
//     blocking: ConsolidatedFinding[],  // the Critical/mustFix subset
//     blocks:   boolean,                // true ⇒ NOT merge-ready (gate)
//   }
// where a ConsolidatedFinding = the FINDINGS finding + { repo, dimension,
// crossRepo:boolean }.
//
// Rules (mirrors /review's gate — any Critical ⇒ not merge-ready):
//   - DEDUPE within a repo: findings with the same (file, normalized-title) key
//     collapse to one; the highest severity / mustFix-true wins; dimensions are
//     unioned so the survivor records every reviewer that raised it.
//   - CROSS-REPO TAG: a (file, title) key seen in MORE THAN ONE repo is flagged
//     crossRepo:true on every surviving copy.
//   - RANK by severity (Critical > Major > Minor > Nit), then by repo then file
//     for a stable, deterministic order.
//   - BLOCK: any surviving finding with severity 'Critical' OR mustFix === true.
// No Date.now / Math.random / fs — fully deterministic. (runtime contract)
// ===========================================================================
function dedupeAndRank(findingsByRepo) {
  const SEVERITY_RANK = { Critical: 0, Major: 1, Minor: 2, Nit: 3 };

  // 1) Flatten every panel member's findings, tagging each with its repo and the
  //    reporting dimension (the FINDINGS object carries the dimension once).
  const flat = [];
  for (const repo of Object.keys(findingsByRepo)) {
    for (const fset of findingsByRepo[repo] || []) {
      const dimension = fset.dimension;
      for (const f of fset.findings || []) {
        flat.push({ ...f, repo, dimension, crossRepo: false });
      }
    }
  }

  // 2) Dedupe WITHIN a repo on (file, normalized-title). The survivor keeps the
  //    most severe severity, OR-s mustFix/userFacing, and unions the dimensions.
  const byRepoKey = new Map(); // `${repo} ${key}` -> survivor
  for (const f of flat) {
    const key = dedupeKey(f);
    const rk = `${f.repo} ${key}`;
    const prev = byRepoKey.get(rk);
    if (!prev) {
      byRepoKey.set(rk, { ...f, dimensions: [f.dimension] });
      continue;
    }
    // Merge into the survivor.
    if (SEVERITY_RANK[f.severity] < SEVERITY_RANK[prev.severity]) {
      prev.severity = f.severity;
    }
    prev.mustFix = prev.mustFix || f.mustFix === true;
    prev.userFacing = prev.userFacing || f.userFacing === true;
    if (!prev.dimensions.includes(f.dimension)) prev.dimensions.push(f.dimension);
  }
  const deduped = Array.from(byRepoKey.values());

  // 3) Cross-repo tag: a (file, normalized-title) key present in >1 repo gets
  //    crossRepo:true on every surviving copy.
  const repoCountByKey = new Map();
  for (const f of deduped) {
    const key = dedupeKey(f);
    if (!repoCountByKey.has(key)) repoCountByKey.set(key, new Set());
    repoCountByKey.get(key).add(f.repo);
  }
  for (const f of deduped) {
    if (repoCountByKey.get(dedupeKey(f)).size > 1) f.crossRepo = true;
  }

  // 4) Rank: severity, then repo, then file — stable & deterministic.
  deduped.sort((a, b) =>
    (SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])
    || cmp(a.repo, b.repo)
    || cmp(a.file || '', b.file || '')
    || cmp(a.title || '', b.title || ''));

  // 5) Gate: any Critical OR mustFix blocks merge.
  const blocking = deduped.filter((f) => f.severity === 'Critical' || f.mustFix === true);

  return { findings: deduped, blocking, blocks: blocking.length > 0 };
}

// dedupeKey — the within-repo / cross-repo identity of a finding: its file plus
// a normalized title (lowercased, collapsed whitespace) so trivial wording
// differences between reviewers still collapse. Pure. (dedupeAndRank helper)
function dedupeKey(f) {
  const title = (f.title || '').toLowerCase().replace(/\s+/g, ' ').trim();
  return `${f.file || ''} ${title}`;
}

// cmp — deterministic string comparator (no locale dependence, so two runs on
// two machines rank identically). (dedupeAndRank helper)
function cmp(a, b) {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

// reflectorQuestions — pure JS: collect the user-facing question titles from any
// reflector finding marked `userFacing`. A non-empty result is the Phase-5 halt.
// (BR-4 halt #2)
function reflectorQuestions(findingsByRepo) {
  const out = [];
  for (const repo of Object.keys(findingsByRepo)) {
    for (const fset of findingsByRepo[repo] || []) {
      if (fset.dimension !== 'reflector') continue;
      for (const f of fset.findings || []) {
        if (f.userFacing === true) out.push(f.title || f.detail || '(unspecified question)');
      }
    }
  }
  return out;
}

// fixedPairs — pure JS: from the blocking findings, the set of REVIEWER
// dimensions to re-check per repo. The reflector is excluded (re-verify reruns
// only the 5 reviewers). Returns { [repo]: dimension[] }. (AC-5)
function fixedPairs(blocking) {
  const REVIEWER_DIMS = ['correctness', 'quality', 'architecture', 'test-coverage', 'security'];
  const out = {};
  for (const f of blocking || []) {
    // A consolidated finding records every dimension that raised it; re-check
    // each reviewer dimension that did (skip the reflector). Use `dimensions`
    // (the unioned list) when present, else the single `dimension`.
    const dims = f.dimensions || [f.dimension];
    for (const d of dims) {
      if (!REVIEWER_DIMS.includes(d)) continue;
      if (!out[f.repo]) out[f.repo] = [];
      if (!out[f.repo].includes(d)) out[f.repo].push(d);
    }
  }
  return out;
}

// mergeReverified — pure JS: overlay the re-verified reviewer FINDINGS onto the
// original per-repo panel results. For a re-checked (repo,dimension) the fresh
// findings REPLACE the stale ones; the reflector's findings and any untouched
// dimension are preserved verbatim. (re-verify merge, AC-5)
function mergeReverified(original, reverified) {
  const merged = {};
  for (const repo of Object.keys(original)) {
    const reDims = new Set((reverified[repo] || []).map((f) => f.dimension));
    // Keep original sets whose dimension was NOT re-checked.
    const kept = (original[repo] || []).filter((f) => !reDims.has(f.dimension));
    merged[repo] = [...kept, ...(reverified[repo] || [])];
  }
  // Repos that only appear in reverified (shouldn't happen) are appended.
  for (const repo of Object.keys(reverified)) {
    if (!merged[repo]) merged[repo] = reverified[repo];
  }
  return merged;
}

// panelMembers — the 6 review-panel members: the reflector plus the 5 reviewers.
// Each entry maps the FINDINGS `dimension` label to the agentType that produces
// it (the two namespaces differ). Pure literal builder. (schemas PANEL_DIMENSIONS)
function panelMembers() {
  return [
    { dimension: 'reflector', agentType: 'reflector' },
    { dimension: 'correctness', agentType: 'correctness-reviewer' },
    { dimension: 'quality', agentType: 'quality-reviewer' },
    { dimension: 'architecture', agentType: 'architecture-reviewer' },
    { dimension: 'test-coverage', agentType: 'test-auditor' },
    { dimension: 'security', agentType: 'security-auditor' },
  ];
}

// Phase 6 — open PR(s) based on the RESOLVED integration branch. ONE IO agent
// pushes each touched repo's branch and opens its PR against
// origin/<integrationBranch> (never a hardcoded main — BUG-060). Returns the PRS
// schema object the later phases re-verify. (ADR-3, ADR-7, BR-2)
async function openPRs(id, P, worktree, repos) {
  const PR_STATE = await agent(openPRsPrompt(id, repos), {
    ...P,
    label: `${id} phase6-open-prs`,
    schema: PRS,
    // Default workflow subagent (no agentType) — a generic git/gh IO worker
    // driven by the inline prompt, NOT a specialist. (ethos #6)
  });
  return PR_STATE;
}

// Phase 7 — PR cleanup + CI watch (NO re-review). ONE IO agent runs the per-PR
// sanity check and BLOCKS until `gh pr checks` is green for every PR. Phase 5
// already gated correctness; this is purely the operational CI wait, so no
// reviewer/specialist agent is involved. (ADR-3)
async function cleanupAndWatchCI(id, P, worktree, PR_STATE) {
  const prs = (PR_STATE && PR_STATE.prs) || [];
  await agent(cleanupAndWatchCIPrompt(id, prs), {
    ...P,
    label: `${id} phase7-cleanup-ci`,
    // Default workflow subagent (no agentType) — a generic gh IO worker.
  });
}

// Phase 8 — wrapup / merge with gh re-verification + TERMINAL return. (ADR-7,
// ADR-12, BR-6)
//
// Topology (mirrors the legacy pipeline-runner Phase-8 rule, but executed by the
// SCRIPT via leaves, not a monolithic agent):
//   - SINGLE-REPO REQ (exactly one touched repo): YOU own the merge. A merge
//     agent self-merges from the parent path; the script then RE-VERIFIES the
//     true state with `gh pr view` and only on a verified MERGED returns
//     {state:'merged'}. A real merge conflict → blocked(id,'merge-conflict').
//   - CROSS-REPO REQ (>1 touched repo): STOP at pr-ready — the cross-REQ merge
//     barrier (ADR-12, top-level) sequences these merges. Return {state:'pr-ready'}.
//
// EVERY merged/pr-ready claim is re-verified via `gh pr view --json state,mergedAt`
// before it is returned (claim ≠ truth, BR-6). `repos[*].merged` is written to
// state by the merge agent immediately after each successful merge (resumable,
// no double-merge — AC-7). Returns a value conforming to the TERMINAL schema.
async function wrapupAndMerge(id, P, worktree, repos, PR_STATE) {
  const prs = (PR_STATE && PR_STATE.prs) || [];
  const touched = repos || [];

  // CROSS-REPO REQ: do NOT self-merge — the top-level ADR-12 barrier sequences
  // these. Still re-verify the PRs are real/open before claiming pr-ready (BR-6).
  if (touched.length > 1) {
    const verifiedPrs = await verifyPrStates(id, P, prs);
    return { state: 'pr-ready', id, prs: stripVerifyMarkers(verifiedPrs) };
  }

  // SINGLE-REPO REQ: this engine owns the merge. With no touched repo there is
  // nothing to merge — treat as a non-user-answerable failure (mirrors Phase 0's
  // no-worktree failure; never a silent success).
  const repo = touched[0];
  if (!repo) {
    return failed(id, 'phase8-no-repo', 'Phase 8 found no touched repo to merge.');
  }
  const pr = prs.find((p) => p.repo === repo.repo) || prs[0];
  if (!pr) {
    return failed(id, 'phase8-no-pr', 'Phase 8 found no PR to merge for the touched repo.');
  }

  // Dispatch the self-merge IO agent (parent-path merge + immediate state write).
  const mergeResult = await agent(mergePrompt(id, repo, pr), {
    ...P,
    label: `${id} phase8-merge`,
    schema: MERGE_RESULT_SCHEMA,
    // Default workflow subagent (no agentType) — a generic git/gh/state IO worker.
  });

  // A real merge conflict is a user-answerable halt — RETURN blocked, never throw.
  if (mergeResult && mergeResult.mergeConflict === true) {
    return blocked(id, 'merge-conflict', {
      reason: 'merge conflict — the PR could not be merged cleanly',
      detail: mergeResult.detail || '',
    });
  }

  // CLAIM ≠ TRUTH: ignore the agent's `merged` self-claim; re-verify the true
  // state with `gh pr view` in a SEPARATE read-only leaf and accept `merged`
  // ONLY when the ground truth says so (BR-6).
  const verifiedPrs = await verifyPrStates(id, P, prs);
  if (allMerged(verifiedPrs)) {
    return { state: 'merged', id, prs: stripVerifyMarkers(verifiedPrs) };
  }

  // The agent may have CLAIMED merged, but the gh re-verification disagrees — the
  // false claim is caught and corrected here (AC-5). Surface it as a halt so the
  // user can investigate rather than silently reporting a non-merge as merged.
  return blocked(id, 'merge-unverified', {
    reason: 'merge claim could not be verified via gh pr view (state != MERGED)',
    detail: `verified: ${JSON.stringify(verifiedPrs)}`,
  });
}

// verifyPrStates — the "claim ≠ truth" gh re-verification, run as ONE read-only
// IO leaf (the script has no shell). Returns the PRS-shaped array (repo+url
// [+number]) the TERMINAL value carries, sourced from the ground-truth
// `gh pr view` read — NOT from any merge agent's self-claim. (BR-6, ADR-7)
async function verifyPrStates(id, P, prs) {
  if (!prs || prs.length === 0) return [];
  const verified = await agent(verifyMergedPrompt(id, prs), {
    ...P,
    label: `${id} phase8-verify`,
    schema: PR_VERIFY_SCHEMA,
    // Default workflow subagent (no agentType) — a read-only gh IO worker.
  });
  const rows = (verified && verified.prs) || [];
  // Stash the ground-truth state on each row so allMerged() can read it; the
  // TERMINAL `prs` shape keeps only repo/url/number, so map back to that here.
  return rows.map((row) => {
    const orig = prs.find((p) => p.url === row.url) || {};
    const out = { repo: row.repo, url: row.url, _state: row.state };
    if (typeof orig.number === 'number') out.number = orig.number;
    return out;
  });
}

// allMerged — pure JS: true only when EVERY verified PR row reports the gh
// ground-truth state 'MERGED'. The accepted proof of merge (BR-6). The internal
// `_state` marker is stripped before the rows go into the TERMINAL value (see
// stripVerifyMarkers). Empty input is NOT merged (nothing was confirmed).
function allMerged(verifiedPrs) {
  if (!verifiedPrs || verifiedPrs.length === 0) return false;
  return verifiedPrs.every((p) => p._state === 'MERGED');
}

// stripVerifyMarkers — pure JS: project each row down to the closed PRS/TERMINAL
// shape (repo, url, number only), dropping the internal `_state` marker so the
// rows validate against additionalProperties:false. Used just before a TERMINAL
// value is returned to the orchestrator. (ADR-7)
function stripVerifyMarkers(prs) {
  return (prs || []).map((p) => {
    const out = { repo: p.repo, url: p.url };
    if (typeof p.number === 'number') out.number = p.number;
    return out;
  });
}

// ===========================================================================
// Cross-REQ merge sequencing (ADR-12) — the post-pipeline barrier.
//
// Single-repo REQs already self-merged in Phase 8 (`state:'merged'`); they pass
// through here untouched. Cross-repo REQs stopped at `state:'pr-ready'`. This
// barrier merges those now, with one rule: REQs that share a touched sibling repo
// merge SERIALLY (a shared repo can take only one merge at a time without a
// rebase race), while REQs touching disjoint repo sets merge in PARALLEL. We
// group the pr-ready REQs into connected components over the "shares a repo"
// relation, run each component's REQs serially, and run the components
// concurrently via parallel(). (ADR-12, OQ-3 resolution; OQ-4 concurrency stays
// on the built-in cap + budget + max-5)
// ===========================================================================
async function sequenceCrossRepoMerges(results, todo) {
  const all = results || [];

  // touchedRepos per REQ id, from the Preflight eligibility records (the script's
  // own trusted data — not an agent claim).
  const reposById = {};
  for (const r of todo || []) reposById[r.id] = r.touchedRepos || [];

  // The REQs to sequence: only those still at `pr-ready`. Everything else
  // (merged / blocked / failed) is terminal already and passes through verbatim.
  const pending = all.filter((t) => t && t.state === 'pr-ready');
  if (pending.length === 0) return all;

  // Connected components over "shares a touched repo". groupCrossRepoReqs is pure
  // JS (union-find style) — deterministic, no Date.now/Math.random. Each group is
  // a list of REQ ids that must merge serially relative to one another.
  const groups = groupCrossRepoReqs(pending.map((t) => t.id), reposById);

  // Merge each group's REQs serially; run the groups concurrently. A failed thunk
  // yields null (parallel() contract) — we fall back to the pre-barrier terminal
  // so a sequencing hiccup never erases a REQ's result.
  const mergedByGroup = await parallel(
    groups.map((groupIds) => async () => {
      const out = [];
      for (const reqId of groupIds) {
        const term = pending.find((t) => t.id === reqId);
        out.push(await mergeCrossRepoReq(reqId, term));
      }
      return out;
    }),
  );

  // Flatten the per-group results and index the post-merge terminals by id.
  const updatedById = {};
  for (const group of mergedByGroup) {
    if (!group) continue; // a dropped group thunk — keep the originals below
    for (const term of group) updatedById[term.id] = term;
  }

  // Stitch the updated terminals back over the original results, preserving order
  // and leaving non-pr-ready REQs untouched.
  return all.map((t) => (t && updatedById[t.id]) ? updatedById[t.id] : t);
}

// mergeCrossRepoReq — merge ONE cross-repo REQ at the barrier: dispatch the merge
// IO agent (merges every touched-repo PR, writes repos[*].merged), then RE-VERIFY
// the true state with `gh pr view` and only on a verified all-MERGED upgrade the
// terminal to `state:'merged'`. A real merge conflict → blocked(merge-conflict);
// an unverifiable claim → blocked(merge-unverified) (claim ≠ truth, BR-6). On any
// agent drop the REQ keeps its `pr-ready` terminal (no false `merged`).
async function mergeCrossRepoReq(id, term) {
  const P = { phase: id };
  const prs = (term && term.prs) || [];
  if (prs.length === 0) return term;

  const mergeResult = await agent(crossRepoMergePrompt(id, prs), {
    ...P,
    label: `${id} merge-barrier`,
    schema: MERGE_RESULT_SCHEMA,
    // Default workflow subagent (no agentType) — a git/gh/state IO worker.
  });

  if (mergeResult && mergeResult.mergeConflict === true) {
    return blocked(id, 'merge-conflict', {
      reason: 'merge conflict during cross-REQ merge sequencing',
      detail: mergeResult.detail || '',
    });
  }

  // claim ≠ truth — re-verify before upgrading pr-ready → merged (BR-6).
  const verifiedPrs = await verifyPrStates(id, P, prs);
  if (allMerged(verifiedPrs)) {
    return { state: 'merged', id, prs: stripVerifyMarkers(verifiedPrs) };
  }
  return blocked(id, 'merge-unverified', {
    reason: 'cross-REQ merge claim could not be verified via gh pr view',
    detail: `verified: ${JSON.stringify(verifiedPrs)}`,
  });
}

// crossRepoMergePrompt — instruct the barrier merge agent to merge every PR of a
// cross-repo REQ (in mergeOrder), from each repo's parent path, writing
// repos[*].merged after each. Mirrors the single-repo mergePrompt but for the
// multi-repo case the orchestrator (not Phase 8) owns. The script re-verifies via
// gh afterward — the claim here is not accepted on its own. (ADR-12, BR-6)
function crossRepoMergePrompt(id, prs) {
  const prList = (prs || []).map((p) => `${p.repo}: ${p.url}`).join('; ');
  return [
    `Cross-REQ merge for ${id}: the merge barrier has reached this REQ, so merge`,
    'its PR(s) now. This REQ touches MORE THAN ONE repo; merge each touched-repo',
    'PR into its integration branch.',
    '',
    `PRs to merge (repo: url): ${prList || '(none)'}.`,
    '',
    'For EACH PR, in a sensible order (dependency/mergeOrder if one is recorded):',
    '  1. Confirm OPEN + MERGEABLE + CI green',
    '     (`gh pr view <url> --json state,mergeStateStatus`). On a real MERGE',
    '     CONFLICT, STOP and report mergeConflict=true — do not force.',
    '  2. Merge from the repo\'s PARENT path (not the worktree — git refuses to',
    '     delete a branch checked out by a worktree):',
    '     `gh pr merge <url> --squash --delete-branch`.',
    '  3. Immediately set pipeline-state.json.repos[<repo>].merged = true.',
    '',
    'Report mergeConflict (true ONLY on a real conflict) and merged (true if every',
    'PR merge command ran without error). The script re-verifies each merge with',
    '`gh pr view` — your claim is not accepted on its own.',
  ].join('\n');
}

// groupCrossRepoReqs — pure JS union-find: partition REQ ids into connected
// components over the "shares ≥1 touched repo" relation. Two REQs land in the
// same group iff there is a chain of REQs each sharing a repo with the next.
// Deterministic (no Date.now/Math.random): ids are processed in input order, and
// each group preserves that order. Returns id[][]. (ADR-12)
function groupCrossRepoReqs(ids, reposById) {
  const parent = {};
  const find = (x) => {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]]; // path halving
      x = parent[x];
    }
    return x;
  };
  const union = (a, b) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  };

  for (const id of ids) parent[id] = id;

  // Union any two REQs that share at least one touched repo.
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      if (sharesRepo(reposById[ids[i]] || [], reposById[ids[j]] || [])) {
        union(ids[i], ids[j]);
      }
    }
  }

  // Collect components, preserving the input order of ids within each group and
  // ordering the groups by their first member's position (determinism).
  const groupsByRoot = new Map();
  for (const id of ids) {
    const root = find(id);
    if (!groupsByRoot.has(root)) groupsByRoot.set(root, []);
    groupsByRoot.get(root).push(id);
  }
  return Array.from(groupsByRoot.values());
}

// sharesRepo — pure JS: true iff the two repo lists intersect. (groupCrossRepoReqs helper)
function sharesRepo(a, b) {
  const set = new Set(a);
  for (const r of b) if (set.has(r)) return true;
  return false;
}
