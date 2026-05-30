// workflows/tests/helpers.test.js — deterministic unit tests for the PURE
// `adlc-sprint` workflow helpers, which are INLINED into the self-contained
// `workflows/adlc-sprint.workflow.js` behind the `// ==== BEGIN/END PURE ====`
// sentinels and loaded here via the shared `vm` loader (./_load-pure.js). The
// Workflow runtime has no `require`/`import`/`fs`, so the engine is one file and
// the pure section is the only thing under test. (REQ-474, TASK-063, ADR-10)
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
//     node --test 'workflows/tests/*.test.js'
//
// See workflows/tests/README.md.

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

// The pure helpers are INLINED into the self-contained workflow script (the
// Workflow runtime has no `require`/`import`/`fs`). The shared `vm` loader
// evaluates only the `// ==== BEGIN/END PURE ====` section — schemas + helpers —
// with the runtime globals absent and returns its `module.exports`, so node:test
// covers the logic with no build step. Resolved relative to this file so the
// suite runs identically from any cwd (toolkit root, a worktree, or CI). (REQ-474)
const helpers = require('./_load-pure.js')(require('node:path').join(__dirname, '..', 'adlc-sprint.workflow.js'));
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
  // Previously-untested halt/merge-driving helpers (REQ-474 Phase-5 verify fixes).
  reflectorQuestions,
  fixedPairs,
  mergeReverified,
  allMerged,
  stripVerifyMarkers,
  sharesRepo,
  terminalValue,
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
      fset('correctness', [finding('Minor', 'a.js', 'Race', { mustFix: false, userFacing: false })]),
      // The second copy carries mustFix AND userFacing — both must survive the OR-merge.
      fset('security', [finding('Critical', 'a.js', 'race', { mustFix: true, userFacing: true })]),
    ],
  };
  const out = dedupeAndRank(byRepo);
  assert.equal(out.findings.length, 1);
  assert.equal(out.findings[0].severity, 'Critical');
  assert.equal(out.findings[0].mustFix, true);
  // Previously vacuous: the test claimed to exercise the userFacing OR-merge but
  // never asserted it. Pin the OR result so a regression in the merge is caught.
  assert.equal(out.findings[0].userFacing, true);
});

test('dedupeAndRank: coerces a truthy non-boolean mustFix (e.g. 1) to block (defensive)', () => {
  // The FINDINGS schema types mustFix as boolean, but the consolidation gate is the
  // merge-safety backstop: a non-schema-conformant `mustFix:1` must STILL block, and
  // the survivor's mustFix must be a REAL boolean (not the raw 1). (REQ-474 defensive)
  const out = dedupeAndRank({ r: [fset('quality', [finding('Minor', 'a.js', 'x', { mustFix: 1 })])] });
  assert.equal(out.blocks, true, 'a truthy mustFix:1 still blocks the merge gate');
  assert.equal(out.blocking.length, 1);
  assert.equal(out.findings[0].mustFix, true, 'the survivor mustFix is coerced to a real boolean');

  // And on a DEDUPE merge: the truthy 1 arrives on the second copy and must win.
  const merged = dedupeAndRank({
    r: [
      fset('correctness', [finding('Minor', 'a.js', 'dup', { mustFix: false })]),
      fset('security', [finding('Minor', 'a.js', 'DUP', { mustFix: 1 })]),
    ],
  });
  assert.equal(merged.findings.length, 1);
  assert.equal(merged.findings[0].mustFix, true);
  assert.equal(merged.blocks, true);
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

// terminalValue — the shared TERMINAL builder. Cover the falsy-`detail` edge: a
// null/empty reason or detail must be OMITTED (not smuggled in as null past the
// closed additionalProperties:false schema).
test('terminalValue: omits null/undefined reason and detail (closed-schema safe)', () => {
  assert.deepEqual(terminalValue('blocked', 'REQ-9'), { state: 'blocked', id: 'REQ-9' });
  assert.deepEqual(terminalValue('blocked', 'REQ-9', null, null), { state: 'blocked', id: 'REQ-9' });
  // An empty-string detail is NOT null, so it is wrapped as {detail:''} — present
  // but falsy. This pins the boundary: only null/undefined are dropped.
  assert.deepEqual(terminalValue('failed', 'REQ-9', 'r', ''), {
    state: 'failed', id: 'REQ-9', reason: 'r', detail: { detail: '' },
  });
});

// ===========================================================================
// reflectorQuestions — the Phase-5 halt driver. Collects userFacing reflector
// question titles across repos; a non-empty result is the halt. Only the
// reflector dimension and only `userFacing:true` findings count.
// ===========================================================================

test('reflectorQuestions: collects only userFacing reflector findings across repos', () => {
  const byRepo = {
    repoA: [
      fset('reflector', [
        finding('Major', 'x.js', 'Ship v1 without dark mode?', { userFacing: true }),
        finding('Major', 'x.js', 'internal note', { userFacing: false }), // not userFacing → ignored
      ]),
      fset('security', [finding('Critical', 'x.js', 'SQLi', { userFacing: true })]), // not reflector → ignored
    ],
    repoB: [
      fset('reflector', [finding('Minor', 'y.js', 'Drop legacy API?', { userFacing: true })]),
    ],
  };
  assert.deepEqual(reflectorQuestions(byRepo), ['Ship v1 without dark mode?', 'Drop legacy API?']);
});

test('reflectorQuestions: empty when no reflector question is userFacing', () => {
  const byRepo = {
    r: [
      fset('reflector', [finding('Major', 'x.js', 'q', { userFacing: false })]),
      fset('correctness', [finding('Critical', 'x.js', 'bug', { mustFix: true })]),
    ],
  };
  assert.deepEqual(reflectorQuestions(byRepo), []);
  assert.deepEqual(reflectorQuestions({}), []);
});

test('reflectorQuestions: falls back to detail then a placeholder when title is absent', () => {
  const byRepo = {
    r: [fset('reflector', [
      { severity: 'Major', file: 'x.js', detail: 'fallback detail', mustFix: false, userFacing: true },
      { severity: 'Major', file: 'x.js', mustFix: false, userFacing: true },
    ])],
  };
  assert.deepEqual(reflectorQuestions(byRepo), ['fallback detail', '(unspecified question)']);
});

// ===========================================================================
// The Critical resume-answer-propagation DECISION (REQ-474 verify fix). The
// engine dispatches a guidance-carrying fix agent when `consolidated.blocks ||
// (Boolean(ans) && hadReflectorQ)`. This pins the PURE inputs to that decision so
// a resumed reflector-only question (blocks=false, ans set) DOES dispatch — i.e.
// the human's reply is never silently discarded. (mirrors verify()'s gate)
// ===========================================================================

test('resume dispatch decision: a resumed reflector-only question (blocks=false) DOES dispatch a guidance agent', () => {
  // A lone reflector userFacing question with mustFix:false ⇒ the consolidation
  // does NOT block (the bug: the blocks-gated fix would never run, dropping `ans`).
  const findingsByRepo = {
    r: [fset('reflector', [finding('Major', 'x.js', 'Ship without dark mode?', { userFacing: true, mustFix: false })])],
  };
  const hadReflectorQ = reflectorQuestions(findingsByRepo).length > 0;
  const consolidated = dedupeAndRank(findingsByRepo);
  assert.equal(hadReflectorQ, true);
  assert.equal(consolidated.blocks, false, 'a mustFix:false reflector question does NOT block consolidation');

  // On resume (`ans` set) the dispatch decision MUST be true even though nothing
  // blocks — otherwise the user's answer is lost.
  const ans = 'Yes, ship v1 without dark mode.';
  const applyResumeAnswer = Boolean(ans) && hadReflectorQ;
  const willDispatch = consolidated.blocks || applyResumeAnswer;
  assert.equal(willDispatch, true, 'resumed reflector-only answer dispatches a guidance-carrying fix agent');

  // First run (no answer): no dispatch here — the engine HALTS earlier instead.
  const firstRunDispatch = consolidated.blocks || (Boolean(undefined) && hadReflectorQ);
  assert.equal(firstRunDispatch, false, 'first run does not fix past the open question — it halts');
});

// ===========================================================================
// fixedPairs — the ≤1 re-verify targeting. From the blocking findings, the set of
// REVIEWER dimensions to re-check per repo; the reflector is excluded.
// ===========================================================================

test('fixedPairs: groups reviewer dimensions per repo, excluding the reflector', () => {
  const blocking = [
    { repo: 'api', dimensions: ['correctness', 'security'] },
    { repo: 'api', dimension: 'quality' },                 // single-dimension fallback
    { repo: 'web', dimensions: ['reflector', 'architecture'] }, // reflector dropped
  ];
  const out = fixedPairs(blocking);
  assert.deepEqual(out.api.sort(), ['correctness', 'quality', 'security']);
  assert.deepEqual(out.web, ['architecture']);
  assert.ok(!out.web.includes('reflector'));
});

test('fixedPairs: dedupes a dimension repeated across findings; empty/blank inputs yield {}', () => {
  const out = fixedPairs([
    { repo: 'api', dimension: 'security' },
    { repo: 'api', dimensions: ['security', 'correctness'] },
  ]);
  assert.deepEqual(out.api.sort(), ['correctness', 'security']);
  assert.deepEqual(fixedPairs([]), {});
  assert.deepEqual(fixedPairs(null), {});
  // A blocking finding that ONLY raised the reflector dimension contributes nothing.
  assert.deepEqual(fixedPairs([{ repo: 'api', dimension: 'reflector' }]), {});
});

// ===========================================================================
// mergeReverified — overlay the re-verified reviewer findings over the original
// panel result. For a re-checked (repo,dimension) the fresh set REPLACES the
// stale one; the reflector and untouched dimensions are preserved verbatim.
// ===========================================================================

test('mergeReverified: replaces a re-checked dimension, preserves reflector + untouched dims', () => {
  const original = {
    api: [
      fset('reflector', [finding('Major', 'a.js', 'question', { userFacing: true })]),
      fset('security', [finding('Critical', 'a.js', 'old SQLi')]),
      fset('quality', [finding('Minor', 'a.js', 'naming')]),
    ],
  };
  const reverified = {
    api: [fset('security', [finding('Major', 'a.js', 'fixed, now only Major')])],
  };
  const merged = mergeReverified(original, reverified);
  const dims = merged.api.map((f) => f.dimension).sort();
  assert.deepEqual(dims, ['quality', 'reflector', 'security'], 'one set per dimension — security replaced, not duplicated');
  const sec = merged.api.find((f) => f.dimension === 'security');
  assert.equal(sec.findings[0].title, 'fixed, now only Major', 'the fresh security set replaced the stale one');
  // The reflector set is preserved verbatim.
  const refl = merged.api.find((f) => f.dimension === 'reflector');
  assert.equal(refl.findings[0].userFacing, true);
});

test('mergeReverified: a repo only present in reverified is appended', () => {
  const merged = mergeReverified(
    { api: [fset('security', [finding('Major', 'a.js', 'x')])] },
    { web: [fset('quality', [finding('Minor', 'b.js', 'y')])] },
  );
  assert.ok('api' in merged && 'web' in merged);
  assert.equal(merged.web[0].dimension, 'quality');
});

// ===========================================================================
// allMerged / stripVerifyMarkers — the BR-6 "claim ≠ truth" merge-state proof.
// ===========================================================================

test('allMerged: true only when EVERY verified PR row reports gh state MERGED', () => {
  assert.equal(allMerged([{ _state: 'MERGED' }, { _state: 'MERGED' }]), true);
  assert.equal(allMerged([{ _state: 'MERGED' }, { _state: 'OPEN' }]), false);
  assert.equal(allMerged([{ _state: 'CLOSED' }]), false);
  // Empty input is NOT merged — nothing was confirmed (BR-6).
  assert.equal(allMerged([]), false);
  assert.equal(allMerged(null), false);
});

test('stripVerifyMarkers: projects rows to the closed {repo,url[,number]} PRS shape', () => {
  const rows = [
    { repo: 'api', url: 'https://x/1', number: 7, _state: 'MERGED' },
    { repo: 'web', url: 'https://x/2', _state: 'OPEN' }, // no number → number omitted
  ];
  const out = stripVerifyMarkers(rows);
  assert.deepEqual(out, [
    { repo: 'api', url: 'https://x/1', number: 7 },
    { repo: 'web', url: 'https://x/2' },
  ]);
  // The internal _state marker never survives into the TERMINAL value.
  assert.ok(out.every((r) => !('_state' in r)));
  assert.deepEqual(stripVerifyMarkers(null), []);
});

// ===========================================================================
// sharesRepo — the groupCrossRepoReqs primitive: true iff two repo lists intersect.
// ===========================================================================

test('sharesRepo: true iff the two touched-repo lists intersect', () => {
  assert.equal(sharesRepo(['api', 'web'], ['ios', 'api']), true);
  assert.equal(sharesRepo(['api'], ['web']), false);
  assert.equal(sharesRepo([], ['api']), false);
  assert.equal(sharesRepo(['api'], []), false);
});
