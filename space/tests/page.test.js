// space/tests/page.test.js — the Space page, its DOM layer, the sample and the card
// (REQ-670 TASK-148).
//
// Two kinds of evidence. Structural checks read index.html, app.js and intake.js as text:
// the disclosure comes before the key input, the CSP pins the network, and no script
// reaches an HTML sink, browser storage or the console. Behavioral checks drive app.js's
// real mount() against a minimal fake document and a spy fetch, so "no key makes no model
// call" and "the model id is on the page before a key" are observed, not inferred. The
// fake keeps the suite at zero dependencies (no jsdom).
//
// Runner: Node's built-in node:test. From the toolkit root:
//
//     node --test 'space/tests/*.test.js'

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SPACE = path.resolve(__dirname, '..');
const read = (f) => fs.readFileSync(path.join(SPACE, f), 'utf8');

const app = require('../app.js');
const intake = require('../intake.js');
const toolkit = require('../toolkit-data.js');
const sample = require('../sample.js');
const config = JSON.parse(read('config.json'));

// Source text with comments removed, so a word in a comment is not a finding and a call
// hidden after one is not missed.
function code(file) {
  return read(file)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"\\])\/\/.*$/gm, '$1');
}

// --- a minimal fake DOM ------------------------------------------------------------

function fakeElement(id) {
  return {
    id,
    textContent: '',
    value: '',
    className: '',
    disabled: false,
    children: [],
    listeners: {},
    addEventListener(type, fn) {
      this.listeners[type] = fn;
    },
    appendChild(c) {
      this.children.push(c);
      return c;
    },
    removeChild(c) {
      this.children.splice(this.children.indexOf(c), 1);
    },
    get firstChild() {
      return this.children[0] || null;
    },
    click() {},
  };
}

function fakePage(fetchReplies) {
  const ids = [...read('index.html').matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
  const els = Object.fromEntries(ids.map((id) => [id, fakeElement(id)]));
  const doc = {
    getElementById: (id) => els[id] || null,
    createElement: (tag) => fakeElement(tag),
    createTextNode: (text) => ({ textContent: text }),
    body: fakeElement('body'),
  };
  const calls = [];
  const win = {
    ADLC_TOOLKIT: toolkit,
    ADLC_SAMPLE: sample,
    AdlcIntake: intake,
    fetch: async (url, init) => {
      calls.push({ url, init });
      const r = fetchReplies(url, init);
      const text = JSON.stringify(r.body);
      return { ok: r.status === 200, status: r.status, text: async () => text, json: async () => r.body };
    },
    setTimeout: (fn) => fn(),
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
    Blob: function (parts) {
      this.text = parts.join('');
    },
  };
  return { els, doc, win, calls };
}

const tick = () => new Promise((r) => setImmediate(r));
const settle = async () => {
  for (let i = 0; i < 6; i += 1) await tick();
};

// Every string the fake page holds, for grepping.
function pageText(els) {
  const walk = (el) => [el.textContent || '', el.value || '', ...(el.children || []).flatMap(walk)];
  return Object.values(els).flatMap(walk).join('\n');
}

function livePage(reply) {
  return fakePage((url, init) => (url === 'config.json' ? { status: 200, body: config } : reply(url, init)));
}

function configOnly(url) {
  if (url === 'config.json') return { status: 200, body: config };
  throw new Error(`unexpected request to ${url}`);
}

// --- structural ----------------------------------------------------------------------

test('disclosure and model id precede the key input', () => {
  const html = read('index.html');
  const key = html.indexOf('id="api-key"');
  assert.ok(key > 0);
  for (const marker of [
    'id="disclosure"',
    'id="model-id"',
    "straight to <strong>Anthropic's API, under your own API key",
    'Nothing is stored',
    'may not share with Anthropic',
  ]) {
    const at = html.indexOf(marker);
    assert.ok(at > 0 && at < key, `${marker} must come before the key input`);
  }
});

test('CSP limits connect-src', () => {
  const html = read('index.html');
  const csp = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/);
  assert.ok(csp, 'CSP meta tag present');
  const directives = Object.fromEntries(
    csp[1].split(';').map((d) => d.trim().split(/\s+/)).map(([k, ...v]) => [k, v.join(' ')]),
  );
  assert.equal(directives['connect-src'], "'self' https://api.anthropic.com");
  assert.equal(directives['script-src'], "'self'");
  assert.equal(directives['default-src'], "'none'");
  // No inline script and no inline handlers, which the CSP would block anyway.
  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    assert.match(m[1], /\ssrc="[^"]+"/);
    assert.equal(m[2].trim(), '');
  }
  assert.doesNotMatch(html, /\son[a-z]+\s*=/i);
  // Every referenced file exists.
  for (const m of html.matchAll(/(?:src|href)="([^":]+)"/g)) {
    assert.ok(fs.existsSync(path.join(SPACE, m[1])), m[1]);
  }
});

test('no storage, console or HTML sinks', () => {
  const banned = [
    /\binnerHTML\b/, /\bouterHTML\b/, /\binsertAdjacentHTML\b/, /\bdocument\.write\b/,
    /\blocalStorage\b/, /\bsessionStorage\b/, /\bindexedDB\b/, /\.cookie\b/,
    /\bconsole\s*\./, /\beval\s*\(/, /\bnew\s+Function\b/, /\bsendBeacon\b/, /\bXMLHttpRequest\b/,
  ];
  for (const file of ['app.js', 'intake.js', 'sample.js']) {
    const src = code(file);
    for (const re of banned) assert.doesNotMatch(src, re, `${file}: ${re}`);
  }
  // The one network call in intake.js goes to the fixed endpoint; app.js fetches only config.json.
  assert.equal(intake.ENDPOINT, 'https://api.anthropic.com/v1/messages');
  assert.deepEqual([...code('app.js').matchAll(/\.fetch\(\s*'([^']+)'/g)].map((m) => m[1]), ['config.json']);
});

test('card links only live targets', () => {
  const card = read('README.md');
  const front = card.match(/^---\n([\s\S]*?)\n---\n/);
  assert.ok(front, 'YAML front matter');
  assert.match(front[1], /^sdk: static$/m);
  assert.match(front[1], /^app_file: index\.html$/m);
  assert.ok(card.includes('https://github.com/atelier-fashion/adlc-toolkit'));
  for (const cmd of toolkit.installCommands) assert.ok(card.includes(cmd), cmd);
  assert.ok(card.includes(`${toolkit.maxLines} lines`), 'the budget the card states is the built one');
  // REQ-671's dataset is not live yet: no dataset link, not even a dead one (BR-13).
  assert.doesNotMatch(card, /huggingface\.co\/datasets/);
  const links = [...card.matchAll(/https?:\/\/[^\s)]+/g)].map((m) => m[0]);
  assert.deepEqual([...new Set(links)], ['https://github.com/atelier-fashion/adlc-toolkit']);
});

// --- behavioral ----------------------------------------------------------------------

test('model id comes from config.json', async () => {
  const { els, doc, win, calls } = fakePage(configOnly);
  app.mount(doc, win);
  await tick();
  assert.equal(els['model-id'].textContent, config.model);
  assert.equal(els['api-key'].value, '', 'shown before any key is entered');
  assert.deepEqual(calls.map((c) => c.url), ['config.json']);
  assert.equal(els.run.disabled, false);
  assert.equal(els['toolkit-version'].textContent, toolkit.version);

  // A different config.json is a different model on the page, with no code change.
  const other = fakePage((url) => ({ status: 200, body: { model: 'claude-other-model', max_tokens: 1 } }));
  app.mount(other.doc, other.win);
  await tick();
  assert.equal(other.els['model-id'].textContent, 'claude-other-model');
});

test('no key shows the sample and makes no call', async () => {
  const { els, doc, win, calls } = fakePage(configOnly);
  app.mount(doc, win);
  await tick();
  assert.equal(els.requirement.textContent, sample.output.requirement_md, 'sample shown on load');
  els.source.value = 'Some notes of my own.\n';
  els['api-key'].value = '   ';
  els.run.listeners.click();
  await tick();
  await tick();
  assert.deepEqual(calls.map((c) => c.url), ['config.json'], 'no model call');
  assert.equal(els['output-kind'].textContent, '(sample)');
  assert.match(els.status.textContent, /Nothing was sent/);

  // Benign path: with a key, the same click does call the model.
  const live = fakePage((url) =>
    url === 'config.json'
      ? { status: 200, body: config }
      : { status: 200, body: { content: [{ type: 'tool_use', name: 'record_intake', input: { requirement_md: '## Description\n\nX.\n', gaps: [] } }] } },
  );
  app.mount(live.doc, live.win);
  await tick();
  live.els.source.value = 'Notes.\n';
  live.els['api-key'].value = 'test-key-not-real';
  live.els.run.listeners.click();
  for (let i = 0; i < 5; i += 1) await tick();
  assert.deepEqual(live.calls.map((c) => c.url), ['config.json', intake.ENDPOINT]);
  assert.equal(live.els['output-kind'].textContent, '(your run)');
});

test('handleRun decisions', async () => {
  const spy = async () => {
    throw new Error('must not be called');
  };
  const base = { config, toolkit, sample, intake, fetchImpl: spy };
  assert.equal((await app.handleRun({ ...base, apiKey: '', source: 'x' })).kind, 'sample');
  assert.equal((await app.handleRun({ ...base, apiKey: undefined, source: 'x' })).kind, 'sample');
  assert.equal((await app.handleRun({ ...base, apiKey: 'k', source: '  \n' })).kind, 'empty');
});

test('download matches display and next step has install commands', async () => {
  const { els, doc, win } = fakePage(configOnly);
  app.mount(doc, win);
  await tick();
  let blob = null;
  win.Blob = function (parts) {
    blob = parts.join('');
  };
  const anchors = [];
  doc.createElement = (tag) => {
    const el = fakeElement(tag);
    anchors.push(el);
    return el;
  };
  els.download.listeners.click();
  assert.equal(blob, els.requirement.textContent);
  assert.equal(anchors.at(-1).download, 'requirement.md');
  assert.equal(app.downloadText(sample.output), sample.output.requirement_md);

  const next = els['next-step'].textContent;
  for (const cmd of toolkit.installCommands) assert.ok(next.includes(cmd), cmd);
  assert.ok(next.includes('/adlc:spec --intake'));
});

test('rendering uses text nodes, so markup in a result stays text', async () => {
  const hostile = '<img src=x onerror=alert(1)>';
  const live = fakePage((url) =>
    url === 'config.json'
      ? { status: 200, body: config }
      : {
          status: 200,
          body: {
            content: [{
              type: 'tool_use',
              name: 'record_intake',
              input: {
                requirement_md: `## Description\n\n${hostile}\n`,
                gaps: [{ section: 'Business Rules', severity: 'blocking', question: `${hostile}?`, justification: hostile }],
              },
            }],
          },
        },
  );
  app.mount(live.doc, live.win);
  await tick();
  live.els.source.value = 'Notes.\n';
  live.els['api-key'].value = 'test-key-not-real';
  live.els.run.listeners.click();
  await settle();
  assert.ok(live.els.requirement.textContent.includes(hostile), 'shown verbatim, as text');
  const li = live.els.gaps.children[0];
  assert.ok(li.children.some((c) => c.textContent.includes(hostile)));
});

test('sample carries every required section and well-formed gaps', () => {
  const md = sample.output.requirement_md;
  for (const s of toolkit.requiredSections) assert.ok(md.split('\n').includes(`## ${s}`), s);
  assert.ok(intake.countLines(sample.input) > 10);
  const sevs = new Set(sample.output.gaps.map((g) => g.severity));
  assert.deepEqual([...sevs].sort(), ['assumption', 'blocking']);
  for (const gap of sample.output.gaps) {
    assert.match(gap.question, /\?$/);
    assert.ok(gap.justification.length > 20);
    assert.ok(toolkit.templateSections.includes(gap.section), gap.section);
  }
  // Blocking gaps are open questions in the sample too, as BR-5 has it for live runs.
  for (const gap of sample.output.gaps.filter((g) => g.severity === 'blocking')) {
    assert.ok(intake.ensureOpenQuestions(md, [gap]) === md, gap.question);
  }
});

test('a failed config.json leaves live runs off and the sample up', async () => {
  for (const reply of [() => ({ status: 404, body: {} }), () => ({ status: 200, body: { model: 7 } })]) {
    const { els, doc, win } = fakePage(reply);
    app.mount(doc, win);
    await settle();
    assert.equal(els['model-id'].textContent, 'unavailable');
    assert.equal(els.run.disabled, true);
    assert.equal(els.status.className, 'error');
    assert.equal(els.requirement.textContent, sample.output.requirement_md);
  }
});

test('uploads are normalized, oversized ones refused, and read errors reported', async () => {
  const { els, doc, win } = fakePage(configOnly);
  app.mount(doc, win);
  await tick();
  els.file.listeners.change({ target: { files: [{ name: 'notes.md', size: 10, text: async () => 'a\r\nb\r\n' }] } });
  await settle();
  assert.equal(els.source.value, 'a\nb\n');
  assert.match(els.status.textContent, /notes\.md \(2 lines\)/);

  let read = false;
  const big = { name: 'big.bin', size: app.maxUploadBytes(toolkit) + 1, text: async () => { read = true; return ''; } };
  els.file.listeners.change({ target: { files: [big] } });
  await settle();
  assert.equal(read, false, 'not read');
  assert.equal(els.status.className, 'error');

  els.file.listeners.change({ target: { files: [{ name: 'bad.txt', size: 1, text: async () => { throw new Error('io'); } }] } });
  await settle();
  assert.match(els.status.textContent, /Could not read bad\.txt/);
});

test('an error shows its class on the page, and the key appears nowhere on it', async () => {
  const key = 'sk-ant-' + 'api03-' + 'PAGESENTINEL0123456789abcdef';
  const { els, doc, win } = livePage(() => ({ status: 401, body: { error: { type: 'authentication_error', message: `invalid x-api-key ${key}` } } }));
  app.mount(doc, win);
  await tick();
  els.source.value = 'Notes.\n';
  els['api-key'].value = key;
  els.run.listeners.click();
  await settle();
  assert.match(els.status.textContent, /^Invalid API key/);
  assert.equal(els.status.className, 'error');
  els['api-key'].value = '';
  assert.ok(!pageText(els).includes(key));
  assert.ok(!pageText(els).includes('PAGESENTINEL'));
});

test('a live run shows its redaction count and downloads what it displays', async () => {
  const aws = 'AKIA' + 'IOSFODNN7EXAMPLE';
  const gh = 'ghp_' + 'abcdefghijklmnopqrstuvwxyz0123456789AB';
  const md = toolkit.requiredSections.map((x) => `## ${x}\n\nLive ${x}.`).join('\n\n');
  const { els, doc, win, calls } = livePage(() => ({
    status: 200,
    body: { content: [{ type: 'tool_use', name: 'record_intake', input: { requirement_md: md, gaps: [] } }] },
  }));
  app.mount(doc, win);
  await tick();
  els.source.value = `keys ${aws}\nand ${gh}\n`;
  els['api-key'].value = '  test-key-not-real  ';
  els.run.listeners.click();
  await settle();
  assert.equal(calls[1].init.headers['x-api-key'], 'test-key-not-real', 'the key is trimmed');
  assert.match(els.redactions.textContent, /^2 credential-shaped strings were removed/);
  assert.ok(els.requirement.textContent.includes('Live Description.'));
  let blob = null;
  win.Blob = function (parts) {
    blob = parts.join('');
  };
  els.download.listeners.click();
  assert.equal(blob, els.requirement.textContent);
});
