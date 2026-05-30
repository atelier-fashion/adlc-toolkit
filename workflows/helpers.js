// workflows/helpers.js — the PURE, deterministic helpers for the `adlc-sprint`
// Dynamic Workflows engine, extracted from `adlc-sprint.workflow.js` so they can
// be unit-tested with `node:test` (the workflow script itself runs only inside
// the Workflow runtime and cannot be imported by a plain Node test). (REQ-474,
// ADR-7, ADR-10)
//
// Every function here is a PURE function of its arguments: no ambient `agent` /
// `parallel` / `pipeline` / `log` / `args` / `phase` / `budget` runtime global,
// and — like the workflow runtime contract — NO `Date.now()`, `Math.random()`,
// `new Date()`, fs, or shell. Two runs on two machines produce byte-identical
// output. This is exactly the property the tests pin down (the LESSON-008
// citation boundary and the BR-7 consolidation gate must never silently
// regress).
//
// This is a CommonJS module (`module.exports`), matching `schemas.js`, so both
// the workflow engine (`require('./helpers.js')`) and the test harness
// (`node --test workflows/tests/`) load the SAME definitions. Run the tests:
//
//     node --test workflows/tests/
//
// See workflows/tests/README.md.

// The 5 reviewer dimensions are defined ONCE in schemas.js (the contract source of
// truth) and imported here, so `validateCitations` and `fixedPairs` cannot drift
// from the CANDIDATES enum. The only `require` permitted from a helper is this
// sibling schemas module. (REQ-474, ADR-7, ADR-10)
const { REVIEWER_DIMENSIONS } = require('./schemas.js');

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
      byRepoKey.set(rk, {
        ...f,
        mustFix: Boolean(f.mustFix),
        userFacing: Boolean(f.userFacing),
        dimensions: [f.dimension],
      });
      continue;
    }
    // Merge into the survivor.
    if (SEVERITY_RANK[f.severity] < SEVERITY_RANK[prev.severity]) {
      prev.severity = f.severity;
    }
    prev.mustFix = prev.mustFix || Boolean(f.mustFix);
    prev.userFacing = prev.userFacing || Boolean(f.userFacing);
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
// security boundary for the Kimi pre-pass. (ADR-8, BR-9, BR-10)
//
// The `kimi-pre-pass` agent transcribes Kimi's UNTRUSTED stdout into candidate
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

module.exports = {
  blocked,
  failed,
  terminalValue,
  selectEligible,
  orderByTier,
  dedupeAndRank,
  dedupeKey,
  cmp,
  validateCitations,
  sanitizeDescription,
  candidatesByDimension,
  reflectorQuestions,
  fixedPairs,
  mergeReverified,
  panelMembers,
  allMerged,
  stripVerifyMarkers,
  groupCrossRepoReqs,
  sharesRepo,
};
