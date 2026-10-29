// space/tests/build.test.js — the BR-3 build step and its drift check (REQ-670 TASK-134).
//
// Each mutation runs against a temp copy of the toolkit inputs, never the checkout, and
// the unchanged copy passing `--check` is the benign path: a drift check that fails on a
// clean tree is as broken as one that never fails.
//
// Runner: Node's built-in node:test, zero dependencies. From the toolkit root:
//
//     node --test 'space/tests/*.test.js'

'use strict';

const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', '..');
const INPUTS = [
  'templates/requirement-template.md',
  'partials/intake.sh',
  'spec/SKILL.md',
  'README.md',
  'VERSION',
  'space/toolkit-data.js',
];

const build = () => import(path.join(ROOT, 'space', 'build.mjs'));

const temps = [];
after(() => temps.forEach((d) => fs.rmSync(d, { recursive: true, force: true })));

function tempToolkit() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'adlc-space-build-'));
  temps.push(dir);
  for (const rel of INPUTS) {
    fs.mkdirSync(path.join(dir, path.dirname(rel)), { recursive: true });
    fs.copyFileSync(path.join(ROOT, rel), path.join(dir, rel));
  }
  return dir;
}

// Run main() against a temp root, capturing stderr.
async function run(dir, extra = []) {
  const { main } = await build();
  const chunks = [];
  const write = process.stderr.write;
  process.stderr.write = (s) => {
    chunks.push(String(s));
    return true;
  };
  try {
    const rc = main(['node', 'build.mjs', '--root', dir, ...extra]);
    return { rc, err: chunks.join('') };
  } finally {
    process.stderr.write = write;
  }
}

function edit(dir, rel, fn) {
  const p = path.join(dir, rel);
  fs.writeFileSync(p, fn(fs.readFileSync(p, 'utf8')));
}

test('the committed toolkit-data.js matches the toolkit (benign path)', async () => {
  const { rc, err } = await run(ROOT, ['--check']);
  assert.equal(rc, 0, err);
});

test('build is idempotent', async () => {
  const dir = tempToolkit();
  const before = fs.readFileSync(path.join(dir, 'space/toolkit-data.js'), 'utf8');
  assert.equal((await run(dir)).rc, 0);
  assert.equal(fs.readFileSync(path.join(dir, 'space/toolkit-data.js'), 'utf8'), before);
  assert.equal((await run(dir, ['--check'])).rc, 0);
});

test('check fails when the template changes', async () => {
  const dir = tempToolkit();
  assert.equal((await run(dir, ['--check'])).rc, 0, 'unchanged copy must pass');
  edit(dir, 'templates/requirement-template.md', (t) => t + '\n## Rollout Plan\n');
  const { rc, err } = await run(dir, ['--check']);
  assert.equal(rc, 1);
  assert.match(err, /template/);
  assert.match(err, /templateSections/);
});

test('check fails when the gap rules change', async () => {
  const dir = tempToolkit();
  edit(dir, 'spec/SKILL.md', (t) =>
    t.replace('<!-- /intake-gap-rules -->', 'A new rule.\n\n   <!-- /intake-gap-rules -->'),
  );
  const { rc, err } = await run(dir, ['--check']);
  assert.equal(rc, 1);
  assert.match(err, /gapRules/);
});

test('check fails when the redaction chain changes', async () => {
  const dir = tempToolkit();
  edit(dir, 'partials/intake.sh', (t) => t.replace('ghp_[A-Za-z0-9]{36,}|', 'ghp_[A-Za-z0-9]{36,}|hf_[A-Za-z0-9]{30,}|'));
  const { rc, err } = await run(dir, ['--check']);
  assert.equal(rc, 1);
  assert.match(err, /redactPattern/);
});

test('missing gap-rule markers exit 2, never an empty rule block', async () => {
  const dir = tempToolkit();
  edit(dir, 'spec/SKILL.md', (t) => t.replace('<!-- /intake-gap-rules -->', ''));
  const { rc, err } = await run(dir);
  assert.equal(rc, 2);
  assert.match(err, /intake-gap-rules markers/);
});

test('a missing input exits 2 and names it', async () => {
  const dir = tempToolkit();
  fs.rmSync(path.join(dir, 'VERSION'));
  const { rc, err } = await run(dir);
  assert.equal(rc, 2);
  assert.match(err, /missing input: VERSION/);
});

test('budget constants come from intake.sh', async () => {
  const d = require('../toolkit-data.js');
  const intake = fs.readFileSync(path.join(ROOT, 'partials/intake.sh'), 'utf8');
  assert.match(intake, new RegExp(`^ADLC_INTAKE_SEGMENT_LINES=${d.segmentLines}$`, 'm'));
  assert.match(intake, new RegExp(`^ADLC_INTAKE_MAX_SEGMENTS=${d.maxSegments}$`, 'm'));
  assert.equal(d.segmentLines, 200);
  assert.equal(d.maxSegments, 40);
  assert.equal(d.maxLines, 8000);
});

test('redaction regex translated from intake.sh', async () => {
  const { translatePosix, BuildError } = await build();
  const d = require('../toolkit-data.js');
  assert.doesNotMatch(d.redactPattern, /\[:[a-z]+:\]/);
  assert.equal(translatePosix('a[[:space:]]b[^[:space:]]+'), 'a\\sb\\S+');
  assert.throws(() => translatePosix('[[:alpha:]]'), BuildError);
  // The translated chain matches what the sed chain is for.
  const re = new RegExp(d.redactPattern, d.redactFlags);
  const aws = 'AKIA' + 'ABCDEFGHIJKLMNOP';
  const env = 'MY_API_KEY' + ' = ' + 'value123';
  assert.equal(`x ${aws} y`.replace(re, '[REDACTED]'), 'x [REDACTED] y');
  assert.equal(`${env} tail`.replace(re, '[REDACTED]'), '[REDACTED] tail');
  assert.equal('nothing secret here'.replace(re, '[REDACTED]'), 'nothing secret here');
});

test('gap sections are the template headings minus intake.sh exclusions', async () => {
  const d = require('../toolkit-data.js');
  const tpl = fs.readFileSync(path.join(ROOT, 'templates/requirement-template.md'), 'utf8');
  const headings = tpl.split('\n').filter((l) => l.startsWith('## ')).map((l) => l.slice(3).trim());
  assert.deepEqual(d.templateSections, headings);
  for (const s of ['Description', 'Assumptions', 'Open Questions', 'Retrieved Context', 'Provenance']) {
    assert.ok(!d.gapSections.includes(s), s);
  }
  assert.ok(d.gapSections.includes('Business Rules'));
});

test('required sections are the uncommented headings plus intake-only Provenance', async () => {
  const { requiredSections, BuildError } = await build();
  const d = require('../toolkit-data.js');
  assert.ok(d.requiredSections.includes('Provenance'));
  assert.ok(!d.requiredSections.includes('Retrieved Context'));
  assert.ok(d.requiredSections.includes('Open Questions'));
  const tpl = '## A\n<!--\nOPTIONAL — intake only\n## P\n-->\n<!--\n## R\n-->\n## B\n';
  assert.throws(() => requiredSections(tpl), BuildError); // no Provenance
  assert.deepEqual(requiredSections(tpl.replace('## P', '## Provenance')), ['A', 'Provenance', 'B']);
});

test('install commands come from README', () => {
  const d = require('../toolkit-data.js');
  const readme = fs.readFileSync(path.join(ROOT, 'README.md'), 'utf8');
  assert.equal(d.installCommands.length, 2);
  for (const cmd of d.installCommands) assert.ok(readme.includes(cmd), cmd);
  assert.match(d.installCommands[0], /^claude plugin marketplace add /);
  assert.match(d.installCommands[1], /^claude plugin install /);
});
