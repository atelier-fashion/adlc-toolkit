// workflows/schemas.js — JSON-Schema literals for the adlc-sprint Workflow engine.
//
// These are the structured-output contracts every `agent({ schema })` call in
// the workflow validates against. They replace prose-parsing with a validated
// shape so the deterministic script (consolidation, gating, terminal-state
// acceptance) operates on data, not free text. (REQ-474, ADR-7)
//
// Path-resolution convention: this module is reached via the standard two-level
// fallback — `.adlc/workflows/schemas.js` in a consumer project first, then
// `~/.claude/skills/workflows/schemas.js` (the skills symlink) — so the script
// and its tests both import the same literals regardless of where they run.
// See workflows/README.md.
//
// Field provenance: every field below comes verbatim from the REQ-474
// requirement.md "System Model". Every object schema sets
// `additionalProperties: false` so an agent cannot smuggle un-modeled keys past
// validation.
//
// Dimension note (load-bearing):
//   - CANDIDATES.candidates[].dimension enum = the 5 REVIEWER dimensions only
//     (correctness, quality, architecture, test-coverage, security). The
//     reflector receives NO candidates (BR-9), so `reflector` is absent here.
//   - FINDINGS.dimension enum = 6 dimensions (the 5 reviewers PLUS reflector),
//     because the reflector also returns findings.

// The 5 reviewer dimensions — the only sources of advisory pre-pass candidates.
const REVIEWER_DIMENSIONS = [
  'correctness',
  'quality',
  'architecture',
  'test-coverage',
  'security',
];

// The 6 review-panel dimensions — reviewers plus the reflector.
const PANEL_DIMENSIONS = ['reflector', ...REVIEWER_DIMENSIONS];

// REPOS — per-REQ repo records. The Phase-0 agent records the persistent
// worktree absolute path here; `/status` and resume consume `merged`. (BR-2, BR-11)
const REPOS = {
  type: 'object',
  additionalProperties: false,
  required: ['repos'],
  properties: {
    repos: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['repo', 'worktree'],
        properties: {
          repo: { type: 'string' },
          worktree: { type: 'string' }, // absolute path, created in Phase 0
          integrationBranch: { type: 'string' },
          primary: { type: 'boolean' },
          merged: { type: 'boolean' },
        },
      },
    },
  },
};

// VERDICT — output of a validation gate (Phase 1 / Phase 3). A failing verdict
// drives the 3×-retry-then-halt behavior. (BR-4)
const VERDICT = {
  type: 'object',
  additionalProperties: false,
  required: ['pass'],
  properties: {
    pass: { type: 'boolean' },
    reason: { type: 'string' },
    detail: { type: 'string' },
  },
};

// TASKS — output of the architect/tasks phase (Phase 2). Tasks are grouped into
// dependency tiers; Phase 4 implements each tier serially in the REQ worktree.
const TASKS = {
  type: 'object',
  additionalProperties: false,
  required: ['tasks'],
  properties: {
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'title'],
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          repo: { type: 'string' },
          tier: { type: 'integer' },
          dependencies: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
};

// FINDINGS — returned by each Phase-5 panel agent. `dimension` is one of the 6
// panel dimensions (includes `reflector`). The script consolidates, dedupes,
// ranks, and applies the Critical-blocks gate over these. (BR-7, ADR-7)
const FINDINGS = {
  type: 'object',
  additionalProperties: false,
  required: ['dimension', 'findings'],
  properties: {
    dimension: { type: 'string', enum: PANEL_DIMENSIONS },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'file', 'title', 'mustFix', 'userFacing'],
        properties: {
          severity: { type: 'string', enum: ['Critical', 'Major', 'Minor', 'Nit'] },
          file: { type: 'string' },
          line: { type: 'integer' },
          title: { type: 'string' },
          detail: { type: 'string' },
          suggestedFix: { type: 'string' },
          mustFix: { type: 'boolean' },
          userFacing: { type: 'boolean' },
          lessonId: { type: 'string' },
          fromCandidate: { type: 'boolean' },
        },
      },
    },
  },
};

// CANDIDATES — returned by the per-repo `kimi-pre-pass` agent (target design).
// `invoked` drives the `candidates ⇒ invoked` ghost-skip assertion; the script
// validates each candidate's `path` against the TRUSTED `changedFiles` and
// slices candidates per reviewer dimension. `candidates[].dimension` is one of
// the 5 REVIEWER dimensions only — the reflector gets none. (BR-9, BR-10)
const CANDIDATES = {
  type: 'object',
  additionalProperties: false,
  required: ['repo', 'invoked', 'exit', 'gateReason', 'changedFiles', 'candidates'],
  properties: {
    repo: { type: 'string' },
    invoked: { type: 'boolean' },
    exit: { type: 'integer' },
    gateReason: { type: 'string', enum: ['ok', 'no-binary', 'disabled-via-env'] },
    changedFiles: { type: 'array', items: { type: 'string' } }, // TRUSTED
    candidates: {
      type: 'array',
      items: {
        // UNTRUSTED — sourced from Kimi stdout; validated in deterministic JS.
        type: 'object',
        additionalProperties: false,
        required: ['dimension', 'path', 'description'],
        properties: {
          dimension: { type: 'string', enum: REVIEWER_DIMENSIONS },
          path: { type: 'string' },
          lineRange: { type: 'string' },
          description: { type: 'string' },
        },
      },
    },
  },
};

// PRS — PR urls produced by the PR phase (Phase 6/7). Consumed by the terminal
// state and re-verified with `gh pr view --json state,mergedAt`. (BR-6)
const PRS = {
  type: 'object',
  additionalProperties: false,
  required: ['prs'],
  properties: {
    prs: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['repo', 'url'],
        properties: {
          repo: { type: 'string' },
          url: { type: 'string' },
          number: { type: 'integer' },
        },
      },
    },
  },
};

// TERMINAL — per-REQ terminal state. A halt is a RETURNED `{ state: 'blocked' }`
// value, never a throw (BR-4). `merged`/`pr-ready` claims are re-verified before
// the dashboard accepts them (BR-6).
//
// `id` is carried so the top-level orchestrator can correlate each terminal back
// to its REQ for the ADR-12 cross-REQ merge-sequencing barrier (the post-pipeline
// step keys on the REQ id + its touched repos). It is part of the contract — the
// engine's `blocked()`/`failed()` constructors and the Phase-8 merged/pr-ready
// returns all stamp it — so the closed schema must admit it (don't silently drop
// the REQ identity past validation). (ADR-12, ADR-7)
const TERMINAL = {
  type: 'object',
  additionalProperties: false,
  required: ['state'],
  properties: {
    id: { type: 'string' },
    state: { type: 'string', enum: ['merged', 'pr-ready', 'blocked', 'failed'] },
    prs: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['repo', 'url'],
        properties: {
          repo: { type: 'string' },
          url: { type: 'string' },
          number: { type: 'integer' },
        },
      },
    },
    reason: { type: 'string' },
    // Halt-specific payload. Closed shape (additionalProperties:false) with the
    // known halt sub-fields — e.g. the reflector-question halt carries
    // `questions[]`. (System Model: events halt:reflector-question / halt:*)
    detail: {
      type: 'object',
      additionalProperties: false,
      properties: {
        questions: { type: 'array', items: { type: 'string' } },
        reason: { type: 'string' },
        detail: { type: 'string' },
      },
    },
  },
};

// REVIEWER_DIMENSIONS is exported too: it is the SINGLE source of truth for the
// 5 reviewer dimensions, consumed by helpers.js (validateCitations / fixedPairs)
// so the list is defined ONCE (no drift between the schema enum and the helpers'
// allowlists). (REQ-474, ADR-7)
module.exports = { REPOS, VERDICT, TASKS, FINDINGS, CANDIDATES, PRS, TERMINAL, REVIEWER_DIMENSIONS };
