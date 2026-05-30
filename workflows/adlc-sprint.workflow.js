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
// `{terminal:'blocked', ...}`, NEVER a thrown error. A throw drops the pipeline
// item to null and loses the question, so `runReq` must never let a halt escape
// as an exception. See `blocked()`.

const { REPOS, VERDICT, TASKS, TERMINAL } = require('./schemas.js');

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
    agentType: 'pipeline-runner', // read-only scoring; reuses the existing doer
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
// barrier here — cross-repo merge sequencing is handled in Phase 8 / ADR-12,
// owned by TASK-059). A halt inside `runReq` is a RETURNED terminal value, so a
// blocked REQ never poisons its siblings. (ADR-6 / BR-4)
const results = await pipeline(todo, (r) => runReq(r.id));

return { results };

// ===========================================================================
// runReq(id) — the per-REQ chain. Phases 0–3 are implemented here (TASK-057);
// Phases 4–8 are dispatched to stubs owned by TASK-058 / TASK-059.
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
    agentType: 'pipeline-runner',
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
    agentType: 'pipeline-runner',
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
  // Phases 4–8 — owned by TASK-058 (4/5) and TASK-059 (6/7/8). Wired here so
  // the control flow is complete and reviewable; the stubs throw until those
  // tasks land. A throw inside a stub is acceptable ONLY because these are
  // not-yet-implemented placeholders — once implemented they must follow the
  // returned-halt contract like the gates above. (See stubs below.)
  // -------------------------------------------------------------------------
  await implement(id, P, worktree, tasks);      // Phase 4 — TASK-058
  await verify(id, P, worktree, repos);         // Phase 5 — TASK-058
  const PR_STATE = await openPRs(id, P, worktree, repos); // Phase 6 — TASK-059
  await cleanupAndWatchCI(id, P, worktree, PR_STATE);     // Phase 7 — TASK-059
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
      agentType: 'pipeline-runner',
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

// blocked — a user-answerable halt. `detail` is the closed halt payload
// (questions / reason / detail) the orchestrator surfaces; on resume the
// answer is threaded via args.answers[id]. (ADR-6, BR-5)
function blocked(id, reason, detail) {
  return { terminal: 'blocked', id, reason, detail };
}

// failed — a non-user-answerable terminal failure (e.g. no worktree). Distinct
// from `blocked`: there is no question for the user to answer.
function failed(id, reason, detail) {
  return { terminal: 'failed', id, reason, detail };
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

// ===========================================================================
// STUBS — Phases 4–8. Each throws so the file is syntactically complete and the
// control flow in runReq() is reviewable, while the real implementations land
// in their owning tasks. These are the ONLY throws in the engine; every real
// phase must return values (the halt contract), not throw. (ADR-6)
// ===========================================================================

// Phase 4 — serial implement in the single REQ worktree. (OWNER: TASK-058)
// TODO(TASK-058): for each dependency tier, for each task, `await
// agent(task-implementer)` SERIALLY in `worktree` (one writer, no git-index
// contention — ADR-5); update pipeline-state.json.phase4 per task.
async function implement(/* id, P, worktree, tasks */) {
  throw new Error('Phase 4 (implement) not yet implemented — TASK-058');
}

// Phase 5 — parallel review panel + deterministic consolidation. (OWNER: TASK-058)
// TODO(TASK-058): parallel(reflector + 5 reviewers) per touched repo → FINDINGS;
// dedupeAndRank() in pure JS; Critical/mustFix blocks merge; a reflector
// userFacing finding RETURNS blocked(id,'reflector-questions'). (ADR-7, BR-7)
async function verify(/* id, P, worktree, repos */) {
  throw new Error('Phase 5 (review panel + consolidate) not yet implemented — TASK-058');
}

// Phase 6 — open PR(s) based on the resolved integration branch. (OWNER: TASK-059)
// TODO(TASK-059): one agent opens the PR(s); returns the PRS schema object.
async function openPRs(/* id, P, worktree, repos */) {
  throw new Error('Phase 6 (open PRs) not yet implemented — TASK-059');
}

// Phase 7 — PR cleanup + CI watch (no re-review). (OWNER: TASK-059)
// TODO(TASK-059): one agent runs the per-PR sanity check and watches CI.
async function cleanupAndWatchCI(/* id, P, worktree, PR_STATE */) {
  throw new Error('Phase 7 (cleanup + CI watch) not yet implemented — TASK-059');
}

// Phase 8 — wrapup / merge with gh re-verification + TERMINAL return. (OWNER: TASK-059)
// TODO(TASK-059): single-repo REQs self-merge → {terminal:'merged'}; cross-repo
// REQs stop → {terminal:'pr-ready'}. EVERY merged/pr-ready claim re-verified via
// `gh pr view --json state,mergedAt` (BR-6). A merge conflict RETURNS
// blocked(id,'merge-conflict'). Return conforms to the TERMINAL schema.
async function wrapupAndMerge(/* id, P, worktree, repos, PR_STATE */) {
  // eslint-disable-next-line no-unused-vars
  const _schema = TERMINAL; // documents the intended return contract for TASK-059
  throw new Error('Phase 8 (wrapup / merge) not yet implemented — TASK-059');
}
