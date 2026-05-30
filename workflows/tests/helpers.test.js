// workflows/tests/helpers.test.js — deterministic unit tests for the PURE
// `adlc-sprint` workflow helpers (workflows/helpers.js). (REQ-474, TASK-063,
// ADR-10)
//
// These are the "Verify, Don't Trust" backstop for the parts of the engine that
// can silently fail: the LESSON-008 citation boundary (`validateCitations`), the
// BR-7 review consolidation gate (`dedupeAndRank`), the BR-12 Preflight max-5
// bound (`selectEligible`), and the cross-REQ merge grouping (`groupCrossRepoReqs`).
// The orchestration itself is dogfooded via `/sprint --workflow`; only the pure,
// security-critical helpers get unit coverage here.
//
// Runner: Node's BUILT-IN `node:test` + `node:assert` — ZERO new dependencies
// (the toolkit has no JS package manager). Run from the toolkit root:
//
//     node --test workflows/tests/
//
// See workflows/tests/README.md.

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

// Resolve the module-under-test relative to this file so the suite runs
// identically from any cwd (the toolkit root, a worktree, or CI).
const helpers = require(path.join(__dirname, '..', 'helpers.js'));
const {
  validateCitations,
  sanitizeDescription,
  candidatesByDimension,
  dedupeAndRank,
  selectEligible,
  orderByTier,
  groupCrossRepoReqs,
  blocked,
  failed,
} = helpers;

// ===========================================================================
// validateCitations — the LESSON-008 security boundary. The MANDATORY cases
// (task AC): reject `..`, off-`changedFiles` paths, charset violations
// (spaces / shell metachars), and reflector/unknown dimensions; sanitize the
// description; accept a valid in-diff candidate.
// ===========================================================================

test('validateCitations: accepts a valid in-diff reviewer candidate', () => {
  const changed = ['src/app.js', 'lib/util.js'];
  const cands = [{ dimension: 'security', path: 'src/app.js', description: 'SQL injection risk', lineRange: '10-20' }];
  const out = validateCitations(cands, changed);
  assert.equal(out.length, 1);
  assert.deepEqual(out[0], {
    dimension: 'security',
    path: 'src/app.js',
    description: 'SQL injection risk',
    lineRange: '10-20',
  });
});

test('validateCitations: REJECTS directory traversal (..) paths (LESSON-008)', () => {
  const changed = ['src/app.js'];
  const cands = [
    { dimension: 'security', path: '../etc/passwd', description: 'x' },
    { dimension: 'security', path: 'src/../../../secret', description: 'x' },
    { dimension: 'security', path: 'a/../b.js', description: 'x' },
  ];
  assert.deepEqual(validateCitations(cands, changed), []);
});

test('validateCitations: REJECTS paths absent from changedFiles (anchors to real diff)', () => {
  const changed = ['src/app.js'];
  // Charset-valid + traversal-free, but NOT a changed file → dropped.
  const cands = [{ dimension: 'correctness', path: 'src/other.js', description: 'x' }];
  assert.deepEqual(validateCitations(cands, changed), []);
});

test('validateCitations: REJECTS charset violations — spaces, shell metachars, NUL', () => {
  // Each path is listed in changedFiles so the ONLY reason to drop is the
  // charset allowlist ^[A-Za-z0-9_./-]+$ — proving the regex, not the diff check.
  const bad = [
    'src/a b.js',          // space
    'src/a;rm -rf.js',     // shell metachar + space
    'src/$(whoami).js',    // command substitution
    'src/a|b.js',          // pipe
    'src/a\u0000b.js',      // NUL byte (control char)
    'src/a\tb.js',          // tab (control char)
    'src/a`b`.js',         // backtick
    'src/a&b.js',          // ampersand
  ];
  const changed = bad.slice();
  const cands = bad.map((p) => ({ dimension: 'quality', path: p, description: 'x' }));
  assert.deepEqual(validateCitations(cands, changed), []);
});

test('validateCitations: REJECTS the reflector dimension and unknown dimensions', () => {
  const changed = ['src/app.js'];
  const cands = [
    { dimension: 'reflector', path: 'src/app.js', description: 'x' },   // reflector NEVER gets candidates (BR-9)
    { dimension: 'bogus', path: 'src/app.js', description: 'x' },       // unknown dim
    { dimension: '', path: 'src/app.js', description: 'x' },            // empty dim
  ];
  assert.deepEqual(validateCitations(cands, changed), []);
});

test('validateCitations: REJECTS non-string / empty / missing paths and non-object entries', () => {
  const changed = ['src/app.js'];
  const cands = [
    null,
    'not-an-object',
    { dimension: 'security', description: 'x' },               // no path
    { dimension: 'security', path: '', description: 'x' },     // empty path
    { dimension: 'security', path: 42, description: 'x' },     // non-string path
  ];
  assert.deepEqual(validateCitations(cands, changed), []);
});

test('validateCitations: SANITIZES the description (strips injection punctuation/control chars)', () => {
  const changed = ['src/app.js'];

  // Precise small case — each unsafe char (<, >, `, !) maps to exactly one space;
  // the safe chars (letters, digits, parens, space) pass through unchanged.
  const exact = validateCitations(
    [{ dimension: 'architecture', path: 'src/app.js', description: 'a<b>`c`!' }], changed,
  );
  assert.equal(exact[0].description, 'a b  c  ');

  // Adversarial case — a script/injection payload with newline, braces, backticks.
  const cands = [{
    dimension: 'architecture',
    path: 'src/app.js',
    description: 'see <script>alert(1)</script>\n{inject} `cmd` !!',
  }];
  const out = validateCitations(cands, changed);
  assert.equal(out.length, 1);
  // No char outside the safe set [A-Za-z0-9 .,:;()/_'"-] survives — and no control
  // char (newline/backtick/brace) leaks into a reviewer prompt. (LESSON-008)
  assert.ok(/^[A-Za-z0-9 .,:;()/_'"-]*$/.test(out[0].description));
  assert.ok(!/[<>{}`\n!]/.test(out[0].description), 'injection chars must be gone');
  // Safe alphanumeric content survives the sanitization.
  assert.ok(out[0].description.includes('script'));
  assert.ok(out[0].description.includes('alert(1)'));
});

test('validateCitations: drops a malformed lineRange but keeps the survivor', () => {
  const changed = ['src/app.js'];
  const good = validateCitations(
    [{ dimension: 'security', path: 'src/app.js', description: 'x', lineRange: '5' }], changed,
  );
  assert.equal(good[0].lineRange, '5');

  const bad = validateCitations(
    [{ dimension: 'security', path: 'src/app.js', description: 'x', lineRange: '5; rm' }], changed,
  );
  assert.equal(bad.length, 1);
  assert.ok(!('lineRange' in bad[0]), 'a malformed lineRange must be dropped, candidate kept');
});

test('validateCitations: tolerates null/empty inputs (never throws)', () => {
  assert.deepEqual(validateCitations(null, null), []);
  assert.deepEqual(validateCitations([], ['src/app.js']), []);
  assert.deepEqual(validateCitations([{ dimension: 'security', path: 'a.js', description: 'x' }], null), []);
});

test('sanitizeDescription: null/undefined become empty string', () => {
  assert.equal(sanitizeDescription(null), '');
  assert.equal(sanitizeDescription(undefined), '');
  assert.equal(sanitizeDescription('plain text 1.2'), 'plain text 1.2');
});

test('candidatesByDimension: buckets validated survivors by reviewer dimension', () => {
  const changed = ['a.js', 'b.js'];
  const validated = validateCitations([
    { dimension: 'security', path: 'a.js', description: 'one' },
    { dimension: 'security', path: 'b.js', description: 'two' },
    { dimension: 'quality', path: 'a.js', description: 'three' },
  ], changed);
  const byDim = candidatesByDimension(validated);
  assert.equal(byDim.security.length, 2);
  assert.equal(byDim.quality.length, 1);
  assert.ok(!('reflector' in byDim));
});

// ===========================================================================
// dedupeAndRank — the BR-7 consolidation gate. Dedupe within a repo, tag
// cross-repo, rank by severity, and the Critical/mustFix block predicate.
// ===========================================================================

// A FINDINGS-shaped panel object (one per panel member).
function fset(dimension, findings) {
  return { dimension, findings };
}
function finding(severity, file, title, extra = {}) {
  return { severity, file, title, mustFix: false, userFacing: false, ...extra };
}

test('dedupeAndRank: dedupes within a repo on (file, normalized-title), unioning dimensions', () => {
  const byRepo = {
    repoA: [
      fset('correctness', [finding('Major', 'a.js', 'Off-by-one  ERROR')]),
      fset('quality', [finding('Major', 'a.js', 'off-by-one error')]), // same key, different wording/case
    ],
  };
  const out = dedupeAndRank(byRepo);
  assert.equal(out.findings.length, 1, 'the two near-identical findings collapse to one');
  const f = out.findings[0];
  assert.deepEqual(f.dimensions.sort(), ['correctness', 'quality']);
  assert.equal(f.crossRepo, false);
});

test('dedupeAndRank: dedupe keeps the MOST SEVERE severity and OR-s mustFix/userFacing', () => {
  const byRepo = {
    repoA: [
      fset('correctness', [finding('Minor', 'a.js', 'Race', { mustFix: false })]),
      fset('security', [finding('Critical', 'a.js', 'race', { mustFix: true })]),
    ],
  };
  const out = dedupeAndRank(byRepo);
  assert.equal(out.findings.length, 1);
  assert.equal(out.findings[0].severity, 'Critical');
  assert.equal(out.findings[0].mustFix, true);
});

test('dedupeAndRank: tags a (file,title) seen in MORE THAN ONE repo as crossRepo', () => {
  const byRepo = {
    repoA: [fset('security', [finding('Major', 'shared.js', 'Leaks token')])],
    repoB: [fset('security', [finding('Major', 'shared.js', 'Leaks token')])],
  };
  const out = dedupeAndRank(byRepo);
  assert.equal(out.findings.length, 2, 'cross-repo findings are NOT merged (dedupe is within-repo)');
  assert.ok(out.findings.every((f) => f.crossRepo === true));
});

test('dedupeAndRank: orders by severity (Critical > Major > Minor > Nit), then repo, then file', () => {
  const byRepo = {
    repoB: [fset('quality', [finding('Nit', 'z.js', 'style')])],
    repoA: [
      fset('correctness', [finding('Critical', 'a.js', 'crash')]),
      fset('quality', [finding('Minor', 'b.js', 'naming')]),
      fset('architecture', [finding('Major', 'c.js', 'coupling')]),
    ],
  };
  const out = dedupeAndRank(byRepo);
  assert.deepEqual(out.findings.map((f) => f.severity), ['Critical', 'Major', 'Minor', 'Nit']);
});

test('dedupeAndRank: Critical OR mustFix ⇒ blocks (the merge gate)', () => {
  // A lone Critical blocks.
  const crit = dedupeAndRank({ r: [fset('correctness', [finding('Critical', 'a.js', 'x')])] });
  assert.equal(crit.blocks, true);
  assert.equal(crit.blocking.length, 1);

  // A non-Critical finding with mustFix:true ALSO blocks.
  const mustFix = dedupeAndRank({ r: [fset('quality', [finding('Minor', 'a.js', 'x', { mustFix: true })])] });
  assert.equal(mustFix.blocks, true);

  // Only Major/Minor/Nit and no mustFix ⇒ clean.
  const clean = dedupeAndRank({ r: [fset('quality', [finding('Major', 'a.js', 'x'), finding('Nit', 'b.js', 'y')])] });
  assert.equal(clean.blocks, false);
  assert.equal(clean.blocking.length, 0);
});

test('dedupeAndRank: empty / no-findings input is clean and non-blocking', () => {
  assert.deepEqual(dedupeAndRank({}), { findings: [], blocking: [], blocks: false });
  assert.deepEqual(dedupeAndRank({ r: [] }), { findings: [], blocking: [], blocks: false });
  assert.deepEqual(dedupeAndRank({ r: [fset('quality', [])] }), { findings: [], blocking: [], blocks: false });
});

test('dedupeAndRank: is deterministic — same input yields byte-identical output across runs', () => {
  const byRepo = {
    repoB: [fset('quality', [finding('Nit', 'z.js', 'style')])],
    repoA: [fset('correctness', [finding('Critical', 'a.js', 'crash')])],
  };
  const a = JSON.stringify(dedupeAndRank(byRepo));
  const b = JSON.stringify(dedupeAndRank(byRepo));
  assert.equal(a, b);
});

// ===========================================================================
// selectEligible — the BR-12 Preflight selection + max-5 truncation. Truncation
// must be visible (the dropped list is what the script logs).
// ===========================================================================

test('selectEligible: keeps only eligible REQs in the agent\'s ranked order', () => {
  const reqs = [
    { id: 'A', eligible: true },
    { id: 'B', eligible: false, reason: 'not approved' },
    { id: 'C', eligible: true },
  ];
  const { todo, dropped, ineligible } = selectEligible(reqs, 5);
  assert.deepEqual(todo.map((r) => r.id), ['A', 'C']);
  assert.deepEqual(dropped, []);
  assert.deepEqual(ineligible.map((r) => r.id), ['B']);
});

test('selectEligible: applies the max-5 bound AFTER eligibility and reports the dropped tail (BR-12)', () => {
  const reqs = ['A', 'B', 'C', 'D', 'E', 'F', 'G'].map((id) => ({ id, eligible: true }));
  const { todo, dropped, ineligible } = selectEligible(reqs, 5);
  assert.deepEqual(todo.map((r) => r.id), ['A', 'B', 'C', 'D', 'E'], 'runs the first 5 eligible');
  assert.deepEqual(dropped, ['F', 'G'], 'defers the rest — surfaced, never silently dropped');
  assert.deepEqual(ineligible, []);
});

test('selectEligible: ineligible REQs never count against the max-5 bound', () => {
  // 2 ineligible interleaved; 5 eligible must all run (none crowded out).
  const reqs = [
    { id: 'A', eligible: true },
    { id: 'X', eligible: false, reason: 'no tasks' },
    { id: 'B', eligible: true },
    { id: 'C', eligible: true },
    { id: 'Y', eligible: false, reason: 'already merged' },
    { id: 'D', eligible: true },
    { id: 'E', eligible: true },
  ];
  const { todo, dropped } = selectEligible(reqs, 5);
  assert.deepEqual(todo.map((r) => r.id), ['A', 'B', 'C', 'D', 'E']);
  assert.deepEqual(dropped, []);
});

test('selectEligible: empty input yields empty selection (never throws)', () => {
  assert.deepEqual(selectEligible([], 5), { todo: [], dropped: [], ineligible: [] });
  assert.deepEqual(selectEligible(null, 5), { todo: [], dropped: [], ineligible: [] });
});

// ===========================================================================
// orderByTier — stable ascending tier sort (Phase-4 serial order).
// ===========================================================================

test('orderByTier: sorts ascending by tier, stable within a tier, missing tier = 0', () => {
  const tasks = [
    { id: 'T3', tier: 2 },
    { id: 'T1', tier: 0 },
    { id: 'T2' },          // missing tier → treated as 0, AFTER T1 (stable)
    { id: 'T4', tier: 1 },
  ];
  assert.deepEqual(orderByTier(tasks).map((t) => t.id), ['T1', 'T2', 'T4', 'T3']);
});

test('orderByTier: a flat (untiered) plan keeps its array order', () => {
  const tasks = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  assert.deepEqual(orderByTier(tasks).map((t) => t.id), ['a', 'b', 'c']);
  assert.deepEqual(orderByTier(null), []);
});

// ===========================================================================
// groupCrossRepoReqs — ADR-12 cross-REQ merge grouping (union-find over "shares
// a touched repo"). REQs that share a sibling repo merge serially (same group);
// disjoint REQs stay parallel (separate groups).
// ===========================================================================

test('groupCrossRepoReqs: groups REQs that share a repo; keeps disjoint REQs apart', () => {
  const groups = groupCrossRepoReqs(['R1', 'R2', 'R3'], {
    R1: ['api'],
    R2: ['api'],     // shares 'api' with R1 → same group
    R3: ['web'],     // disjoint → its own group
  });
  // Determinism: input order within groups, groups ordered by first member.
  assert.deepEqual(groups, [['R1', 'R2'], ['R3']]);
});

test('groupCrossRepoReqs: transitively unions a chain (R1-R2 via a, R2-R3 via b)', () => {
  const groups = groupCrossRepoReqs(['R1', 'R2', 'R3'], {
    R1: ['a'],
    R2: ['a', 'b'],  // bridges R1 and R3
    R3: ['b'],
  });
  assert.deepEqual(groups, [['R1', 'R2', 'R3']]);
});

test('groupCrossRepoReqs: REQs touching disjoint repos are all separate groups', () => {
  const groups = groupCrossRepoReqs(['R1', 'R2'], { R1: ['x'], R2: ['y'] });
  assert.deepEqual(groups, [['R1'], ['R2']]);
});

// ===========================================================================
// blocked / failed — terminal-value constructors. The discriminant is `state`
// (the TERMINAL schema's name), NOT `terminal`; unsupplied keys are omitted so
// the value validates against the closed (additionalProperties:false) schema.
// ===========================================================================

test('blocked: emits state="blocked" with a normalized object detail payload', () => {
  const t = blocked('REQ-1', 'reflector-questions', { questions: ['Ship v1 without dark mode?'] });
  assert.deepEqual(t, {
    state: 'blocked',
    id: 'REQ-1',
    reason: 'reflector-questions',
    detail: { questions: ['Ship v1 without dark mode?'] },
  });
});

test('blocked: a string detail is wrapped as {detail} (closed-schema safe)', () => {
  const t = blocked('REQ-2', 'merge-conflict', 'PR could not merge cleanly');
  assert.deepEqual(t, {
    state: 'blocked',
    id: 'REQ-2',
    reason: 'merge-conflict',
    detail: { detail: 'PR could not merge cleanly' },
  });
});

test('blocked: omits an undefined detail key (no detail:undefined past additionalProperties:false)', () => {
  const t = blocked('REQ-3', 'spec-validation');
  assert.deepEqual(t, { state: 'blocked', id: 'REQ-3', reason: 'spec-validation' });
  assert.ok(!('detail' in t));
});

test('failed: emits state="failed" — distinct from blocked, same payload normalization', () => {
  const t = failed('REQ-4', 'phase0-no-worktree', 'Phase 0 returned no repo records.');
  assert.deepEqual(t, {
    state: 'failed',
    id: 'REQ-4',
    reason: 'phase0-no-worktree',
    detail: { detail: 'Phase 0 returned no repo records.' },
  });
});
