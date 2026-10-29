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

// workflows/adlc-sprint.workflow.js — the `adlc-sprint` Dynamic Workflows engine.
//
// This is a Claude Code DYNAMIC WORKFLOWS script, NOT a normal Node program. It
// runs inside the Workflow runtime, which has NO filesystem, NO shell, and — the
// load-bearing finding from dogfooding (REQ-474, Rung 1) — NO `require` / `import`
// / `fs` either. So this engine MUST be ONE self-contained file: `export const
// meta` is the FIRST statement (the runtime reads it statically), and every
// schema literal + pure helper is INLINED below behind the `// ==== BEGIN/END
// PURE ====` sentinels rather than `require`d from sibling modules. The toolkit
// forbids a build step, so the pure logic stays inline and is unit-tested via a
// shared `vm` loader (workflows/tests/_load-pure.js) that evaluates just the
// sentinel-delimited section with the runtime globals absent. (ADR-2, ADR-10)
//
// The script owns ONLY control flow (sequence, fan-out, loops, merge ordering)
// and dispatches `agent()` leaves to do every git / gh / file / state operation.
// "Orchestration is the script; agents are the hands." (REQ-474, ADR-3)
//
// Runtime globals available here (do NOT import them):
//   meta      — exported pure literal (declared FIRST, above).
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
// fs / shell / require / import. There is NO module system here — the inlined
// PURE block below is how the schemas + helpers are available in-scope.
//
// Halt contract (load-bearing, ADR-6 / BR-4): a halt is a RETURNED value
// `{state:'blocked', ...}`, NEVER a thrown error. A throw drops the pipeline
// item to null and loses the question, so `runReq` must never let a halt escape
// as an exception. The discriminant field is `state` (the TERMINAL schema's
// name — schemas are the contract, ADR-7), NOT `terminal`. See `blocked()`.

// ==== BEGIN PURE ====
// Everything between the BEGIN/END PURE sentinels is PURE, deterministic logic:
// the JSON-Schema literals and the pure helper functions. It is in normal file
// scope, so the orchestration below references these names directly (no import).
// The `if (typeof module !== 'undefined')` guard at the end of this block is
// load-bearing: in the Workflow runtime `module` is undefined so the line is
// skipped (a bare `module.exports = …` would THROW there); under the test loader
// (workflows/tests/_load-pure.js) `module` is defined so the exports populate and
// node:test can cover this logic. Do NOT use a bare `module.exports`. (REQ-474)
//
// Field provenance: every schema field comes verbatim from the REQ-474
// requirement.md "System Model". Every object schema sets
// `additionalProperties: false` so an agent cannot smuggle un-modeled keys past
// validation. (ADR-7)
//
// Dimension note (load-bearing):
//   - CANDIDATES.candidates[].dimension enum = the 5 REVIEWER dimensions only
//     (correctness, quality, architecture, test-coverage, security). The
//     reflector receives NO candidates (BR-9), so `reflector` is absent there.
//   - FINDINGS.dimension enum = 6 dimensions (the 5 reviewers PLUS reflector),
//     because the reflector also returns findings.

// The 5 reviewer dimensions — the only sources of advisory pre-pass candidates.
// SINGLE source of truth, consumed by both the CANDIDATES enum and the helpers
// (validateCitations / fixedPairs) so the allowlists never drift. (ADR-7)
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

// CANDIDATES — returned by the per-repo `delegate-pre-pass` agent (target design).
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
        // UNTRUSTED — sourced from the delegate stdout; validated in deterministic JS.
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
//
// `closeOut` (BUG-249): a `merged` terminal stays `merged` even when its Step-8b
// close-out (/wrapup --close-out: spec status, terminal record, knowledge
// capture) failed — the merge is a fact the forge confirmed, and the unblock
// pass keys on `state` alone, so a held REQ is released by a merged blocker
// regardless of close-out. The close-out outcome rides beside it: `ok`,
// `failed` (reason in `closeOutDetail`), or `skipped` (no Phase-0 evidence in
// memory for this REQ). Absent means the close-out pass has not run.
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
    // BUG-249: Step-8b close-out outcome, stamped by the post-terminal close-out
    // pass on `merged` terminals only. Never encoded in `state`.
    closeOut: { type: 'string', enum: ['ok', 'failed', 'skipped'] },
    closeOutDetail: { type: 'string' },
    // Halt-specific payload. Closed shape (additionalProperties:false) with the
    // known halt sub-fields — e.g. the reflector-question halt carries
    // `questions[]`; a REQ-485 self-healing rebase halt carries the BlockHold
    // payload (`conflictFiles`, `holdState`, `rebaseAttempts`, `resolvedBlocker`)
    // so the orchestrator can surface a precise manual-rebase advisory and a later
    // pass can read the prior attempt count. (System Model: events
    // halt:reflector-question / halt:* ; REQ-485 ADR-6/ADR-7/BR-4/BR-10)
    detail: {
      type: 'object',
      additionalProperties: false,
      properties: {
        questions: { type: 'array', items: { type: 'string' } },
        reason: { type: 'string' },
        detail: { type: 'string' },
        // REQ-485 self-healing rebase-halt payload (BlockHold fields).
        conflictFiles: { type: 'array', items: { type: 'string' } },
        holdState: {
          type: 'string',
          enum: ['held', 'rebasing', 'resumed', 're-halted', 'needs-manual-rebase'],
        },
        rebaseAttempts: { type: 'number' },
        resolvedBlocker: { type: 'string' },
      },
    },
  },
};

// --- Pure helpers ----------------------------------------------------------
// Every function below is a PURE function of its arguments: no ambient runtime
// global (agent/parallel/pipeline/log/args/phase/budget) and — like the runtime
// contract — NO Date.now(), Math.random(), new Date(), fs, or shell. Two runs on
// two machines produce byte-identical output. This is exactly the property the
// tests pin down (the LESSON-008 citation boundary and the BR-7 consolidation
// gate must never silently regress). (ADR-7, ADR-10)

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

// selectEligible — pure JS Preflight selection: from the eligibility records the
// agent returned, keep ONLY the eligible REQs (in the agent's ranked order), then
// apply the max-`max` concurrency bound AFTER eligibility (BR-12) so an eligible
// REQ is never silently dropped before it is scored. Returns the deterministic
// split the top-level block then logs over:
//   { todo: record[],      // the first `max` eligible REQs — these run
//     dropped: string[],   // ids of eligible REQs deferred by the max-N bound
//     ineligible: record[] // the not-eligible records (surfaced with reasons) }
// No Date.now / Math.random / fs. (BR-12, AC-8)
function selectEligible(reqs, max) {
  const all = reqs || [];
  const eligible = all.filter((r) => r.eligible);
  const todo = eligible.slice(0, max);
  const dropped = eligible.slice(max).map((r) => r.id);
  const ineligible = all.filter((r) => !r.eligible);
  return { todo, dropped, ineligible };
}

// liteFallbackNotice — pure JS: one log line per REQ whose spec is on the lite
// lane. This engine's phases are a fixed script with no lite path yet, so it
// runs a lite REQ on the full lane and says so, once per REQ (REQ-652 BR-16,
// AC-13). A record without `lane`, or with `lane: 'full'`, yields nothing:
// absent means full (BR-12). The engine writes no `lane` object to state, so
// /status's Active Pipelines column reports these runs as full, which is what
// actually ran (its Requirements Summary still shows the spec's lane).
function liteFallbackNotice(reqs) {
  return (reqs || [])
    .filter((r) => r && r.lane === 'lite')
    .map((r) => `Lite lane: ${r.id} runs on the full lane under the workflow engine `
      + '(it has no lite path yet); run it with the legacy engine to use its lite lane.');
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
  const byRepoKey = new Map(); // `${repo}\x00${key}` -> survivor
  for (const f of flat) {
    const key = dedupeKey(f);
    const rk = `${f.repo}\x00${key}`;
    const prev = byRepoKey.get(rk);
    if (!prev) {
      // Coerce truthy `mustFix`/`userFacing` to a REAL boolean on the survivor, so
      // a non-schema-conformant input like `mustFix:1` still blocks merge (the gate
      // and the merge-OR below test `=== true`, which a bare `1` would slip past).
      // Defensive: the FINDINGS schema types these as boolean, but the consolidation
      // gate is the merge-safety backstop and must not be fooled by a truthy non-bool.
      const survivor = {
        ...f,
        mustFix: Boolean(f.mustFix),
        userFacing: Boolean(f.userFacing),
        dimensions: [f.dimension],
      };
      if (f.lessonId) survivor.lessonIds = [f.lessonId];
      byRepoKey.set(rk, survivor);
      continue;
    }
    // Merge into the survivor. The more severe copy's severity wins, and with it
    // the record of whether a lesson escalated it (REQ-647 BR-6).
    if (SEVERITY_RANK[f.severity] < SEVERITY_RANK[prev.severity]) {
      prev.severity = f.severity;
      if (f.escalatedFrom) prev.escalatedFrom = f.escalatedFrom; else delete prev.escalatedFrom;
    }
    prev.mustFix = prev.mustFix || Boolean(f.mustFix);
    prev.userFacing = prev.userFacing || Boolean(f.userFacing);
    if (!prev.dimensions.includes(f.dimension)) prev.dimensions.push(f.dimension);
    // UNION lesson ids across duplicates rather than keeping the first copy's: a
    // reviewer that matched a lesson must not be erased by one that did not. The
    // first non-empty id stays in `lessonId` (the FINDINGS field). (REQ-647 BR-6)
    if (f.lessonId) {
      if (!prev.lessonId) prev.lessonId = f.lessonId;
      prev.lessonIds = prev.lessonIds || [];
      if (!prev.lessonIds.includes(f.lessonId)) prev.lessonIds.push(f.lessonId);
    }
    if (!prev.lessonNote && f.lessonNote) prev.lessonNote = f.lessonNote;
  }
  const deduped = Array.from(byRepoKey.values());
  for (const f of deduped) if (f.lessonIds) f.lessonIds.sort(cmp);

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
  // `\x00` (NUL) is the field separator because it cannot appear in a file path or
  // a finding title, so `file + NUL + title` is an unambiguous composite key — no
  // path/title combination can collide with another by spanning the boundary. The
  // NUL lives only in an in-memory Map key string, never in any file or output.
  return `${f.file || ''}\x00${title}`;
}

// cmp — deterministic string comparator (no locale dependence, so two runs on
// two machines rank identically). (dedupeAndRank helper)
function cmp(a, b) {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

// ===========================================================================
// validateCitations(candidates, changedFiles) — PURE JS, the LESSON-008
// security boundary for the delegate pre-pass. (ADR-8, BR-9, BR-10)
//
// The `delegate-pre-pass` agent transcribes the delegate's UNTRUSTED stdout into candidate
// objects verbatim; this function is the script-side gate that decides which of
// them are safe to forward to the reviewers. It NEVER trusts a candidate's
// `path` — that string came from a model, so it could be a traversal (`..`), an
// injection payload, or a hallucinated file outside the diff.
//
//   candidates:   UNTRUSTED {dimension, path, lineRange?, description}[] (or null)
//   changedFiles: TRUSTED string[] — git `--name-only` output from the worktree
//
// A candidate SURVIVES iff ALL hold:
//   - `path` is a non-empty string,
//   - `path` does NOT contain `..` (no directory traversal),
//   - `path` matches ^[A-Za-z0-9_./-]+$ (no spaces, shell metachars, NULs, etc.),
//   - `path` is present in `changedFiles` (the citation must point at a file this
//     REQ actually changed — anchors the advisory to the real diff),
//   - `dimension` is one of the 5 REVIEWER dimensions (never reflector).
// Survivors are returned with their `description` SANITIZED: every char outside
// [A-Za-z0-9 .,:;()/_'"-] is replaced with a space (so an untrusted description
// can never carry control chars or prompt-injection punctuation into a reviewer
// prompt). `lineRange` is kept only when it is a sane `\d+(-\d+)?` token.
// Anything dropped is NOT forwarded. Fully deterministic — no Date.now /
// Math.random / fs. (runtime contract)
// ===========================================================================
function validateCitations(candidates, changedFiles) {
  const PATH_RE = /^[A-Za-z0-9_./-]+$/;
  const LINE_RE = /^\d+(-\d+)?$/;
  const changed = new Set(changedFiles || []);
  const out = [];
  for (const c of candidates || []) {
    if (!c || typeof c !== 'object') continue;
    const path = c.path;
    if (typeof path !== 'string' || path.length === 0) continue;
    if (path.indexOf('..') !== -1) continue;            // no traversal
    if (!PATH_RE.test(path)) continue;                  // charset allowlist
    if (!changed.has(path)) continue;                   // must be in the real diff
    if (!REVIEWER_DIMENSIONS.includes(c.dimension)) continue;  // reviewers only, never reflector
    const survivor = {
      dimension: c.dimension,
      path,
      description: sanitizeDescription(c.description),
    };
    if (typeof c.lineRange === 'string' && LINE_RE.test(c.lineRange)) {
      survivor.lineRange = c.lineRange;
    }
    out.push(survivor);
  }
  return out;
}

// sanitizeDescription — pure JS: replace every char outside the safe set
// [A-Za-z0-9 .,:;()/_'"-] with a space, so an untrusted candidate description
// can never smuggle control characters or injection punctuation into a reviewer
// prompt. A missing description becomes ''. (validateCitations helper, LESSON-008)
function sanitizeDescription(desc) {
  return String(desc == null ? '' : desc).replace(/[^A-Za-z0-9 .,:;()/_'"-]/g, ' ');
}

// candidatesByDimension — pure JS: bucket VALIDATED candidates by their reviewer
// dimension so each reviewer's prompt gets only its own slice. The reflector key
// is never produced (validateCitations already excludes it). Returns
// { [dimension]: candidate[] }. (Phase-5 pre-pass wiring helper)
function candidatesByDimension(validated) {
  const out = {};
  for (const c of validated || []) {
    if (!out[c.dimension]) out[c.dimension] = [];
    out[c.dimension].push(c);
  }
  return out;
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
  const out = {};
  for (const f of blocking || []) {
    // A consolidated finding records every dimension that raised it; re-check
    // each reviewer dimension that did (skip the reflector). Use `dimensions`
    // (the unioned list) when present, else the single `dimension`.
    const dims = f.dimensions || [f.dimension];
    for (const d of dims) {
      if (!REVIEWER_DIMENSIONS.includes(d)) continue;
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
// Each entry maps the FINDINGS `dimension` label to the bare name of the agent
// that produces it (the two namespaces differ). The dispatch site turns `agent`
// into an agentType with agentTypeFor (REQ-669 ADR-6). Pure literal builder.
// (PANEL_DIMENSIONS)
function panelMembers() {
  return [
    { dimension: 'reflector', agent: 'reflector' },
    { dimension: 'correctness', agent: 'correctness-reviewer' },
    { dimension: 'quality', agent: 'quality-reviewer' },
    { dimension: 'architecture', agent: 'architecture-reviewer' },
    { dimension: 'test-coverage', agent: 'test-auditor' },
    { dimension: 'security', agent: 'security-auditor' },
  ];
}

// AGENT_NAMESPACE_RE / normalizeAgentNamespace / agentTypeFor — REQ-669 ADR-6.
// The toolkit's agents are registered by bare name on the symlink install and as
// `<plugin>:<agent>` on the plugin install, so `adlc:reflector` there
// (verification.md row 7). A wrong agentType does not fail loudly: on the fork
// path an unresolved name silently became a generic agent with no checklist
// (row 7, evidence E3, note N4). So every agentType in this file goes through
// agentTypeFor, and the namespace is checked against a closed allowlist.
//
// `args.agentNamespace` is untrusted input like every arg (LESSON-008).
// normalizeAgentNamespace accepts exactly the two values /sprint can send: ""
// (or an absent value) on the symlink install and "adlc:" on the plugin install.
// Anything else, a well-shaped other plugin's prefix such as "other:" included,
// is `rejected` and yields "", so a bad value degrades to bare names instead of
// routing every dispatch to another plugin's agents. agentTypeFor normalizes
// again, so a caller cannot bypass the check.
const AGENT_NAMESPACES = Object.freeze(['', 'adlc:']);

function normalizeAgentNamespace(raw) {
  if (raw === undefined || raw === null || raw === '') return { ns: '', rejected: false };
  if (typeof raw === 'string' && AGENT_NAMESPACES.includes(raw)) return { ns: raw, rejected: false };
  return { ns: '', rejected: true };
}

function agentTypeFor(name, ns) {
  return normalizeAgentNamespace(ns).ns + name;
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

// ---------------------------------------------------------------------------
// BUG-249 — Step-8b close-out helpers (pure JS; the IO lives in the leaf).
// ---------------------------------------------------------------------------

// closeOutEvidenceStatus — pure JS: 'present' when the in-memory evidence for a
// REQ holds at least one Phase-5 finding or one implementer report, else 'none'.
// 'none' is what makes the close-out leaf write NO lesson and record
// `NO_ENTRY: close-out had no run evidence` — a lesson invented without run
// evidence is worse than none (REQ-646 BR-4 rule 3; LESSON-626).
function closeOutEvidenceStatus(ev) {
  const findings = ev && Array.isArray(ev.findings) ? ev.findings : [];
  const reports = ev && Array.isArray(ev.reports) ? ev.reports : [];
  return findings.length === 0 && reports.length === 0 ? 'none' : 'present';
}

// closeOutDigest — pure JS: the bounded, deterministic evidence block the
// close-out leaf drafts from. Bounded so the prompt stays a prompt (default:
// 30 findings, 1500 chars per report); deterministic so a replayed run builds
// byte-identical prompt text from the journal's cached leaf outputs.
function closeOutDigest(ev, limits) {
  const maxFindings = (limits && limits.maxFindings) || 30;
  const maxReportChars = (limits && limits.maxReportChars) || 1500;
  const tasks = (ev && ev.tasks) || [];
  const findings = (ev && ev.findings) || [];
  const reports = (ev && ev.reports) || [];
  const lines = [];
  lines.push(
    `Tasks (${tasks.length}): `
    + (tasks.map((t) => t.id + (t.title ? ` — ${t.title}` : '')).join('; ') || 'none'),
  );
  lines.push(
    `Phase-5 consolidated findings (${findings.length}`
    + (findings.length > maxFindings ? `, first ${maxFindings} shown` : '') + '):',
  );
  for (const f of findings.slice(0, maxFindings)) {
    lines.push(
      `  - [${f.severity}] ${f.file}${typeof f.line === 'number' ? `:${f.line}` : ''} — ${f.title}`
      + (lessonIdsOf(f).length ? ` (lesson ${lessonIdsOf(f).join(', ')})` : '') + (f.mustFix ? ' [must-fix]' : ''),
    );
  }
  if (findings.length === 0) lines.push('  (none)');
  lines.push(`Implementer reports (${reports.length}):`);
  for (const r of reports) {
    const text = String(r.text || '');
    lines.push(
      `  - ${r.taskId}: `
      + (text.length > maxReportChars ? `${text.slice(0, maxReportChars)} […truncated]` : text),
    );
  }
  if (reports.length === 0) lines.push('  (none)');
  return lines.join('\n');
}

// repoRootFromWorktree — pure JS: the engine's own worktree convention is
// `<repoRoot>/.worktrees/<id>` (phase0Prompt), so the repo root is recoverable
// from the recorded absolute path. Returns null when the path does not follow
// the convention (the leaf then derives it from `git worktree list`).
function repoRootFromWorktree(worktree, id) {
  if (typeof worktree !== 'string' || !id) return null;
  const suffix = `/.worktrees/${id}`;
  return worktree.endsWith(suffix) && worktree.length > suffix.length
    ? worktree.slice(0, -suffix.length)
    : null;
}

// groupMergedByRepo — pure JS: partition the `merged` terminals into groups
// keyed by primary repo id, ids sorted within a group and groups in repo-id
// order. Close-outs run in PARALLEL across groups and SERIALLY within one: two
// close-outs in the same repo would otherwise commit, open and merge chore PRs
// against one integration tip at the same time (BUG-249 contract 4 — the same
// one-writer-per-repo rule the ADR-12 merge barrier enforces). Non-merged
// terminals are not grouped (nothing to close out).
function groupMergedByRepo(terminals, primaryRepoById) {
  const groups = {};
  for (const t of terminals || []) {
    if (!t || t.state !== 'merged') continue;
    const repo = (primaryRepoById && primaryRepoById[t.id]) || '<unknown>';
    (groups[repo] = groups[repo] || []).push(t.id);
  }
  return Object.keys(groups).sort().map((k) => groups[k].slice().sort());
}

// ===========================================================================
// REQ-647 — lessons reach the architect, each implementer and the review panel.
//
// The script has no shell, so a LessonSet is produced by a RETRIEVAL LEAF that runs
// `adlc_lessons select … --format json --with-text` (partials/lessons.sh) and returns
// it as a LESSONS object: after Phase 0 (the Step-0 set), before Phase 4 (every
// task's set in one call, as TASK_LESSONS), and before the Phase-5 fan-out. The
// leaf also writes the set, without `text`, to the primary-path state copy
// (`lessons.<set>`). `text` is the loaded text (frontmatter + `## Lesson` +
// `## Applies When`, ≤ 40 lines) and exists only so a prompt can carry it.
// Closed schemas + a pure structural test, in the same change (LESSON-331).
// ===========================================================================
const LESSON_ID_RE = /^LESSON-[0-9]{3,6}$/;
const LESSON_TEXT_MAX_LINES = 40;

const LESSON_QUERY = {
  type: 'object',
  additionalProperties: false,
  required: ['components'],
  properties: {
    components: { type: 'array', items: { type: 'string' } },
    domain: { type: 'string' },
    stack: { type: 'array', items: { type: 'string' } },
    concerns: { type: 'array', items: { type: 'string' } },
    tags: { type: 'array', items: { type: 'string' } },
  },
};

const LESSON_ENTRY = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'title', 'path'],
  properties: {
    id: { type: 'string' },
    title: { type: 'string' },
    path: { type: 'string' },
    component: { type: 'string' },
    score: { type: 'integer' }, // absent on a Phase-5 top-up entry
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    kind: { type: 'string', enum: ['process', 'domain'] },
    newerThanSpec: { type: 'boolean' },
    supersededBy: { type: 'array', items: { type: 'string' } },
    text: { type: 'string' },
  },
};

const LESSONS = {
  type: 'object',
  additionalProperties: false,
  required: ['query', 'lessons', 'retrievedAt'],
  properties: {
    query: LESSON_QUERY,
    lessons: { type: 'array', maxItems: 15, items: LESSON_ENTRY },
    cap: { type: 'integer' },
    retrievedAt: { type: 'string' },
    unavailable: { type: 'string' }, // the `lessons: unavailable — <reason>` reason
  },
};

const TASK_LESSONS = {
  type: 'object',
  additionalProperties: false,
  required: ['sets'],
  properties: {
    sets: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['taskId', 'set'],
        properties: { taskId: { type: 'string' }, set: LESSONS },
      },
    },
  },
};

// lessonIdsOf — every lesson id a consolidated finding carries (the unioned
// `lessonIds` when present, else its single `lessonId`). Pure.
function lessonIdsOf(f) {
  if (f && Array.isArray(f.lessonIds) && f.lessonIds.length) return f.lessonIds;
  return f && f.lessonId ? [f.lessonId] : [];
}

// setEntriesById — the set's entries keyed by id, keeping only well-formed ids.
function setEntriesById(set) {
  const byId = new Map();
  for (const e of (set && Array.isArray(set.lessons)) ? set.lessons : []) {
    if (e && typeof e.id === 'string' && LESSON_ID_RE.test(e.id) && !byId.has(e.id)) byId.set(e.id, e);
  }
  return byId;
}

// escalateByLessons(findingsByRepo, set) — /review Step 4's escalation rule, in
// code, BEFORE dedupeAndRank. A finding's `lessonId` escalates its severity one
// level (Nit→Minor→Major→Critical; Critical stays) ONLY when the id is a member of
// the Phase-5 set the panel was handed: an agent-written id is untrusted
// (LESSON-008), so an id outside the set is REMOVED from the finding and never
// escalates. A member with `confidence: "low"` or a non-empty `supersededBy` keeps
// the finding's severity and records /review's annotation in `lessonNote` (REQ-646
// BR-6). Returns a new map; the input is not mutated. Pure. (REQ-647 BR-6)
function escalateByLessons(findingsByRepo, set) {
  const UP = { Nit: 'Minor', Minor: 'Major', Major: 'Critical' };
  const byId = setEntriesById(set);
  const out = {};
  for (const repo of Object.keys(findingsByRepo || {})) {
    out[repo] = (findingsByRepo[repo] || []).map((fset) => {
      if (!fset) return fset;
      return {
        ...fset,
        findings: (fset.findings || []).map((f) => {
          if (!f || !f.lessonId) return f;
          const g = { ...f };
          const entry = byId.get(f.lessonId);
          if (!entry) {
            delete g.lessonId;
            return g;
          }
          const supersededBy = (Array.isArray(entry.supersededBy) ? entry.supersededBy : [])
            .filter((id) => typeof id === 'string' && LESSON_ID_RE.test(id));
          if (supersededBy.length) {
            g.lessonNote = `matched ${entry.id}, superseded by ${supersededBy.join(', ')} — not escalated`;
            return g;
          }
          if (entry.confidence === 'low') {
            g.lessonNote = `matched ${entry.id}, confidence low — not escalated`;
            return g;
          }
          if (UP[g.severity]) {
            g.escalatedFrom = g.severity;
            g.severity = UP[g.severity];
          }
          return g;
        }),
      };
    });
  }
  return out;
}

// lessonsBlock(set, heading) — the prompt text for a LessonSet: a heading, then
// one `### LESSON-xxx — title (notes)` block of loaded text per lesson, each capped
// at 40 lines. '' for an absent, unavailable or empty set, so a prompt with no
// lessons is byte-identical to one built before REQ-647. Pure + deterministic.
function lessonsBlock(set, heading) {
  const byId = setEntriesById(set);
  if (!set || set.unavailable || byId.size === 0) return '';
  const lines = ['', heading];
  for (const e of byId.values()) {
    const notes = [];
    if (Number.isInteger(e.score)) notes.push(`score ${e.score}`);
    if (e.kind === 'process') notes.push('process');
    if (e.newerThanSpec === true) notes.push('newer than spec');
    if (e.confidence === 'low') notes.push('confidence low');
    const sup = (Array.isArray(e.supersededBy) ? e.supersededBy : []).filter((id) => LESSON_ID_RE.test(String(id)));
    if (sup.length) notes.push(`superseded by ${sup.join(', ')}`);
    lines.push('', `### ${e.id} — ${String(e.title || '')}${notes.length ? ` (${notes.join('; ')})` : ''}`);
    if (typeof e.text === 'string' && e.text) {
      const text = e.text.split('\n');
      lines.push(...(text.length > LESSON_TEXT_MAX_LINES
        ? text.slice(0, LESSON_TEXT_MAX_LINES - 1).concat(`[… truncated — read ${e.id} for the rest]`)
        : text));
    }
  }
  return lines.join('\n');
}

// lessonsLogLine(label, set) — REQ-647 BR-10: the line that names which lessons a
// phase loaded, in the same shape `adlc_lessons` prints:
//   Lessons loaded (task TASK-012): LESSON-013, LESSON-335 [newer-than-spec: LESSON-582]
// Pure + deterministic.
function lessonsLogLine(label, set) {
  if (!set) return `Lessons loaded (${label}): unavailable — retrieval leaf returned nothing`;
  if (set.unavailable) return `Lessons loaded (${label}): unavailable — ${set.unavailable}`;
  const entries = Array.from(setEntriesById(set).values());
  const plain = entries.filter((e) => e.newerThanSpec !== true).map((e) => e.id);
  const newer = entries.filter((e) => e.newerThanSpec === true).map((e) => e.id);
  let line = `Lessons loaded (${label}):`;
  if (plain.length) line += ` ${plain.join(', ')}`;
  if (newer.length) line += ` [newer-than-spec: ${newer.join(', ')}]`;
  if (!plain.length && !newer.length) line += ' none';
  return line;
}

// taskSetsById(taskLessons) — TASK_LESSONS → { taskId: LESSONS }. A malformed or
// duplicate row is dropped (first wins), never thrown on. Pure.
function taskSetsById(taskLessons) {
  const out = {};
  for (const row of (taskLessons && Array.isArray(taskLessons.sets)) ? taskLessons.sets : []) {
    if (row && typeof row.taskId === 'string' && row.set && !(row.taskId in out)) out[row.taskId] = row.set;
  }
  return out;
}

// Guarded export — load-bearing (see the BEGIN PURE banner): in the Workflow
// runtime `module` is undefined so this line is SKIPPED (a bare module.exports
// would throw); under the test loader `module` is defined so the pure logic is
// exported for node:test. (REQ-474)
if (typeof module !== 'undefined') module.exports = {
  REPOS, VERDICT, TASKS, FINDINGS, CANDIDATES, PRS, TERMINAL, REVIEWER_DIMENSIONS, PANEL_DIMENSIONS,
  blocked, failed, terminalValue,
  selectEligible, liteFallbackNotice, orderByTier,
  dedupeAndRank, dedupeKey, cmp,
  validateCitations, sanitizeDescription, candidatesByDimension,
  reflectorQuestions, fixedPairs, mergeReverified, panelMembers,
  AGENT_NAMESPACES, normalizeAgentNamespace, agentTypeFor,
  allMerged, stripVerifyMarkers,
  groupCrossRepoReqs, sharesRepo,
  closeOutEvidenceStatus, closeOutDigest, repoRootFromWorktree, groupMergedByRepo,
  LESSON_QUERY, LESSON_ENTRY, LESSONS, TASK_LESSONS,
  lessonIdsOf, escalateByLessons, lessonsBlock, lessonsLogLine, taskSetsById,
};
// ==== END PURE ====

// ---------------------------------------------------------------------------
// Tunables — concurrency bound is the existing /sprint behavior (BR-12).
// ---------------------------------------------------------------------------
const MAX_CONCURRENT_REQS = 5; // applied AFTER eligibility (BR-12)
const MAX_GATE_ITERATIONS = 3; // ≤3 validate→fix loop per gate (BR-4)
// REQ-485 BR-10 / OQ-3: max conflicting-rebase attempts per held REQ before it is
// marked needs-manual-rebase and the auto-retry stops. Default 1; a consumer repo
// may override via .adlc/config.yml `auto_rebase_max_attempts` (the unblock-pass
// find-leaf reads that config and reports each held REQ's prior rebaseAttempts).
const AUTO_REBASE_MAX_ATTEMPTS = 1;

// EVIDENCE — per-REQ run evidence the Step-8b close-out drafts from (BUG-249
// contract 3). The script has no filesystem, and the leaves that produced this
// data (Phase-0 repos, Phase-2 tasks, Phase-4 implementer reports, Phase-5
// consolidated findings) used to discard it; it is kept HERE, in memory, keyed
// by REQ id. On a `resumeFromRunId` replay every cached agent() call returns its
// recorded value and `runReq` re-executes, so the map is rebuilt identically —
// except for Phase-4 tasks skipped via phase4.completedTasks, which are never
// re-dispatched and so contribute no report (the digest says so by omission).
// `ans` is copied in from runReq, the ONE sanctioned read site of args.answers,
// so the close-out prompt can carry a user's retry guidance without a second
// read site. Declared above the top-level await for the TDZ reason below.
const EVIDENCE = new Map();

// ELIGIBILITY_SCHEMA — the Preflight agent's structured return. Declared here,
// ABOVE the top-level Preflight block, because the module body runs top-to-
// bottom: a `const` referenced by top-level code must be initialized before
// that code runs (function declarations hoist, but `const` does not — a later
// declaration would be a temporal-dead-zone ReferenceError). This schema is
// LOCAL to the engine's control flow, not one of the 7 shared agent-output
// contracts in the PURE block above. Pure literal; additionalProperties:false. (ADR-7)
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
          // REQ-652: the spec's lane. Optional; absent means full.
          lane: { type: 'string', enum: ['lite', 'full'] },
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
// LOCAL to the engine's control flow (not the 7 shared contracts in the PURE block).
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

// COMPLETED_TASKS_SCHEMA — the Phase-4 resume-idempotency read. A read-only IO
// leaf returns pipeline-state.json.phase4.completedTasks so `implement` can SKIP
// tasks already finished+committed on a prior run, rather than re-committing them.
// Declared here (above the top-level await) for the same TDZ reason as the schemas
// above. LOCAL to the engine's control flow; pure literal; additionalProperties:false.
const COMPLETED_TASKS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['completedTasks'],
  properties: {
    completedTasks: { type: 'array', items: { type: 'string' } },
  },
};

// CLOSE_OUT_RESULT_SCHEMA — the Step-8b close-out leaf's structured return
// (BUG-249). `closeOut` is copied onto the merged TERMINAL; `detail` carries the
// lessons written, the `NO_ENTRY: …` line, or the failure reason; `chorePr` is
// the close-out bookkeeping PR when one was opened. Declared here (above the
// top-level await) for the same TDZ reason as the schemas above. LOCAL to the
// engine's control flow; pure literal; additionalProperties:false.
const CLOSE_OUT_RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['closeOut'],
  properties: {
    closeOut: { type: 'string', enum: ['ok', 'failed', 'skipped'] },
    detail: { type: 'string' },
    chorePr: { type: 'string' },
  },
};

// HELD_REQS_SCHEMA / REBASE_RESULT_SCHEMA — the REQ-485 self-healing unblock pass
// IO leaves. Same TDZ rule as the schemas above (declared before the top-level
// await). Pure literals; additionalProperties:false.
//
// HELD_REQS_SCHEMA: a read-only scan of the OTHER REQs' pipeline-state.json for a
// STILL-PRESENT blockers entry (the BR-11 idempotency anchor — a cleared entry
// means already-resumed, never re-processed). Each record carries the held REQ's
// own worktree path + resumePhase + the blocker it waits on, so the script can
// rebase + resume it without re-deriving anything (BR-2, BR-5, BR-6).
const HELD_REQS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['held'],
  properties: {
    held: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'blockedBy', 'worktree'],
        properties: {
          id: { type: 'string' },           // the held REQ id
          blockedBy: { type: 'string' },    // the REQ it waits on (live merge dep)
          worktree: { type: 'string' },     // its own repos[<id>].worktree (BR-5)
          resumePhase: { type: 'number' },  // its recorded currentPhase (BR-3)
          rebaseAttempts: { type: 'number' }, // prior conflicting-rebase count (BR-10)
        },
      },
    },
  },
};

// REBASE_RESULT_SCHEMA: the per-held-REQ rebase IO leaf's outcome. `clean` true ⇒
// resume from resumePhase (BR-3); false ⇒ the leaf already ran `rebase --abort`
// (non-mutating restore, BR-4) and reports the materialized conflict files. The
// leaf NEVER auto-resolves/forces (ethos #6).
const REBASE_RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['clean'],
  properties: {
    clean: { type: 'boolean' },
    conflictFiles: { type: 'array', items: { type: 'string' } },
    detail: { type: 'string' },
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
//                            Phase-0 agent re-resolves by /proceed step 4's rule:
//                            branches.integration from .adlc/config.yml when
//                            declared, else two-branch → 'staging', else 'main';
//                            never hardcode 'main').
//   args.answers           — map<reqId,string>; {} on first run, carries user
//                            replies to halts on resume (ADR-6 / BR-5).
//   args.blockerCleared    — map<reqId,blockerId>; {} on first run. The ORCHESTRATOR
//                            (not a user) sets this when it merges a held REQ's
//                            blocker within the run: the post-merge unblock pass
//                            rebases the held REQ's worktree and relaunches THIS
//                            script via resumeFromRunId with the cleared signal,
//                            so the held REQ resumes from its recorded phase and
//                            re-runs the now-passing trial-merge gate. Distinct
//                            from a user answer (REQ-485 BR-8). Like args.answers
//                            it is read ONLY in runReq for the held REQ, keeping
//                            every other REQ byte-identical (cache replay).
//   args.agentNamespace    — string, default "". `adlc:` when /sprint runs from
//                            the plugin install, "" on the symlink install. The
//                            script has no fs, so it cannot detect the route
//                            itself; /sprint computes this from its substituted
//                            ${CLAUDE_PLUGIN_ROOT} (REQ-669 ADR-6). Read ONCE,
//                            just below, and validated there.

phase('Preflight — eligibility + max-5 bound');

// REQ-669 ADR-6: the one read site of args.agentNamespace. A value outside the
// closed allowlist ("" or "adlc:") is logged and replaced by "" (bare names). The log line names only
// the value's type, never the value, so an untrusted string is not echoed
// (LESSON-008). Declared before the first await so runReq and the post-pipeline
// passes never meet it in its TDZ.
const AGENT_NAMESPACE_ARG = args.agentNamespace;
const AGENT_NAMESPACE = normalizeAgentNamespace(AGENT_NAMESPACE_ARG);
if (AGENT_NAMESPACE.rejected) {
  log(
    `agentNamespace rejected: a ${typeof AGENT_NAMESPACE_ARG} that is not "" or ` +
    '"adlc:" — dispatching every agent by its bare name.',
  );
}
const AGENT_NS = AGENT_NAMESPACE.ns;

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
    // task-implementer, delegate-pre-pass). 'pipeline-runner' is the legacy
    // "run a whole /proceed" doer and would misbehave as a generic IO worker;
    // Preflight is read-only eligibility scoring, so use a default subagent
    // (full tools) driven entirely by the inline prompt. (ethos #6)
  },
);

// Keep only the eligible REQs (in the agent's ranked order) and apply the max-5
// concurrency bound AFTER eligibility (BR-12) — selection is PURE JS in
// `selectEligible` so it is unit-tested; the SCRIPT keeps the logging. The bound
// is applied post-eligibility so we never silently drop an eligible REQ before
// scoring it. (BR-12 / AC-8)
const { todo, dropped, ineligible } = selectEligible(ELIGIBILITY.reqs || [], MAX_CONCURRENT_REQS);

// Log any truncation so a silent top-N coverage drop is never hidden (BR-12 / AC-8).
if (dropped.length > 0) {
  log(
    `Preflight: ${todo.length + dropped.length} eligible REQs exceed the max-5 concurrency `
    + `bound; running the first ${MAX_CONCURRENT_REQS}, deferring `
    + `${dropped.length}: ${dropped.join(', ')}.`,
  );
}

// Surface ineligible REQs too, so the user sees why a requested REQ was skipped.
for (const r of ineligible) {
  log(`Preflight: skipping ${r.id} — ineligible (${r.reason || 'no reason given'}).`);
}

// REQ-652 BR-16: a lite REQ runs on the full lane here; say so once per REQ.
for (const line of liteFallbackNotice(todo)) log(line);

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

// Self-healing serialization (REQ-485). After the merge barrier, some REQs may
// have merged that OTHER REQs were held behind (a Phase-8 trial-merge conflict
// against an ahead REQ → {state:'blocked', reason:'merge-conflict'|'trial-merge'}).
// Run the post-merge unblock pass: for each held REQ whose blocker is now MERGED,
// rebase ONLY its own worktree and — on a clean rebase — resume it (re-run its
// now-passing Phase-8 gate + merge). A conflicting rebase aborts non-mutatingly
// and re-halts (BR-4), retry-bounded (BR-10). Held REQs on one blocker resume in
// deterministic order, one at a time (BR-6). With nothing newly merged this is a
// no-op (deterministic + idempotent — BR-6). A blocker that ended `failed` also
// releases REQs held SOLELY on it (OQ-5 / ADR-8). The pass mutates only each held
// REQ's own worktree (BR-5) via leaf agents (the script owns control flow only).
const healed = await unblockHeldReqs(sequenced, todo);

// Step-8b close-out (BUG-249). Every `merged` terminal — single-repo self-merge,
// barrier-merged cross-repo, or a held REQ the unblock pass just resumed — now
// gets the close-out half of Phase 8 that `/proceed` Step 8b requires of
// whoever performed the merge (Step 8c): `/wrapup --close-out` in a dedicated
// worktree (spec status → complete, the five-field terminal record, knowledge
// capture from the in-memory run evidence, a squash-merged chore PR), then
// worktree teardown. Runs AFTER the unblock pass so a close-out can never delay
// a release, serially per repo, and stamps `closeOut` beside — never instead
// of — `state:'merged'`.
const closed = await closeOutMerged(healed, todo);

return { results: closed };

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

  // The user's reply to THIS REQ's prior halt, threaded in on resume via
  // resumeFromRunId (ADR-6 / BR-5). `args.answers` is `{}` on a first run, so
  // `ans` is undefined and every call below is byte-identical to the first run —
  // the journal cache replays. On resume `ans` is the user's guidance string,
  // and it is injected into ONLY the halt-prone prompts (the gate validate/fix
  // prompts and the Phase-5 fix prompt). That surgical divergence is the whole
  // mechanism: only this blocked REQ's halt-prone calls miss the cache, so only
  // it advances past its halt while every other call — and every untouched /
  // already-merged REQ — replays. Read it HERE and nowhere else; do not reference
  // `args.answers` anywhere outside this function or the cache divergence stops
  // being surgical. (ADR-6, BR-5, AC-3)
  const ans = args.answers?.[id];

  // The orchestrator's "blocker-cleared" signal for THIS REQ (REQ-485 BR-8),
  // threaded in on resume by the post-merge unblock pass via resumeFromRunId.
  // `undefined` on a first run (and for every REQ that was not held on a
  // just-merged blocker), so reading it here is cache-neutral. When set, it names
  // the blocker that merged; it is injected ONLY into the Phase-8 wrapup/merge
  // path (the held REQ's now-passing trial-merge gate re-runs and merges), the
  // same surgical-divergence discipline as `ans`. Read it HERE and nowhere else.
  const blockerCleared = args.blockerCleared?.[id];

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

  // Start this REQ's close-out evidence record (BUG-249). `ans` is copied here
  // — the one sanctioned read site of args.answers — so the close-out prompt
  // can carry retry guidance on a resume without a second read site.
  EVIDENCE.set(id, { repos, tasks: [], findings: null, reports: [], ans });

  // REQ-647 BR-6 (a) — the Step-0 LessonSet: REQ-vintage background, handed to
  // the architect. A retrieval leaf runs `adlc_lessons` (the script has no shell)
  // and writes `lessons.step0` to the primary-path state copy. Retrieval is never
  // a gate: an unavailable set is logged and the REQ carries on without lessons.
  const STEP0_LESSONS = await retrieveLessons(id, P, lessonsPrompt(id, worktree, repos, 'step0'), 'step0', LESSONS);
  log(`${id} ${lessonsLogLine('step0', STEP0_LESSONS)}`);

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
    ans, // user guidance on resume (BR-5) — injected into this gate's halt-prone prompts only
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
          agentType: agentTypeFor(a, AGENT_NS),
        }),
      ),
    )
  ).filter(Boolean);

  const TASK_PLAN = await agent(architectPrompt(id, worktree, exploreReports, STEP0_LESSONS), {
    ...P,
    label: `${id} phase2-architect`,
    schema: TASKS,
    // Default workflow subagent (no agentType) — the architect/synthesis role is
    // an inline-prompted generalist, not the legacy 'pipeline-runner'. (ethos #6)
  });
  const tasks = TASK_PLAN.tasks || [];
  if (EVIDENCE.has(id)) EVIDENCE.get(id).tasks = tasks; // BUG-249 evidence

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
    ans, // user guidance on resume (BR-5) — injected into this gate's halt-prone prompts only
  );
  if (archOk !== true) return archOk; // gate() returned a `blocked` terminal

  // -------------------------------------------------------------------------
  // Phase 4 (serial implement) + Phase 5 (review panel) — TASK-058. Phase 5 can
  // RETURN a `blocked` terminal (a reflector userFacing question); that halt is
  // propagated here exactly like the gate halts above — never thrown. (ADR-6)
  // -------------------------------------------------------------------------
  // REQ-647 BR-6 (b) — every task's LessonSet in ONE leaf, now that the task files
  // exist and have passed Phase 3. Phase 4 is serial, so one call before it is
  // enough; each set is chosen by the files its task touches (BR-1a).
  const TASK_LESSON_SETS = taskSetsById(
    await retrieveLessons(id, P, taskLessonsPrompt(id, worktree, repos, tasks), 'tasks', TASK_LESSONS));
  for (const t of orderByTier(tasks)) log(`${id} ${lessonsLogLine(`task ${t.id}`, TASK_LESSON_SETS[t.id])}`);
  await implement(id, P, worktree, tasks, TASK_LESSON_SETS); // Phase 4 — serial writer
  // REQ-647 BR-6 (c) — the Phase-5 LessonSet, from the diff, before the fan-out.
  const PHASE5_LESSONS = await retrieveLessons(id, P, lessonsPrompt(id, worktree, repos, 'phase5'), 'phase5', LESSONS);
  log(`${id} ${lessonsLogLine('phase5', PHASE5_LESSONS)}`);
  const verifyResult = await verify(id, P, worktree, repos, ans, PHASE5_LESSONS); // Phase 5 — panel
  if (verifyResult !== true) return verifyResult;    // reflector-question halt
  const PR_STATE = await openPRs(id, P, repos);       // Phase 6 — open PR(s)
  await cleanupAndWatchCI(id, P, PR_STATE);           // Phase 7 — sanity + CI
  // Phase 8. `blockerCleared` (REQ-485 BR-8) is forwarded so a resumed held REQ
  // skips straight to re-running its now-passing trial-merge gate + merge; on a
  // first run it is undefined and Phase 8 behaves byte-identically (cache replay).
  const term = await wrapupAndMerge(id, P, repos, PR_STATE, blockerCleared); // Phase 8

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
//
// `ans` (optional) is the user's resume guidance for THIS REQ (args.answers[id],
// ADR-6 / BR-5). It is the ONLY thing that makes a resumed gate diverge from the
// journal cache: it is appended to this gate's halt-prone prompts — the validate
// prompt and the fix prompt — so on resume the re-validate/fix are guided by the
// user's reply, while on a first run (`ans` undefined) the prompts are byte-
// identical and the cache replays. No other call site references args.answers.
// ===========================================================================
async function gate(id, P, worktree, spec, ans) {
  // The guidance suffix: appended to the halt-prone prompts ONLY. Empty when
  // there is no answer, so a first run is byte-identical (cache replays). (BR-5)
  const guidance = ans ? ` — user guidance: ${ans}` : '';
  for (let i = 1; i <= MAX_GATE_ITERATIONS; i++) {
    // Validate agent — read-only verdict against the VERDICT schema. On resume
    // the user's guidance is appended so the re-validate accounts for the reply.
    const verdict = await agent(spec.validatePrompt + guidance, {
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
    // so the fix is targeted (plus the user's resume guidance, if any). The next
    // loop iteration re-validates.
    await agent(spec.fixPrompt(verdict) + guidance, {
      ...P,
      label: `${spec.fixLabel} (round ${i})`,
      agentType: agentTypeFor('task-implementer', AGENT_NS),
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
// (ADR-6 / BR-4). Shapes conform to the TERMINAL schema (inlined PURE block).
// ===========================================================================

// blocked(), failed(), terminalValue() — inlined in the PURE block above (pure; unit-tested via node:test). (REQ-474, ADR-10)

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
    '    A lite REQ (frontmatter `lane: "lite"`) is the exception on both counts:',
    '    status "draft" is eligible, because a lite REQ skips spec validation by',
    '    design, and it has no tasks directory. (REQ-652 BR-16)',
    '  - reason: a short human-readable reason when NOT eligible.',
    '  - integrationBranch: the resolved integration branch for the primary',
    '    repo, by /proceed step 4\'s rule: branches.integration from',
    '    .adlc/config.yml when declared, else "staging" in a two-branch repo,',
    '    else "main". NEVER hardcode "main"; resolve it from the repo. Worktrees',
    '    later base on origin/<integrationBranch>. (BUG-060, LESSON-036)',
    '  - touchedRepos: the repo ids this REQ touches (for later cross-repo',
    '    merge sequencing).',
    '  - lane (optional): "lite" or "full", copied from the `lane` key in',
    '    requirement.md frontmatter. Omit it when the key is absent (absent means',
    '    full). This engine runs a lite REQ on the full lane, whose Phase 1',
    '    validates it and whose Phase 2 writes the tasks. (REQ-652 BR-16)',
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
    `  1. Resolve the integration branch for each repo ${id} touches by /proceed`,
    '     step 4\'s rule: branches.integration from that repo\'s .adlc/config.yml',
    '     when declared, else two-branch repo → "staging", else "main". NEVER',
    '     hardcode "main". (BUG-060)',
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

function architectPrompt(id, worktree, exploreReports, step0Lessons) {
  const lines = [
    `Phase 2 architect for ${id} in worktree ${worktree}: synthesize the`,
    'exploration reports below into a tiered task plan. Group tasks into',
    'dependency tiers; tasks within a tier MUST touch disjoint files (this is',
    'what makes serial-in-shared-worktree Phase 4 safe). Write the task files',
    'under the spec\'s tasks/ directory and return the TASKS schema object.',
    '',
    'Exploration reports (JSON):',
    JSON.stringify(exploreReports),
  ];
  // REQ-647: no block when no Step-0 set was retrieved, so the prompt is unchanged.
  const block = lessonsBlock(step0Lessons, 'Lessons for this REQ (the Step-0 set, REQ-647). Design around them and name, in the architecture rationale, the ids your design applies:');
  if (block) lines.push(block);
  return lines.join('\n');
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

function implementPrompt(id, worktree, task, lessonSet) {
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
    // REQ-647 BR-2: '' when the task has no set, so the prompt is unchanged.
    lessonsBlock(lessonSet, `Lessons for ${task.id}, selected for the files it touches (REQ-647). Read them before writing code. When one applies to a change you make, acknowledge it where the Phase-5 check looks: a \`Lessons: LESSON-xxx\` commit trailer (comma-separate several), or the id in the task's ## Verification block. A mention only in your report is not seen.`),
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

// completedTasksPrompt — the Phase-4 resume-idempotency READ. A read-only IO leaf
// reports pipeline-state.json.phase4.completedTasks so `implement` can skip the
// tasks already finished+committed on a prior run. Returns [] when the file or the
// phase4 object is absent (a fresh run), so a first run skips nothing. (AC-7)
function completedTasksPrompt(id, worktree) {
  return [
    `Phase 4 resume check for ${id} in worktree ${worktree}: report which tasks`,
    'are already done so the engine does not re-commit them. Read',
    'pipeline-state.json.phase4.completedTasks and return its array of task ids',
    'VERBATIM. If the file, the phase4 object, or the completedTasks array is',
    'absent (a fresh run), return an empty array. This is a READ-ONLY check — do',
    'NOT modify code, state, or run tests.',
  ].join('\n');
}

// --- REQ-647 retrieval leaf prompts -----------------------------------------
//
// Each prompt's bytes depend only on the REQ id, the worktree, the Phase-0 repo
// records and (for the task leaf) the Phase-2 task list — never on args.answers —
// so a resume replays the leaf from the journal and every prompt built from its
// output stays byte-identical (REQ-474 BR-7). The leaf runs the same
// `adlc_lessons select` call /proceed runs and returns its JSON verbatim.

function lessonsStatePath(id, worktree, repos) {
  const primary = (repos || []).find((r) => r.primary) || (repos || [])[0] || {};
  const root = repoRootFromWorktree(primary.worktree || worktree, id);
  return `${root || '<repoRoot>'}/.adlc/specs/${id}-*/pipeline-state.json`;
}

function lessonsFenceLines(worktree) {
  return [
    `Run ONE shell fence from ${worktree}: the ToolkitRoot root line, then source`,
    '`partials/lessons.sh` with the guarded two-level spelling (conventions.md',
    '"Bash in skills"), then call adlc_lessons in the SAME fence — shell state does',
    'not cross fences.',
  ];
}

function lessonsUnavailableLines() {
  return [
    'If adlc_lessons returns 2 it prints one `lessons: unavailable — <reason>` line:',
    'then use {"query":{"components":[]},"lessons":[],"retrievedAt":"<now, ISO-8601',
    'UTC>","unavailable":"<reason>"} as the set. Never fabricate, reorder or edit an',
    'entry — the JSON the command prints is the set. Retrieval never blocks the REQ.',
  ];
}

function lessonsPrompt(id, worktree, repos, setName) {
  const state = lessonsStatePath(id, worktree, repos);
  const lines = [
    `Lessons retrieval for ${id}: the ${setName} LessonSet (REQ-647), primary worktree`,
    `${worktree}. You are READ-ONLY apart from the one state write the command below`,
    'makes itself (lessons.<set> in the primary-path pipeline-state.json).',
    '',
    ...lessonsFenceLines(worktree),
    `  adlc_lessons select --set ${setName} --root "${worktree}" \\`,
    `    --spec "<the requirement.md under ${worktree}/.adlc/specs/${id}-*/>" \\`,
    `    --state-out "<${state} resolved; the worktree's copy when that spec directory does not exist>" \\`,
  ];
  if (setName === 'step0') {
    lines.push('    --fresh --format json --with-text');
  } else {
    lines.push(
      '    --base "origin/<integrationBranch>" --component "<c>" [--component "<c>" ...] \\',
      '    --format json --with-text',
      '',
      'The components: for EVERY touched repo below, list the paths its branch changes',
      '(`git -C "<worktree>" diff --name-only origin/<integrationBranch>...HEAD`) and',
      'infer each path\'s MOST SPECIFIC component the way /review Step 1 item 7a does',
      '(partials/forge.sh -> adlc/partials/forge; the engine adds the ancestors). One',
      '--component per distinct component, across all repos.',
      `Touched repos: ${(repos || []).map((r) => `${r.repo} @ ${r.worktree} (base origin/${r.integrationBranch || '<resolve>'})`).join('; ')}.`,
    );
  }
  lines.push('', 'Return the JSON it prints VERBATIM as the LESSONS schema object.', ...lessonsUnavailableLines());
  return lines.join('\n');
}

function taskLessonsPrompt(id, worktree, repos, tasks) {
  const state = lessonsStatePath(id, worktree, repos);
  const list = orderByTier(tasks || []).map((t) => `${t.id} — ${t.title || '(untitled)'}`).join('; ') || '(none)';
  return [
    `Lessons retrieval for ${id}: one LessonSet PER TASK (REQ-647 BR-1a), primary`,
    `worktree ${worktree}. You are READ-ONLY apart from the state writes the command`,
    'makes itself (lessons.tasks.<TASK-xxx> in the primary-path pipeline-state.json).',
    '',
    `Tasks, in order: ${list}.`,
    '',
    `For EACH task: read its file under ${worktree}/.adlc/specs/${id}-*/tasks/, take the`,
    'paths under `## Files to Create/Modify`, infer each path\'s MOST SPECIFIC',
    'component the way /review Step 1 item 7a does (partials/forge.sh ->',
    'adlc/partials/forge; the engine adds the ancestors), and run:',
    ...lessonsFenceLines(worktree),
    `  adlc_lessons select --set task --task-id <TASK-xxx> --root "${worktree}" \\`,
    `    --spec "<the requirement.md under ${worktree}/.adlc/specs/${id}-*/>" \\`,
    `    --state-out "<${state} resolved; the worktree's copy when that spec directory does not exist>" \\`,
    '    --component "<c>" [--component "<c>" ...] --format json --with-text',
    '',
    'Return the TASK_LESSONS schema object: sets = one {taskId, set} row per task,',
    'in the order above, where set is the JSON the call printed, VERBATIM.',
    ...lessonsUnavailableLines(),
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

// prePassPrompt — dispatch ONE `delegate-pre-pass` leaf for a single touched repo
// (the citation-scoping boundary, BR-9). The agent does the gate + worktree diff
// + redaction + adlc-read I/O and returns the CANDIDATES schema object; the SCRIPT
// validates the (untrusted) candidates via validateCitations afterward. The agent
// never throws — on any gate/key/api miss it returns invoked-aware degraded data
// (empty candidates), so the panel falls back to candidate-less review. (ADR-8)
function prePassPrompt(id, repo, worktree, base) {
  return [
    `Delegate pre-pass for ${id}, repo ${repo}, worktree ${worktree}.`,
    `Inputs: repo="${repo}"; worktree (absolute)="${worktree}"; REQ="${id}";`,
    `base (resolved integration branch ref)="${base}".`,
    '',
    'Run your full protocol: source the helpers up front, gate (and explicitly',
    'require that a delegate key resolves), diff this worktree vs the base, redact,',
    'ask the delegate for advisory candidates across the 5 reviewer dimensions,',
    'parse stdout VERBATIM, and emit telemetry. Return ONLY the CANDIDATES schema',
    'object. On ANY miss (gate fail, key absent, adlc-read non-zero) return the',
    'degraded object with invoked set correctly and candidates: []. Never throw.',
  ].join('\n');
}

// reviewPrompt — build one panel member's review prompt. `candidates` is the
// VALIDATED per-dimension advisory slice from the delegate pre-pass (already run
// through validateCitations: `..` rejected, path ∈ changedFiles, description
// sanitized). It is passed ONLY for the 5 reviewer dimensions — the reflector is
// always called with `candidates` empty/absent (BR-9). Advisory means advisory:
// the reviewer must independently CONFIRM or REFUTE each candidate, not trust it.
function reviewPrompt(id, worktree, member, repo, manifest, candidates, lessonSet) {
  const advisory = (candidates || []).filter(Boolean);
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
    'fromCandidate (true ONLY when the finding confirms one of the advisory',
    'candidates below; false otherwise — including when there are no candidates).',
  ];
  // Advisory candidate block — reviewers only (the reflector never gets one).
  // The candidates are an UNTRUSTED-origin recall aid that the script already
  // validated; the reviewer must still verify each against the real diff and may
  // refute any of them. (ADR-8, BR-9, LESSON-008 anchoring caveat)
  if (member.dimension !== 'reflector' && advisory.length > 0) {
    lines.push(
      '',
      `Advisory candidates for your ${member.dimension} dimension (a recall aid`,
      'from a fast pre-pass — NOT verified findings). For EACH, independently',
      'CONFIRM it against the actual diff (emit a finding with fromCandidate=true)',
      'or REFUTE it (emit nothing for it). Do NOT trust a candidate on its face,',
      'and do NOT limit your review to this list — find issues it missed too:',
      JSON.stringify(advisory),
    );
  }
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
  // REQ-647 BR-3: the Phase-5 LessonSet, for ALL SIX members. The reflector is
  // told the set was pre-computed and must not grep its own. Only an id from this
  // set escalates a finding (escalateByLessons); '' when no set was retrieved.
  const block = lessonsBlock(lessonSet, member.dimension === 'reflector'
    ? 'Lessons for this diff, PRE-COMPUTED by the engine (REQ-647): use these and do NOT grep .adlc/knowledge/lessons/ yourself. When a finding matches one, set lessonId to its id:'
    : 'Lessons for this diff, pre-computed by the engine (REQ-647). When a finding matches one, set lessonId to its id; only an id from this list counts:');
  if (block) lines.push(block);
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
    '"main"; use the integrationBranch recorded in the repo record (resolved at',
    'Phase 0 by /proceed step 4\'s rule: branches.integration from .adlc/config.yml',
    'when declared, else two-branch repo → "staging", else "main"). (BUG-060, LESSON-036)',
    '',
    'For EACH touched repo (repo @ absolute-worktree, base branch shown):',
    `  ${repoList || '(none)'}`,
    '',
    'Steps per repo, run entirely within the absolute worktree path:',
    '  1. Push the feature branch: `git -C <worktree> push -u origin HEAD`.',
    '  2. Open the PR against the integration branch (forge-neutral — source',
    '     `partials/forge.sh` in the same fence, then call the adapter):',
    '     `adlc_forge_pr_create --base <integrationBranch> --head <featureBranch>`',
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
    '  1. Sanity check: `adlc_forge_pr_view <url> --json files,baseRefName` (source',
    '     `partials/forge.sh` in the same fence) — confirm the diff is coherent (no',
    '     stray build artifacts, debug logs, or unrelated files) and the base branch',
    '     is the intended integration branch.',
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
// legacy topology (pipeline-runner.md Phase 8), the merge MUST run from the
// PARENT repo path, not the worktree. The adapter deletes only the REMOTE branch:
// gh's own --delete-branch removes the worktree holding the branch, and the
// gitignored pipeline-state.json with it (BUG-252). After a successful merge the agent
// sets pipeline-state.json.repos[<repo>].merged = true immediately (resumable,
// no double-merge). The CRITICAL re-verification gate (gh pr view) is enforced by
// the SCRIPT in a SEPARATE leaf (see verifyMergedPrompt) — claim ≠ truth (BR-6).
function mergePrompt(id, repo, pr, blockerCleared) {
  // REQ-485 BR-11: on a blocker-cleared resume, the same write that sets
  // merged=true must also clear this REQ's blockers entry. Omitted (empty) on a
  // first run so the prompt is byte-identical and the journal cache replays.
  const clearStep = blockerCleared
    ? [
        `  4. This is a RESUME of a REQ that was held behind ${blockerCleared}`,
        '     (now merged). In the SAME state write as step 3, CLEAR this REQ\'s',
        '     pipeline-state.json.blockers entry (set its holdState to "resumed",',
        '     then remove the entry) — REQ-485 BR-11. Setting merged=true and',
        '     clearing blockers are distinct writes; do BOTH.',
      ]
    : [];
  return [
    `Phase 8 merge for ${id}: this is a SINGLE-REPO REQ, so YOU own the merge.`,
    `Merge PR ${pr.url} (repo ${repo.repo}) into origin/${repo.integrationBranch || '<integrationBranch-unresolved>'}.`,
    '',
    'Steps:',
    '  1. Confirm the PR is OPEN and MERGEABLE with CI green (forge-neutral —',
    '     source `partials/forge.sh` in the same fence, then call the adapter)',
    `     (\`adlc_forge_pr_view ${pr.url} --json state,mergeStateStatus\`). If it is NOT`,
    '     mergeable due to a MERGE CONFLICT, STOP and report mergeConflict=true —',
    '     do NOT force anything.',
    `  2. Merge from the PARENT repo path (\`${repo.worktree}\`\'s repo root), NOT`,
    '     the worktree. The adapter deletes only the remote branch, so the worktree',
    '     and its state file survive until the close-out removes them (BUG-252):',
    `     \`adlc_forge_pr_merge ${pr.url} --squash --delete-branch\`.`,
    '  3. Immediately set pipeline-state.json.repos[<repo>].merged = true.',
    ...clearStep,
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
    '  run `adlc_forge_pr_view <url> --json state,mergedAt` (forge-neutral — source',
    '  `partials/forge.sh` in the same fence) and report:',
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
async function implement(id, P, worktree, tasks, taskLessonSets) {
  // Sort into ascending dependency tiers. A missing `tier` sorts as tier 0 so a
  // flat (untiered) plan still runs in array order. Sorting is pure JS — the
  // script owns ordering; the agents own the writes. (ADR-3, ADR-5)
  const ordered = orderByTier(tasks);

  // RESUME IDEMPOTENCY (AC-7): read the already-completed task ids from
  // pipeline-state.json.phase4.completedTasks via a read-only IO leaf, so a
  // resumed run SKIPS tasks it already finished+committed instead of re-running
  // (and re-committing) them. The journal cache replays byte-identical calls, but
  // it cannot un-commit a task whose implementer already ran on a prior session;
  // this state read is the authoritative skip signal. Returns [] on a fresh run,
  // so a first run skips nothing and is byte-identical (cache replays). The script
  // has no fs — the read is an agent leaf. (ADR-3)
  const done = await agent(completedTasksPrompt(id, worktree), {
    ...P,
    label: `${id} phase4-completed-read`,
    schema: COMPLETED_TASKS_SCHEMA,
    // Default subagent (no agentType) — a generic read-only state IO worker.
  });
  const completed = new Set((done && done.completedTasks) || []);

  for (const task of ordered) {
    // Skip a task already recorded complete on a prior run — never re-commit it.
    if (completed.has(task.id)) {
      log(`${id} Phase 4: skipping ${task.id} (already in phase4.completedTasks).`);
      continue;
    }

    // ONE writer: await each task-implementer before dispatching the next. Using
    // a serial for-loop (NOT parallel()) is what prevents git-index contention
    // in the shared worktree. task-implementer is the unchanged specialist.
    const report = await agent(implementPrompt(id, worktree, task, (taskLessonSets || {})[task.id]), {
      ...P,
      label: `${id} phase4-${task.id}`,
      agentType: agentTypeFor('task-implementer', AGENT_NS),
    });
    // Keep the implementer's report as close-out evidence (BUG-249). Same
    // prompt bytes as before — capturing the return changes nothing the journal
    // keys on. Unschema'd leaves return text; anything else is stringified.
    if (EVIDENCE.has(id)) {
      EVIDENCE.get(id).reports.push({
        taskId: task.id,
        text: typeof report === 'string' ? report : JSON.stringify(report ?? ''),
      });
    }

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

// orderByTier() — inlined in the PURE block above (pure; unit-tested via node:test). (REQ-474, ADR-10)

// Phase 5 — delegate pre-pass (per repo) → parallel review panel → deterministic
// consolidation. (ADR-7, ADR-8, BR-7, BR-9, BR-10)
//
// Per touched repo the panel fans out: the reflector + the 5 reviewers run
// CONCURRENTLY (read-only, so safe — the only writer was Phase 4). Each returns
// a validated FINDINGS object. The mechanical consolidation — dedupe within a
// repo, cross-repo tagging, severity ranking, and the Critical/mustFix gate —
// runs as PURE JS in `dedupeAndRank()`; NO agent is in that loop (BR-7). A
// reflector `userFacing` finding is a user-answerable halt → RETURN blocked
// (never throw, ADR-6).
//
// BEFORE the panel, one `delegate-pre-pass` leaf runs PER TOUCHED REPO (the citation
// -scoping boundary): it does gate + diff + redaction + adlc-read I/O and returns
// CANDIDATES. The SCRIPT then validates those (untrusted) candidates against the
// TRUSTED changedFiles via validateCitations (rejects `..`, off-diff paths, bad
// charsets; sanitizes descriptions) and asserts `candidates.length > 0 ⇒ invoked`
// — a violation is a ghost-skip, so the candidates are DROPPED and logged. The
// VALIDATED per-dimension slice is fed into ONLY the 5 reviewers' prompts as an
// advisory "confirm or refute" aid; the reflector receives NONE (BR-9). If the
// gate/key is unavailable the agent returns empty candidates and the panel runs
// candidate-less — today's behavior, gracefully. (OQ-1 GO → wired on, not flagged
// off.)
//
// On resume (`ans` set — the user already answered THIS REQ's reflector
// question), the reflector halt is SKIPPED: we do not re-ask a question the user
// already answered; instead the answer is threaded into the Phase-5 fix prompt
// as guidance so the blocking findings are resolved with the user's direction.
// On a first run (`ans` undefined) a reflector `userFacing` finding halts as
// before. This is the surgical resume divergence for the Phase-5 halt. (ADR-6,
// BR-5)
//
// Returns `true` when the panel is clean / non-blocking (the REQ proceeds to
// Phase 6); returns a `{state:'blocked'}` value on a reflector question.
async function verify(id, P, worktree, repos, ans, lessonSet) {
  // The PANEL: agent name + the dimension label it reports under (the FINDINGS
  // `dimension` enum is distinct from the agent name). The reflector leads;
  // the 5 reviewers follow. (PANEL_DIMENSIONS / REVIEWER_DIMENSIONS, PURE block)
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

  // Delegate pre-pass per touched repo → VALIDATED advisory candidates, bucketed by
  // reviewer dimension. This is the ONLY consumer of CANDIDATES; the per-repo map
  // `advisoryByRepo[repo][dimension] = candidate[]` is consulted when each
  // reviewer prompt is built (reflector excluded). Degrades to {} per repo when
  // the gate/key is unavailable. (ADR-8, BR-9)
  const advisoryByRepo = await runPrePass(id, P, worktree, repos);

  // Run the full panel per touched repo. Each repo's reflector + 5 reviewers is
  // ONE parallel() fan-out (single barrier per repo). A failed thunk yields null
  // and is filtered — a dropped reviewer never poisons the consolidation.
  const findingsByRepo = {};
  for (const r of repos) {
    const repoWt = r.worktree || worktree;
    const byDim = advisoryByRepo[r.repo] || {};
    // parallel([]) is unspecified by the runtime contract and a throw would escape
    // verify() (a throw is NOT a halt — ADR-6); guard the empty panel defensively.
    // PANEL is a fixed 6-member literal today, so this is belt-and-suspenders.
    if (PANEL.length === 0) { findingsByRepo[r.repo] = []; continue; }
    const panelFindings = (
      await parallel(
        PANEL.map((m) => () =>
          agent(reviewPrompt(
            id, repoWt, m, r.repo,
            m.dimension === 'architecture' ? MANIFEST : null,
            // Reviewers get their per-dimension slice; the reflector gets none
            // (validateCitations already excludes reflector candidates, but the
            // panelMembers reflector entry would key nothing here anyway). (BR-9)
            m.dimension === 'reflector' ? null : byDim[m.dimension],
            lessonSet, // REQ-647 BR-3 — every member, the reflector included
          ), {
            ...P,
            label: `${id} phase5-${r.repo}-${m.dimension}`,
            schema: FINDINGS,
            agentType: agentTypeFor(m.agent, AGENT_NS),
          }),
        ),
      )
    ).filter(Boolean);
    findingsByRepo[r.repo] = panelFindings;
  }

  // A reflector `userFacing` finding is a question for the user — HALT, but ONLY
  // when the user has NOT already answered it. On resume (`ans` set) we skip the
  // halt and let the answer flow into the Phase-5 fix below as guidance, so the
  // REQ advances past the halt instead of re-asking. Checked BEFORE consolidation
  // /fix so a first run never silently fixes past an open question. (BR-4 halt #2,
  // BR-5 resume, System Model event halt:reflector-question)
  const questions = reflectorQuestions(findingsByRepo);
  // Whether THIS pass surfaced a reflector userFacing question. On resume the halt
  // above is skipped, but the user's reply must still REACH the artifact: a typical
  // reflector question is `mustFix:false` ⇒ `blocks:false`, so the blocks-driven fix
  // path below would never fire and the human's answer would be silently discarded.
  // Capture the flag here so the resume path can dispatch a guidance-carrying apply
  // agent EVEN WHEN nothing blocks. (BR-5 resume, halt:reflector-question)
  const hadReflectorQ = questions.length > 0;
  if (hadReflectorQ && !ans) {
    return blocked(id, 'reflector-questions', { questions });
  }

  // Deterministic consolidation: dedupe within repo, tag cross-repo issues, rank
  // by severity, and decide whether merge is blocked (any Critical or mustFix).
  // REQ-647 BR-6: a finding whose lessonId is in the Phase-5 set escalates one
  // level BEFORE dedupe (an id outside the set is dropped, never escalates), and
  // dedupe unions lesson ids across duplicates.
  let consolidated = dedupeAndRank(escalateByLessons(findingsByRepo, lessonSet));

  // Did the resumed user actually answer a reflector question this pass? If so the
  // answer MUST change the artifact even when consolidation does not block (the
  // common case: a `mustFix:false` reflector question). This is the Critical
  // resume-answer-propagation fix: without it `ans` is consumed only by the
  // blocks-gated fix below and a non-blocking reflector reply is lost, letting the
  // REQ proceed as if the human had been heeded. (BR-5)
  const applyResumeAnswer = Boolean(ans) && hadReflectorQ;

  if (consolidated.blocks || applyResumeAnswer) {
    // Dispatch ONE serial fix pass in the shared worktree (one writer, ADR-5)
    // addressing the blocking findings, then conditionally RE-VERIFY only the
    // (repo,dimension) pairs that had fixes — and only the 5 REVIEWERS, never
    // the reflector (a reflector re-run could only surface a NEW question, which
    // is out of this ≤1 re-verify loop's contract). Bounded to ONE loop. (AC-5)
    //
    // TWO triggers reach this block: (a) `consolidated.blocks` — a Critical/mustFix
    // finding that must be fixed; (b) `applyResumeAnswer` — the user answered a
    // reflector question on resume and that answer must change the artifact even if
    // nothing blocks. In case (b) `consolidated.blocking` is empty, so the fix agent
    // applies the GUIDANCE alone and `fixedPairs([])` is `{}` (the re-verify loop is
    // a no-op) — the human's reply still lands in the worktree. (BR-5)
    //
    // On resume the user's guidance is appended to the fix prompt (the halt-prone
    // Phase-5 site), so the answer to the reflector question — or to whatever the
    // user was asked — directs the fix. Empty on a first run (cache replays). (BR-5)
    const fixGuidance = ans ? ` — user guidance: ${ans}` : '';
    await agent(fixFindingsPrompt(id, worktree, consolidated.blocking) + fixGuidance, {
      ...P,
      label: `${id} phase5-fix`,
      agentType: agentTypeFor('task-implementer', AGENT_NS),
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
      const byDim = advisoryByRepo[repoId] || {};
      const members = PANEL.filter((m) => m.dimension !== 'reflector' && dims.includes(m.dimension));
      // parallel([]) is unspecified by the runtime contract and a throw here would
      // escape verify() (a throw is NOT a halt — ADR-6); guard the empty fan-out.
      if (members.length === 0) { reverified[repoId] = []; continue; }
      const re = (
        await parallel(
          members.map((m) => () =>
            agent(reviewPrompt(
              id, repoWt, m, repoId,
              m.dimension === 'architecture' ? MANIFEST : null,
              byDim[m.dimension], // reviewer-only re-check keeps its advisory slice (BR-9)
              lessonSet, // REQ-647 BR-3
            ), {
              ...P,
              label: `${id} phase5-reverify-${repoId}-${m.dimension}`,
              schema: FINDINGS,
              agentType: agentTypeFor(m.agent, AGENT_NS),
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
    consolidated = dedupeAndRank(escalateByLessons(merged, lessonSet));
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
  // Keep the consolidated findings as close-out evidence (BUG-249) — this data
  // used to be discarded here, which left the Step-8b lesson with nothing to
  // cite. The return contract (`true` | blocked) is unchanged.
  if (EVIDENCE.has(id)) EVIDENCE.get(id).findings = consolidated.findings;
  return true;
}

// ===========================================================================
// retrieveLessons(id, P, prompt, label, schema) — dispatch one REQ-647 retrieval
// leaf. Retrieval is never a gate (BR-7): a leaf that throws or returns nothing
// yields an `unavailable` value the log line reports, and the prompts built from
// it carry no lessons block. Never throws. (BR-6)
// ===========================================================================
async function retrieveLessons(id, P, prompt, label, schema) {
  const unavailable = (why) => (schema === TASK_LESSONS
    ? { sets: [] }
    : { query: { components: [] }, lessons: [], retrievedAt: '', unavailable: why });
  try {
    const value = await agent(prompt, {
      ...P,
      label: `${id} lessons-${label}`,
      schema,
      // Default workflow subagent (no agentType) — a generic read-only IO worker
      // running the inline adlc_lessons call.
    });
    return value || unavailable('retrieval leaf returned nothing');
  } catch (e) {
    log(`${id} lessons-${label}: retrieval leaf threw — ${e && e.message ? e.message : String(e)}`);
    return unavailable('retrieval leaf threw');
  }
}

// ===========================================================================
// runPrePass(id, P, worktree, repos) — dispatch the delegate pre-pass per touched
// repo, validate the (untrusted) candidates in JS, enforce the ghost-skip
// assertion, and return a per-repo map of VALIDATED candidates bucketed by
// reviewer dimension. (ADR-8, BR-9, BR-10, LESSON-008, LESSON-012)
//
// One `delegate-pre-pass` leaf per repo is the citation-scoping boundary: its
// `changedFiles` is the TRUSTED diff of THAT repo's worktree, and a candidate is
// only forwarded if its path is in that repo's changedFiles. The agent never
// throws — on a gate/key/api miss it returns invoked-aware degraded data (empty
// candidates), so a miss degrades the repo to candidate-less review.
//
// Per repo:
//   1. agent('delegate-pre-pass', schema: CANDIDATES) — gate + diff + adlc-read I/O.
//   2. GHOST-SKIP ASSERTION: candidates.length > 0 ⇒ invoked. A violation means
//      the agent claimed candidates without actually invoking adlc-read (a ghost
//      -skip wearing a result); DROP every candidate and log it. The script-side
//      schema assertion replaces the legacy skill-flag dance (LESSON-012).
//   3. validateCitations(candidates, changedFiles) — the LESSON-008 boundary.
//   4. candidatesByDimension(validated) — bucket the survivors for the reviewers.
//
// Returns { [repo]: { [dimension]: candidate[] } }. A repo with no usable
// candidates maps to {} (so the reviewers run candidate-less for it).
async function runPrePass(id, P, worktree, repos) {
  const advisoryByRepo = {};
  for (const r of repos) {
    const repoWt = r.worktree || worktree;
    const base = `origin/${r.integrationBranch || '<integrationBranch-unresolved>'}`;
    // The pre-pass leaf returns CANDIDATES (schema-validated). It never throws;
    // a parallel/agent drop yields null, which we treat as "no candidates".
    const CAND = await agent(prePassPrompt(id, r.repo, repoWt, base), {
      ...P,
      label: `${id} phase5-prepass-${r.repo}`,
      schema: CANDIDATES,
      agentType: agentTypeFor('delegate-pre-pass', AGENT_NS),
    });

    if (!CAND) { advisoryByRepo[r.repo] = {}; continue; }

    const raw = CAND.candidates || [];
    // Ghost-skip assertion: candidates without an actual invocation are rejected.
    if (raw.length > 0 && CAND.invoked !== true) {
      log(
        `${id} Phase 5 pre-pass (${r.repo}): ghost-skip — ${raw.length} candidate(s) `
        + `returned with invoked=false (gateReason=${CAND.gateReason}); dropping them.`,
      );
      advisoryByRepo[r.repo] = {};
      continue;
    }

    // LESSON-008 boundary: validate the untrusted candidates against the TRUSTED
    // per-repo changedFiles before any of them reaches a reviewer prompt.
    const validated = validateCitations(raw, CAND.changedFiles || []);
    if (validated.length < raw.length) {
      log(
        `${id} Phase 5 pre-pass (${r.repo}): dropped ${raw.length - validated.length} `
        + `candidate(s) failing citation validation (traversal / off-diff / bad path).`,
      );
    }
    advisoryByRepo[r.repo] = candidatesByDimension(validated);
  }
  return advisoryByRepo;
}

// dedupeAndRank(), dedupeKey(), cmp(), validateCitations(), sanitizeDescription(), candidatesByDimension(), reflectorQuestions(), fixedPairs(), mergeReverified(), panelMembers() — inlined in the PURE block above (pure; unit-tested via node:test). (REQ-474, ADR-10)

// Phase 6 — open PR(s) based on the RESOLVED integration branch. ONE IO agent
// pushes each touched repo's branch and opens its PR against
// origin/<integrationBranch> (never a hardcoded main — BUG-060). Returns the PRS
// schema object the later phases re-verify. (ADR-3, ADR-7, BR-2)
async function openPRs(id, P, repos) {
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
async function cleanupAndWatchCI(id, P, PR_STATE) {
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
async function wrapupAndMerge(id, P, repos, PR_STATE, blockerCleared) {
  const prs = (PR_STATE && PR_STATE.prs) || [];
  const touched = repos || [];
  // REQ-485 BR-11: when this Phase-8 is the resume of a previously-held REQ
  // (blockerCleared is set), the single-repo merge agent below must, on a
  // successful merge, clear this REQ's pipeline-state.json.blockers entry in the
  // SAME write that sets repos[<id>].merged = true — so a later blocker-merged
  // event does not re-process an already-merged REQ. `mergePrompt` is told to do
  // the clear when `blockerCleared` is set; on a first run it is undefined and the
  // prompt is byte-identical (cache replay). The clear is the idempotency anchor
  // for the unblock pass (which considers only REQs with a live blockers entry).

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
  // On a blocker-cleared resume the prompt also instructs the BR-11 blockers clear.
  const mergeResult = await agent(mergePrompt(id, repo, pr, blockerCleared), {
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

// allMerged(), stripVerifyMarkers() — inlined in the PURE block above (pure; unit-tested via node:test). (REQ-474, ADR-10)

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
    'For EACH PR, in a sensible order (dependency/mergeOrder if one is recorded).',
    'All PR ops are forge-neutral — source `partials/forge.sh` in the same fence,',
    'then call the adapter:',
    '  1. Confirm OPEN + MERGEABLE + CI green',
    '     (`adlc_forge_pr_view <url> --json state,mergeStateStatus`). On a real MERGE',
    '     CONFLICT, STOP and report mergeConflict=true — do not force.',
    '  2. Merge from the repo\'s PARENT path, not the worktree (the adapter deletes',
    '     only the remote branch, so the worktree survives — BUG-252):',
    '     `adlc_forge_pr_merge <url> --squash --delete-branch`.',
    '  3. Immediately set pipeline-state.json.repos[<repo>].merged = true.',
    '',
    'Report mergeConflict (true ONLY on a real conflict) and merged (true if every',
    'PR merge command ran without error). The script re-verifies each merge with',
    '`gh pr view` — your claim is not accepted on its own.',
  ].join('\n');
}

// ===========================================================================
// Self-healing serialization (REQ-485) — the post-merge unblock pass.
//
// After the merge barrier, some REQs may have merged that OTHER REQs were held
// behind (a Phase-8 trial-merge conflict against an ahead REQ — REQ-483). This
// pass auto-rebases each held REQ onto the refreshed integration branch and, on a
// clean rebase, resumes it (re-runs its now-passing Phase-8 gate + merge). A
// conflicting rebase aborts non-mutatingly and re-halts (BR-4); the retry bound
// caps auto-retries (BR-10). The pass mutates ONLY each held REQ's own worktree
// (BR-5), via leaf agents (the script owns control flow only). With nothing newly
// merged it is a no-op (BR-6 idempotency). v1 is WITHIN-RUN only (BR-9): the set
// of "now-merged blocker ids" comes from THIS run's results, never a cross-session
// poll. A blocker that ended `failed` also releases REQs held SOLELY on it
// (OQ-5 / ADR-8) — its dead PR will never fire a merge event otherwise.
// ===========================================================================
async function unblockHeldReqs(results, todo) {
  const all = results || [];

  // The set of blocker ids whose constraint has dissolved THIS run: any REQ that
  // merged, plus (OQ-5) any REQ that ended `failed`/abandoned — both mean "no
  // future merge of this blocker will fire, so stop holding behind it". (BR-9:
  // within-run only — derived from results, not a cross-session watch.)
  const clearedBlockers = new Set(
    all.filter((t) => t && (t.state === 'merged' || t.state === 'failed')).map((t) => t.id),
  );
  if (clearedBlockers.size === 0) return all; // nothing merged/failed → no-op (BR-6)

  // Find the held REQs via ONE read-only IO leaf (the script has no fs). It scans
  // every OTHER REQ's pipeline-state.json for a STILL-PRESENT blockers entry whose
  // blockedBy is in clearedBlockers (the BR-11 anchor: a cleared entry is skipped).
  // It returns each held REQ's own worktree + resumePhase + prior rebaseAttempts.
  const heldScan = await agent(findHeldPrompt(Array.from(clearedBlockers), todo), {
    phase: 'unblock',
    label: 'unblock-scan',
    schema: HELD_REQS_SCHEMA,
    // Default workflow subagent — read-only state scan, no agentType.
  });
  let held = (heldScan && heldScan.held) || [];
  if (held.length === 0) return all; // no live holds on the cleared blockers (BR-6)

  // Deterministic order (BR-6): the scan returns earliest-published-first; enforce
  // a stable lower-REQ tiebreak here in pure JS so two held REQs never race.
  held = held.slice().sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  // Process held REQs ONE AT A TIME (serialized — BR-6): the held REQs may
  // themselves overlap, so a clean rebase + resume of one can change the base the
  // next one rebases onto. NO parallel() here — that is the load-bearing safety.
  const updatedById = {};
  for (const h of held) {
    const term = await unblockOneReq(h);
    if (term) updatedById[h.id] = term;
  }

  // Stitch the updated terminals back over the original results (order preserved).
  return all.map((t) => (t && updatedById[t.id]) ? updatedById[t.id] : t);
}

// unblockOneReq — rebase + resume ONE held REQ. Rebase via an IO leaf in its OWN
// worktree (BR-5); clean → resume from its recorded phase by calling runReq with
// the blocker-cleared signal threaded through args (the early phases replay from
// the journal cache, only Phase-8 diverges to re-run the now-passing gate + merge,
// BR-3/BR-8); conflict → the leaf already aborted (non-mutating, BR-4), so re-halt
// blocked with the materialized files, marking needs-manual-rebase once the retry
// bound is hit (BR-10). NEVER auto-resolve (ethos #6).
async function unblockOneReq(h) {
  const P = { phase: h.id };
  const attempts = typeof h.rebaseAttempts === 'number' ? h.rebaseAttempts : 0;

  const rebase = await agent(rebasePrompt(h), {
    ...P,
    label: `${h.id} unblock-rebase`,
    schema: REBASE_RESULT_SCHEMA,
    // Default workflow subagent — git rebase/abort IO worker in the held worktree.
  });

  if (rebase && rebase.clean === true) {
    // Clean rebase → resume from the recorded phase. Thread the blocker-cleared
    // signal so ONLY this REQ's Phase-8 diverges from the cache (BR-3/BR-8). On a
    // resume that reaches merge the merge leaf also clears blockers (BR-11).
    args.blockerCleared = args.blockerCleared || {};
    args.blockerCleared[h.id] = h.blockedBy;
    return await runReq(h.id);
  }

  // Conflicting rebase: the leaf already ran `rebase --abort` (worktree restored).
  // Increment attempts; at/over the bound, stop auto-retrying and mark
  // needs-manual-rebase (BR-10 / OQ-6) — else re-halt held for a later pass.
  const nextAttempts = attempts + 1;
  const conflictFiles = (rebase && rebase.conflictFiles) || [];
  if (nextAttempts >= AUTO_REBASE_MAX_ATTEMPTS) {
    return blocked(h.id, 'needs-manual-rebase', {
      reason: `auto-rebase conflicted ${nextAttempts}x (bound ${AUTO_REBASE_MAX_ATTEMPTS}); manual rebase needed`,
      conflictFiles,
      resolvedBlocker: h.blockedBy,
      holdState: 'needs-manual-rebase',
      rebaseAttempts: nextAttempts,
    });
  }
  return blocked(h.id, 'merge-conflict', {
    reason: `rebase onto refreshed base conflicted after ${h.blockedBy} merged; resolve and resume`,
    conflictFiles,
    holdState: 'held',
    rebaseAttempts: nextAttempts,
  });
}

// findHeldPrompt — the read-only scan leaf. Reports REQs with a STILL-PRESENT
// blockers entry blocked on a now-cleared blocker (BR-11 anchor). Degrade-safe:
// a held REQ whose worktree is gone or whose currentPhase is unrecorded is
// reported with a note and the script skips it (it cannot be auto-resumed) — never
// an error (BR-7). The retry bound is read from .adlc/config.yml here.
function findHeldPrompt(clearedBlockers, todo) {
  const ids = (todo || []).map((r) => r.id).join(', ');
  return [
    'Self-healing unblock scan (REQ-485). Some REQs just merged or failed within',
    'this /sprint run; find every OTHER REQ that was HELD behind one of them and is',
    'now eligible to auto-rebase + resume.',
    '',
    `Blockers whose constraint dissolved this run (merged or failed): ${clearedBlockers.join(', ') || '(none)'}.`,
    `Candidate REQ ids in this run: ${ids || '(none)'}.`,
    '',
    'For EACH candidate REQ, read its pipeline-state.json and report it ONLY if:',
    '  - it has a STILL-PRESENT blockers entry (a cleared/absent entry means it',
    '    already resumed+merged — skip it; this is the BR-11 idempotency anchor),',
    '    AND',
    '  - that entry\'s blockedBy is one of the dissolved blockers above (for a',
    '    `failed` blocker, include the REQ ONLY if that is its SOLE live blocker —',
    '    OQ-5/ADR-8; a REQ with other live blockers stays held).',
    '',
    'For each reported held REQ return: id, blockedBy, worktree (its OWN',
    'repos[<id>].worktree — never another REQ\'s), resumePhase (its currentPhase),',
    'and rebaseAttempts (its blockers.rebaseAttempts, or 0).',
    '',
    'DEGRADE-SAFE (BR-7): if a held REQ\'s worktree is gone or its currentPhase is',
    'unrecorded, DO NOT include it (it cannot be auto-resumed) — note it in detail',
    'so the orchestrator surfaces a "manual resume needed" advisory. Never error.',
    '',
    'Also read .adlc/config.yml `auto_rebase_max_attempts` if present (default 1) so',
    'the caller can apply the retry bound. Return ONLY the schema object; do NOT',
    'rebase, merge, or modify anything in this read-only scan.',
  ].join('\n');
}

// rebasePrompt — the per-held-REQ rebase IO leaf. Operates ONLY in the held REQ's
// own worktree (BR-5); fetches the integration branch (fresh tip — LESSON-036),
// rebases, and on conflict ALWAYS `git rebase --abort` (non-mutating restore,
// BR-4) before reporting. NEVER auto-resolves / forces (ethos #6).
function rebasePrompt(h) {
  return [
    `Auto-rebase the held REQ ${h.id} after its blocker ${h.blockedBy} merged`,
    '(REQ-485 self-healing serialization). Operate ONLY in this REQ\'s OWN worktree;',
    'do NOT touch the blocker\'s branch/PR or any other REQ\'s worktree (BR-5).',
    '',
    `Worktree: ${h.worktree}`,
    '',
    'Steps (use `git -C <worktree>` form, quote every path):',
    `  1. git -C "${h.worktree}" fetch origin <integrationBranch>   # fresh tip (LESSON-036)`,
    `  2. git -C "${h.worktree}" rebase origin/<integrationBranch>`,
    '  3a. SUCCESS → report clean=true (no conflictFiles).',
    `  3b. CONFLICT → git -C "${h.worktree}" rebase --abort  (restore the worktree,`,
    '      non-mutating — BR-4), then report clean=false with conflictFiles = the',
    '      paths that conflicted. NEVER resolve, -X force, or "merge anyway".',
    '',
    'Resolve <integrationBranch> from the worktree\'s repo by /proceed step 4\'s rule',
    '(branches.integration from .adlc/config.yml when declared, else two-branch →',
    'staging, else main; NEVER hardcode main — LESSON-036). Return ONLY the schema object.',
  ].join('\n');
}

// groupCrossRepoReqs(), sharesRepo() — inlined in the PURE block above (pure; unit-tested via node:test). (REQ-474, ADR-10)

// ===========================================================================
// Step-8b close-out pass (BUG-249). Runs ONCE, after the unblock pass, over the
// final terminals: every `merged` REQ gets the close-out half of Phase 8 that
// `/proceed` Step 8b requires of whoever performed the merge (Step 8c) —
// `/wrapup --close-out` in a dedicated `<repoRoot>/.worktrees/<id>-close-out`
// worktree: spec status → complete, the five-field terminal record plus
// `closeOut` in the PRIMARY-PATH pipeline-state.json, knowledge capture from the
// in-memory EVIDENCE, a squash-merged `chore(<id>): close-out` PR, then teardown
// of the close-out AND feature worktrees. Groups run in parallel across primary
// repos and serially within one (one writer per repo — contract 4). The result
// keeps `state:'merged'` and stamps `closeOut` (+ `closeOutDetail`) beside it;
// the unblock pass already ran, so a failed close-out can never delay a release.
// A leaf drop or throw is caught → closeOut:'failed' (never a thrown pipeline
// item, never a downgraded state). (BUG-249 contracts 2–5)
// ===========================================================================
async function closeOutMerged(results, todo) {
  const all = results || [];
  const primaryRepoById = {};
  for (const t of all) {
    if (!t) continue;
    const ev = EVIDENCE.get(t.id);
    const repos = (ev && ev.repos) || [];
    const primary = repos.find((r) => r.primary) || repos[0];
    primaryRepoById[t.id] = primary ? primary.repo : '<unknown>';
  }
  const groups = groupMergedByRepo(all, primaryRepoById);
  if (groups.length === 0) return all;

  const byId = {};
  for (const t of all) if (t) byId[t.id] = t;
  await parallel(groups.map((ids) => async () => {
    for (const id of ids) byId[id] = await closeOutOneReq(id, byId[id]);
  }));
  // `todo` is accepted for symmetry with the sibling passes; the grouping keys
  // on EVIDENCE (Phase-0 repo records), which is the engine's own trusted data.
  void todo;
  return all.map((t) => (t && byId[t.id]) || t);
}

async function closeOutOneReq(id, term) {
  const P = { phase: id };
  const ev = EVIDENCE.get(id);
  if (!ev || !ev.repos || ev.repos.length === 0) {
    // No Phase-0 record in memory (an unblock-resumed REQ whose runReq dropped
    // before Phase 0 recorded repos) — nothing to close out from; say so.
    return { ...term, closeOut: 'skipped', closeOutDetail: 'no Phase-0 repo records in memory for this REQ' };
  }
  try {
    const result = await agent(closeOutPrompt(id, ev, term), {
      ...P,
      label: `${id} phase8-close-out`,
      schema: CLOSE_OUT_RESULT_SCHEMA,
      // Default workflow subagent (no agentType) — a generic git/gh/skill IO
      // worker driven by the inline prompt. (ethos #6)
    });
    if (!result || !result.closeOut) {
      return { ...term, closeOut: 'failed', closeOutDetail: 'close-out leaf returned no result' };
    }
    const out = { ...term, closeOut: result.closeOut };
    if (result.detail) out.closeOutDetail = result.detail;
    return out;
  } catch (e) {
    return { ...term, closeOut: 'failed', closeOutDetail: `close-out leaf threw: ${e && e.message ? e.message : String(e)}` };
  }
}

// closeOutPrompt — the Step-8b close-out IO leaf. Byte-identical on a cache
// replay (the digest is built from cached leaf outputs); diverges only when the
// user answered a close-out failure (`ev.ans`, copied from runReq's single read
// of args.answers) so a resume RETRIES instead of replaying the failure.
function closeOutPrompt(id, ev, term) {
  const repos = ev.repos || [];
  const primary = repos.find((r) => r.primary) || repos[0];
  const ib = primary.integrationBranch || '<integrationBranch-unresolved>';
  const root = repoRootFromWorktree(primary.worktree, id);
  const rootText = root || '<the parent of the `.worktrees` directory that holds the recorded worktree — read it from `git worktree list --porcelain`>';
  const closeOutWt = root ? `${root}/.worktrees/${id}-close-out` : `<repoRoot>/.worktrees/${id}-close-out`;
  const prs = ((term && term.prs) || []).map((p) => `${p.repo}: ${p.url}`).join('; ') || '<none recorded>';
  const featureWts = repos.map((r) => `${r.repo}: ${r.worktree}`).join('; ');
  const status = closeOutEvidenceStatus(ev);
  const guidance = ev.ans ? ` — user guidance: ${ev.ans}` : '';
  return [
    `Phase 8 close-out for ${id} (BUG-249): the feature PR(s) are MERGED — ${prs}.`,
    'This is /proceed Step 8b, owed by whoever performed the merge (Step 8c). Run it',
    'as the wrapup skill\'s CLOSE-OUT MODE (wrapup/SKILL.md "Close-out mode"), which',
    'never merges a feature PR, never deploys, and drafts knowledge ONLY from the',
    'run evidence supplied below.',
    '',
    `Primary repo: ${primary.repo}. Repo root: ${rootText}. Integration branch: ${ib}.`,
    `Recorded feature worktree(s): ${featureWts}.`,
    `Close-out worktree: ${closeOutWt} on branch chore/${id}-close-out.`,
    '',
    'Steps (use `git -C <path>` form, quote every path; PR ops are forge-neutral —',
    'source `partials/forge.sh` in the same fence, then call the adapter):',
    `  1. git -C "<repoRoot>" fetch origin ${ib}; then create the close-out worktree`,
    `     IDEMPOTENTLY (reuse it if it already exists — resume): git -C "<repoRoot>"`,
    `     worktree add "${closeOutWt}" -b chore/${id}-close-out origin/${ib}.`,
    `  2. Run \`/wrapup ${id} --close-out\` with the line`,
    `     \`WORKTREE PATH (mandatory): ${closeOutWt}\` and hand it the run evidence`,
    '     below VERBATIM. If your harness cannot invoke a skill, perform the mode\'s',
    '     steps exactly as wrapup/SKILL.md "Close-out mode" writes them: its Step 1,',
    '     Step 3 (artifact statuses + the terminal record), Step 4 (knowledge),',
    '     Step 5 (summary), then the close-out commit. The mode:',
    '       - confirms the feature PR(s) are MERGED first (refuses otherwise);',
    `       - writes ALL FIVE terminal-record fields to the PRIMARY-PATH state file`,
    `         <repoRoot>/.adlc/specs/${id}-*/pipeline-state.json — completed:true,`,
    '         currentPhase:8, 8 appended to completedPhases, a phase-8 phaseHistory',
    '         entry naming the merge commit, repos[<id>].merged:true for every touched',
    '         repo — plus closeOut:{status:"ok", at:<ISO timestamp>} (BUG-193 list);',
    `       - commits \`chore(${id}): close-out — spec complete[, LESSON-nnn]\`, pushes,`,
    '         opens a PR with adlc_forge_pr_create and squash-merges it with',
    '         adlc_forge_pr_merge <url> --squash --delete-branch (check branch_deleted —',
    '         BUG-195); its summary ends with a `### Lessons captured` section.',
    '  3. After the mode returns: remove the close-out worktree AND every recorded',
    '     feature worktree by absolute path (git -C "<repoRoot>" worktree remove',
    '     "<path>"), then git -C "<repoRoot>" branch -D the feature branch if the',
    '     squash-merge left it behind, and git -C "<repoRoot>" fetch --prune.',
    '  4. If ANY step fails: write closeOut:{status:"failed", reason:"<why>"} into the',
    '     same primary-path state file (change nothing else), do NOT retry or force',
    '     any merge, leave an unmergeable chore PR open and report its URL, and',
    '     report closeOut=failed with the reason.',
    '',
    `Run evidence for ${id} (evidence status: ${status}):`,
    closeOutDigest(ev),
    status === 'none'
      ? 'No findings or reports were captured for this REQ: the mode must write NO lesson and record `NO_ENTRY: close-out had no run evidence` in the summary.'
      : 'Any lesson written must cite one of these findings/reports (or the task files / merged PR file list the mode reads itself) — never invent an attribution.',
    `pipeline-state.json for ${id} (primary path) carries phaseHistory, blockers and conflictsResolved — read it there; the close-out worktree has no state file.`,
    '',
    'Report ONLY the schema object: closeOut (ok | failed | skipped), detail (the',
    'lesson ids written, the NO_ENTRY line, or the failure reason), chorePr (the',
    `close-out PR url when one was opened).${guidance}`,
  ].join('\n');
}
