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
  liteFallbackNotice,
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
  TERMINAL,
  // BUG-249 Step-8b close-out helpers.
  closeOutEvidenceStatus,
  closeOutDigest,
  repoRootFromWorktree,
  groupMergedByRepo,
  // REQ-669 ADR-6 agent namespace.
  panelMembers,
  AGENT_NAMESPACES,
  normalizeAgentNamespace,
  agentTypeFor,
  // REQ-647 lessons in the engine.
  LESSONS,
  TASK_LESSONS,
  escalateByLessons,
  lessonsBlock,
  lessonsLogLine,
  taskSetsById,
  lessonIdsOf,
} = helpers;

// ===========================================================================
// BUG-249 — Step-8b close-out pass helpers + the TERMINAL `closeOut` contract.
// ===========================================================================

test('closeOutEvidenceStatus: "none" with no findings and no reports, "present" with either', () => {
  assert.equal(closeOutEvidenceStatus(undefined), 'none');
  assert.equal(closeOutEvidenceStatus({ repos: [], tasks: [], findings: null, reports: [] }), 'none');
  assert.equal(closeOutEvidenceStatus({ findings: [{ severity: 'Minor', file: 'a', title: 't' }], reports: [] }), 'present');
  assert.equal(closeOutEvidenceStatus({ findings: [], reports: [{ taskId: 'TASK-1', text: 'done' }] }), 'present');
});

test('closeOutDigest: bounded (30 findings, 1500 chars per report), deterministic, and says "(none)" for empty sections', () => {
  const ev = {
    tasks: [{ id: 'TASK-1', title: 'Do a thing' }, { id: 'TASK-2' }],
    findings: Array.from({ length: 35 }, (_, i) => ({
      severity: i === 0 ? 'Major' : 'Minor', file: `f${i}.js`, line: i, title: `finding ${i}`, lessonId: i === 0 ? 'LESSON-404' : undefined, mustFix: i === 0,
    })),
    reports: [{ taskId: 'TASK-1', text: 'x'.repeat(2000) }],
  };
  const d1 = closeOutDigest(ev);
  const d2 = closeOutDigest(ev);
  assert.equal(d1, d2, 'digest must be deterministic for byte-identical replay prompts');
  assert.ok(d1.includes('Tasks (2): TASK-1 — Do a thing; TASK-2'));
  assert.ok(d1.includes('Phase-5 consolidated findings (35, first 30 shown):'));
  assert.ok(d1.includes('  - [Major] f0.js:0 — finding 0 (lesson LESSON-404) [must-fix]'));
  assert.ok(d1.includes('finding 29'));
  assert.ok(!d1.includes('finding 30'), 'the 31st finding must be cut');
  assert.ok(d1.includes('[…truncated]'));
  assert.ok(!d1.includes('x'.repeat(1501)), 'a report must be cut at 1500 chars');
  const empty = closeOutDigest({ tasks: [], findings: [], reports: [] });
  assert.ok(empty.includes('Tasks (0): none'));
  assert.ok(empty.includes('Phase-5 consolidated findings (0):\n  (none)'));
  assert.ok(empty.includes('Implementer reports (0):\n  (none)'));
});

test('repoRootFromWorktree: recovers <repoRoot> from the engine\'s `<root>/.worktrees/<id>` convention, null otherwise', () => {
  assert.equal(repoRootFromWorktree('/abs/repo/.worktrees/REQ-7', 'REQ-7'), '/abs/repo');
  assert.equal(repoRootFromWorktree('/abs/repo/.worktrees/REQ-7', 'REQ-8'), null);
  assert.equal(repoRootFromWorktree('/abs/repo', 'REQ-7'), null);
  assert.equal(repoRootFromWorktree('/.worktrees/REQ-7', 'REQ-7'), null, 'an empty root is not a root');
  assert.equal(repoRootFromWorktree(undefined, 'REQ-7'), null);
});

test('groupMergedByRepo: only merged terminals, grouped by primary repo, serial within a group, deterministic order', () => {
  const terminals = [
    { state: 'merged', id: 'REQ-3' },
    { state: 'pr-ready', id: 'REQ-2' },
    { state: 'merged', id: 'REQ-1' },
    { state: 'blocked', id: 'REQ-4' },
    null,
    { state: 'merged', id: 'REQ-5' },
  ];
  const groups = groupMergedByRepo(terminals, { 'REQ-1': 'web', 'REQ-3': 'web', 'REQ-5': 'api' });
  assert.deepEqual(groups, [['REQ-5'], ['REQ-1', 'REQ-3']]);
  assert.deepEqual(groupMergedByRepo([{ state: 'blocked', id: 'REQ-9' }], {}), []);
  assert.deepEqual(groupMergedByRepo([{ state: 'merged', id: 'REQ-9' }], {}), [['REQ-9']], 'an unknown repo still closes out, in its own group');
});

// The TERMINAL closed schema must admit a merged-with-closeOut value: the
// close-out pass stamps `closeOut` + `closeOutDetail` beside state:'merged'
// (never instead of it), so every key of that value has to be declared or the
// runtime rejects the terminal (additionalProperties:false — the LESSON-331
// closed-schema-rot class).
test('TERMINAL: declares closeOut (ok|failed|skipped) and closeOutDetail beside state:"merged"', () => {
  const t = { state: 'merged', id: 'REQ-1', prs: [{ repo: 'web', url: 'https://x/pull/1' }], closeOut: 'failed', closeOutDetail: 'chore PR blocked by policy' };
  const declared = Object.keys(TERMINAL.properties);
  for (const k of Object.keys(t)) {
    assert.ok(declared.includes(k), `TERMINAL must declare "${k}" (additionalProperties:false)`);
  }
  assert.deepEqual(TERMINAL.properties.closeOut.enum, ['ok', 'failed', 'skipped']);
  assert.deepEqual(TERMINAL.properties.state.enum, ['merged', 'pr-ready', 'blocked', 'failed'], 'closeOut is never encoded in state');
});

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
// liteFallbackNotice — REQ-652 BR-16 / AC-13: the workflow engine runs a lite
// REQ on the full lane and logs one line per lite REQ; nothing for full or
// lane-less REQs (absent means full).
// ===========================================================================

test('liteFallbackNotice: one line per lite REQ, naming it, in input order (BR-16)', () => {
  const lines = liteFallbackNotice([
    { id: 'REQ-101', eligible: true, lane: 'lite' },
    { id: 'REQ-102', eligible: true, lane: 'full' },
    { id: 'REQ-103', eligible: true },
    { id: 'REQ-104', eligible: true, lane: 'lite' },
  ]);
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^Lite lane: REQ-101 runs on the full lane/);
  assert.match(lines[1], /^Lite lane: REQ-104 runs on the full lane/);
});

test('liteFallbackNotice: no notice when every REQ is full or has no lane (AC-13)', () => {
  assert.deepEqual(liteFallbackNotice([
    { id: 'REQ-201', eligible: true, lane: 'full' },
    { id: 'REQ-202', eligible: true },
  ]), []);
  assert.deepEqual(liteFallbackNotice([]), []);
  assert.deepEqual(liteFallbackNotice(null), []);
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

// REQ-485 self-healing rebase-halt payload. The post-merge unblock pass returns a
// blocked() halt whose detail carries BlockHold fields (conflictFiles, holdState,
// rebaseAttempts, resolvedBlocker). Those keys MUST be declared in the closed
// (additionalProperties:false) TERMINAL.detail schema, or the halt would be
// rejected by any consumer that validates a returned terminal against TERMINAL.
// This pins the schema↔payload contract WITHOUT ajv (the harness has none): every
// key the rebase-halt payload uses must be a declared TERMINAL.detail property.
test('blocked: REQ-485 rebase-halt payload validates against the closed TERMINAL.detail schema', () => {
  const t = blocked('REQ-485', 'needs-manual-rebase', {
    reason: 'auto-rebase conflicted; manual rebase needed',
    conflictFiles: ['sprint/SKILL.md'],
    holdState: 'needs-manual-rebase',
    rebaseAttempts: 1,
    resolvedBlocker: 'REQ-483',
  });
  assert.deepEqual(t, {
    state: 'blocked',
    id: 'REQ-485',
    reason: 'needs-manual-rebase',
    detail: {
      reason: 'auto-rebase conflicted; manual rebase needed',
      conflictFiles: ['sprint/SKILL.md'],
      holdState: 'needs-manual-rebase',
      rebaseAttempts: 1,
      resolvedBlocker: 'REQ-483',
    },
  });
  // additionalProperties:false → every detail key must be a declared property.
  const declared = Object.keys(TERMINAL.properties.detail.properties);
  for (const k of Object.keys(t.detail)) {
    assert.ok(declared.includes(k), `TERMINAL.detail must declare "${k}" (additionalProperties:false)`);
  }
  // holdState is a closed enum — the rebase-halt value must be a member.
  assert.ok(TERMINAL.properties.detail.properties.holdState.enum.includes('needs-manual-rebase'));
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

// ===========================================================================
// REQ-669 ADR-6 — agentTypeFor / normalizeAgentNamespace: the agent namespace
// /sprint passes as args.agentNamespace. Bare on the symlink install, `adlc:` on
// the plugin install. A wrong agentType does not fail loudly (an unresolved name
// can silently run a generic agent, REQ-669 verification.md N4), so these pin the
// value and the source check below pins that it reaches every dispatch.
// ===========================================================================

test('agentTypeFor: bare name on the symlink route, adlc:-prefixed on the plugin route', () => {
  assert.equal(agentTypeFor('reflector', ''), 'reflector');
  assert.equal(agentTypeFor('reflector', 'adlc:'), 'adlc:reflector');
  assert.equal(agentTypeFor('task-implementer', 'adlc:'), 'adlc:task-implementer');
  // Absent is the documented default ("").
  assert.equal(agentTypeFor('reflector', undefined), 'reflector');
  assert.equal(agentTypeFor('reflector', null), 'reflector');
});

test('agentTypeFor: an invalid namespace yields the bare name, never a spliced value (LESSON-008)', () => {
  const invalid = [
    '../', 'adlc', 'ADLC:', 'adlc::', ':', 'a b:', 'adlc:x', 'adlc:\n', '\nadlc:',
    'adlc:../', 'adlc/:', 'ädlc:', ' adlc:', 'adlc: ',
    // Well-shaped, but not a value /sprint sends: the allowlist is closed.
    'other:', 'my-fork2:', 'adlc-dev:', 'a:',
    42, true, {}, ['adlc:'], () => 'adlc:',
  ];
  for (const ns of invalid) {
    assert.equal(agentTypeFor('reflector', ns), 'reflector', `namespace ${String(ns)} must be refused`);
  }
});

test('normalizeAgentNamespace: "" and absent are the quiet default; a bad value is flagged rejected', () => {
  assert.deepEqual(normalizeAgentNamespace(undefined), { ns: '', rejected: false });
  assert.deepEqual(normalizeAgentNamespace(null), { ns: '', rejected: false });
  assert.deepEqual(normalizeAgentNamespace(''), { ns: '', rejected: false });
  assert.deepEqual(normalizeAgentNamespace('adlc:'), { ns: 'adlc:', rejected: false });
  assert.deepEqual(normalizeAgentNamespace('../'), { ns: '', rejected: true });
  assert.deepEqual(normalizeAgentNamespace('adlc'), { ns: '', rejected: true });
  assert.deepEqual(normalizeAgentNamespace(0), { ns: '', rejected: true });
  // Another plugin's well-shaped prefix is rejected and logged, not honoured.
  assert.deepEqual(normalizeAgentNamespace('other:'), { ns: '', rejected: true });
  assert.deepEqual(normalizeAgentNamespace(new String('adlc:')), { ns: '', rejected: true });
});

test('AGENT_NAMESPACES: the closed allowlist is exactly "" and "adlc:", and frozen', () => {
  assert.deepEqual([...AGENT_NAMESPACES], ['', 'adlc:']);
  assert.equal(Object.isFrozen(AGENT_NAMESPACES), true);
});

test('panelMembers: bare agent names, so the dispatch site alone applies the namespace', () => {
  const members = panelMembers();
  assert.deepEqual(members.map((m) => m.agent), [
    'reflector', 'correctness-reviewer', 'quality-reviewer',
    'architecture-reviewer', 'test-auditor', 'security-auditor',
  ]);
  for (const m of members) {
    assert.equal(Object.prototype.hasOwnProperty.call(m, 'agentType'), false);
    assert.equal(agentTypeFor(m.agent, 'adlc:'), `adlc:${m.agent}`);
  }
});

test('agentTypeFor: every agentType in the engine goes through agentTypeFor(…, AGENT_NS)', () => {
  // The Workflow runtime cannot be run here, so this reads the engine source.
  // Comment lines are dropped first; what remains must name agentType only as
  // `agentType: agentTypeFor(<name>, AGENT_NS)`. The count floor keeps the check
  // from passing vacuously if the dispatch sites move (LESSON-019).
  const src = require('node:fs').readFileSync(
    require('node:path').join(__dirname, '..', 'adlc-sprint.workflow.js'), 'utf8');
  const code = src.split('\n').filter((line) => !/^\s*\/\//.test(line));
  const sites = code.filter((line) => /\bagentType\s*:/.test(line));
  assert.ok(sites.length >= 7, `expected at least 7 agentType sites, found ${sites.length}`);
  for (const line of sites) {
    assert.match(line, /\bagentType: agentTypeFor\([^,()]+, AGENT_NS\),?\s*$/, line.trim());
  }
  assert.equal(code.filter((line) => /agentType:\s*'/.test(line)).length, 0);
  // args.agentNamespace is read at exactly one site (ADR-6: read once, validated).
  const reads = code.filter((line) => /\bargs\.agentNamespace\b/.test(line));
  assert.equal(reads.length, 1, reads.join('\n'));
  assert.match(reads[0], /^const AGENT_NAMESPACE_ARG = args\.agentNamespace;$/);
});

// ===========================================================================
// REQ-647 — LESSONS schemas, set-gated escalation, lessonId union, prompt block.
// ===========================================================================

// A test-local JSON-Schema checker for the subset the engine's literals use (type,
// required, properties, additionalProperties:false, items, maxItems, enum). The
// harness has no ajv; this validates against the EXPORTED literal itself, so a
// schema edit that drops a field or loosens a bound fails here (LESSON-331).
function schemaErrors(schema, value, at = '$') {
  const errs = [];
  const t = schema.type;
  const isObj = value !== null && typeof value === 'object' && !Array.isArray(value);
  if (t === 'object' && !isObj) return [`${at}: not an object`];
  if (t === 'array' && !Array.isArray(value)) return [`${at}: not an array`];
  if (t === 'string' && typeof value !== 'string') return [`${at}: not a string`];
  if (t === 'integer' && !Number.isInteger(value)) return [`${at}: not an integer`];
  if (t === 'boolean' && typeof value !== 'boolean') return [`${at}: not a boolean`];
  if (schema.enum && !schema.enum.includes(value)) errs.push(`${at}: ${JSON.stringify(value)} not in enum`);
  if (t === 'object') {
    for (const k of schema.required || []) if (!(k in value)) errs.push(`${at}.${k}: required`);
    for (const k of Object.keys(value)) {
      if (schema.properties && k in schema.properties) errs.push(...schemaErrors(schema.properties[k], value[k], `${at}.${k}`));
      else if (schema.additionalProperties === false) errs.push(`${at}.${k}: unknown key`);
    }
  }
  if (t === 'array') {
    if (typeof schema.maxItems === 'number' && value.length > schema.maxItems) errs.push(`${at}: ${value.length} > maxItems ${schema.maxItems}`);
    value.forEach((v, i) => { if (schema.items) errs.push(...schemaErrors(schema.items, v, `${at}[${i}]`)); });
  }
  return errs;
}

function lessonEntry(n, extra = {}) {
  return { id: `LESSON-${String(100 + n)}`, title: `t${n}`, path: `.adlc/knowledge/lessons/LESSON-${100 + n}-x.md`, ...extra };
}
function lessonSet(entries, extra = {}) {
  return { query: { components: ['adlc/partials'] }, lessons: entries, retrievedAt: '2026-10-29T00:00:00Z', ...extra };
}

test('LESSONS: 15 unscored and 10 scored validate; 16 entries and an unknown key are rejected (AC-8)', () => {
  const unscored = lessonSet(Array.from({ length: 15 }, (_, i) => lessonEntry(i)));
  assert.deepEqual(schemaErrors(LESSONS, unscored), []);
  const scored = lessonSet(Array.from({ length: 10 }, (_, i) => lessonEntry(i, {
    score: 10 - i, component: 'adlc/partials', kind: 'process', confidence: 'high', newerThanSpec: true,
    supersededBy: ['LESSON-999'], text: '---\nid: x\n---',
  })), { cap: 10 });
  assert.deepEqual(schemaErrors(LESSONS, scored), []);
  const sixteen = lessonSet(Array.from({ length: 16 }, (_, i) => lessonEntry(i)));
  assert.ok(schemaErrors(LESSONS, sixteen).some((e) => /maxItems 15/.test(e)));
  assert.ok(schemaErrors(LESSONS, lessonSet([lessonEntry(0)], { surprise: 1 })).some((e) => /surprise: unknown key/.test(e)));
  assert.ok(schemaErrors(LESSONS, lessonSet([lessonEntry(0, { body: 'x' })])).some((e) => /body: unknown key/.test(e)));
  assert.ok(schemaErrors(LESSONS, lessonSet([lessonEntry(0, { kind: 'other' })])).some((e) => /not in enum/.test(e)));
  // the unavailable shape the leaf returns when adlc_lessons exits 2 is a valid value
  assert.deepEqual(schemaErrors(LESSONS, { query: { components: [] }, lessons: [], retrievedAt: '', unavailable: 'engine missing' }), []);
});

test('TASK_LESSONS: one {taskId, set} row per task, each a LESSONS value; unknown keys rejected', () => {
  const ok = { sets: [{ taskId: 'TASK-001', set: lessonSet([lessonEntry(0, { score: 3 })]) }] };
  assert.deepEqual(schemaErrors(TASK_LESSONS, ok), []);
  assert.ok(schemaErrors(TASK_LESSONS, { sets: [{ taskId: 'TASK-001', set: lessonSet([]), extra: 1 }] }).length > 0);
  assert.equal(TASK_LESSONS.properties.sets.items.properties.set, LESSONS, 'each row is validated against LESSONS itself');
});

test('escalateByLessons: an id outside the set is dropped and not escalated; one inside escalates one level (AC-9)', () => {
  const set = lessonSet([lessonEntry(1, { score: 5 })]);
  const byRepo = { r: [fset('correctness', [
    finding('Minor', 'a.js', 'inside', { lessonId: 'LESSON-101' }),
    finding('Minor', 'b.js', 'outside', { lessonId: 'LESSON-999' }),
    finding('Critical', 'c.js', 'already critical', { lessonId: 'LESSON-101' }),
    finding('Nit', 'd.js', 'no lesson'),
  ])] };
  const snapshot = JSON.stringify(byRepo);
  const out = escalateByLessons(byRepo, set).r[0].findings;
  assert.equal(out[0].severity, 'Major');
  assert.equal(out[0].escalatedFrom, 'Minor');
  assert.equal(out[1].severity, 'Minor', 'an untrusted id outside the set never escalates');
  assert.equal('lessonId' in out[1], false, 'and is removed from the finding (LESSON-008)');
  assert.equal(out[2].severity, 'Critical');
  assert.equal('escalatedFrom' in out[2], false);
  assert.deepEqual(out[3], finding('Nit', 'd.js', 'no lesson'));
  assert.equal(JSON.stringify(byRepo), snapshot, 'the input is not mutated');
  // no set at all: every lessonId is untrusted
  assert.equal(escalateByLessons(byRepo, null).r[0].findings[0].severity, 'Minor');
});

test('escalateByLessons: confidence low and superseded lessons keep the severity and say why (REQ-646 BR-6)', () => {
  const set = lessonSet([lessonEntry(1, { confidence: 'low' }), lessonEntry(2, { supersededBy: ['LESSON-300'] }), lessonEntry(3, { confidence: 'medium' })]);
  const out = escalateByLessons({ r: [fset('quality', [
    finding('Minor', 'a.js', 'low', { lessonId: 'LESSON-101' }),
    finding('Minor', 'b.js', 'superseded', { lessonId: 'LESSON-102' }),
    finding('Minor', 'c.js', 'medium', { lessonId: 'LESSON-103' }),
  ])] }, set).r[0].findings;
  assert.equal(out[0].severity, 'Minor');
  assert.equal(out[0].lessonNote, 'matched LESSON-101, confidence low — not escalated');
  assert.equal(out[1].severity, 'Minor');
  assert.equal(out[1].lessonNote, 'matched LESSON-102, superseded by LESSON-300 — not escalated');
  assert.equal(out[2].severity, 'Major', 'medium confidence escalates as before');
});

test('dedupeAndRank: unions lessonId — duplicates where only the second carries it keep the id and the escalation (AC-9)', () => {
  const set = lessonSet([lessonEntry(1), lessonEntry(2)]);
  const byRepo = { r: [
    fset('correctness', [finding('Minor', 'a.js', 'Race')]),
    fset('security', [finding('Minor', 'a.js', 'race', { lessonId: 'LESSON-101' })]),
    fset('quality', [finding('Minor', 'a.js', 'RACE', { lessonId: 'LESSON-102' })]),
  ] };
  const out = dedupeAndRank(escalateByLessons(byRepo, set));
  assert.equal(out.findings.length, 1);
  const f = out.findings[0];
  assert.equal(f.lessonId, 'LESSON-101');
  assert.deepEqual(f.lessonIds, ['LESSON-101', 'LESSON-102']);
  assert.equal(f.severity, 'Major', 'the escalated copy\'s severity wins');
  assert.equal(f.escalatedFrom, 'Minor');
  assert.deepEqual(lessonIdsOf(f), ['LESSON-101', 'LESSON-102']);
  // a finding with no lesson gains no lessonIds key (pre-REQ-647 output unchanged)
  assert.equal('lessonIds' in dedupeAndRank({ r: [fset('quality', [finding('Nit', 'b.js', 'x')])] }).findings[0], false);
  assert.ok(closeOutDigest({ tasks: [], findings: out.findings, reports: [] }).includes('(lesson LESSON-101, LESSON-102)'));
});

test('lessonsBlock: empty for no set, an unavailable set or no lessons; caps text at 40 lines; deterministic', () => {
  assert.equal(lessonsBlock(null, 'H'), '');
  assert.equal(lessonsBlock(lessonSet([]), 'H'), '');
  assert.equal(lessonsBlock(lessonSet([lessonEntry(1)], { unavailable: 'x' }), 'H'), '');
  const long = Array.from({ length: 60 }, (_, i) => `line ${i}`).join('\n');
  const set = lessonSet([
    lessonEntry(1, { score: 6, kind: 'process', newerThanSpec: true, text: long }),
    lessonEntry(2, { text: 'short' }),
    { id: 'not-an-id', title: 'x', path: 'p' },
  ]);
  const block = lessonsBlock(set, 'Lessons heading:');
  assert.equal(block, lessonsBlock(set, 'Lessons heading:'));
  assert.ok(block.startsWith('\nLessons heading:\n\n### LESSON-101 — t1 (score 6; process; newer than spec)\n'));
  assert.ok(block.includes('line 38\n[… truncated — read LESSON-101 for the rest]'));
  assert.ok(!block.includes('line 39'));
  assert.ok(block.includes('### LESSON-102 — t2\nshort'));
  assert.ok(!block.includes('not-an-id'));
});

test('lessonsLogLine: names the lessons, brackets the newer-than-spec ones, reports unavailable (BR-10)', () => {
  const set = lessonSet([lessonEntry(1), lessonEntry(2, { newerThanSpec: true })]);
  assert.equal(lessonsLogLine('task TASK-012', set), 'Lessons loaded (task TASK-012): LESSON-101 [newer-than-spec: LESSON-102]');
  assert.equal(lessonsLogLine('step0', lessonSet([])), 'Lessons loaded (step0): none');
  assert.equal(lessonsLogLine('phase5', lessonSet([], { unavailable: 'lessons.py not found in the installed toolkit' })),
    'Lessons loaded (phase5): unavailable — lessons.py not found in the installed toolkit');
  assert.equal(lessonsLogLine('step0', null), 'Lessons loaded (step0): unavailable — retrieval leaf returned nothing');
});

test('taskSetsById: maps rows by taskId, first wins, malformed rows dropped', () => {
  const a = lessonSet([lessonEntry(1)]);
  const b = lessonSet([lessonEntry(2)]);
  assert.deepEqual(taskSetsById({ sets: [{ taskId: 'TASK-1', set: a }, { taskId: 'TASK-1', set: b }, { set: b }, null] }), { 'TASK-1': a });
  assert.deepEqual(taskSetsById(null), {});
});

test('lessons retrieval prompts never read args.answers, so a resume replays them byte-identically (BR-6)', () => {
  const src = require('node:fs').readFileSync(
    require('node:path').join(__dirname, '..', 'adlc-sprint.workflow.js'), 'utf8');
  for (const name of ['lessonsPrompt', 'taskLessonsPrompt', 'lessonsStatePath', 'lessonsFenceLines', 'lessonsUnavailableLines', 'retrieveLessons']) {
    const at = src.indexOf(`function ${name}(`);
    assert.ok(at >= 0, `${name} is defined`);
    const body = src.slice(at, src.indexOf('\n}\n', at));
    assert.doesNotMatch(body, /\bargs\b|\bans\b|answers/, `${name} must not depend on the resume answers`);
  }
  // every dispatch of the three prompts receives a LessonSet
  assert.match(src, /architectPrompt\(id, worktree, exploreReports, STEP0_LESSONS\)/);
  assert.match(src, /implementPrompt\(id, worktree, task, \(taskLessonSets \|\| \{\}\)\[task\.id\]\)/);
  assert.equal((src.match(/^\s+lessonSet, \/\/ REQ-647 BR-3/gm) || []).length, 2, 'both reviewPrompt dispatch sites pass the set');
  assert.equal((src.match(/dedupeAndRank\(escalateByLessons\(/g) || []).length, 2, 'both consolidations escalate first');
});
