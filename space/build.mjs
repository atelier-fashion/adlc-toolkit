#!/usr/bin/env node
// space/build.mjs — generate space/toolkit-data.js from the toolkit it sits in (REQ-670 ADR-3).
//
// The Space serves the toolkit's own requirement template, /spec intake's gap rules, its
// source budget and its credential-redaction chain. None of them is copied by hand: this
// script reads them from the toolkit checkout and writes one generated file, and
// `--check` fails when the committed file differs from what the toolkit would generate
// (BR-3). Run it from a tagged release before deploying (RELEASING.md).
//
//     node space/build.mjs            # write space/toolkit-data.js
//     node space/build.mjs --check    # exit 1 on drift, naming each differing field
//     node space/build.mjs --root <toolkit-dir> [--out <file>] [--check]
//
// Exit codes: 0 ok, 1 drift (--check only), 2 an input is missing or unreadable.
// Zero dependencies: Node's standard library only.

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

export class BuildError extends Error {}

const read = (root, rel) => {
  const p = join(root, rel);
  if (!existsSync(p)) throw new BuildError(`missing input: ${rel}`);
  return readFileSync(p, 'utf8');
};

// The template's level-2 headings, as `adlc_intake_sections` reads them.
export function templateSections(template) {
  return template
    .split('\n')
    .filter((l) => l.startsWith('## '))
    .map((l) => l.replace(/^##\s*/, '').replace(/\s*$/, ''));
}

// The sections an intake result must carry: every heading outside an HTML comment, plus
// a commented-out heading whose comment says it is for intake only (`## Provenance`).
// Other commented headings (`## Retrieved Context`) are omitted, as the template says
// to when the skill has not run retrieval, and the Space runs none.
export function requiredSections(template) {
  const out = [];
  let comment = null;
  for (const line of template.split('\n')) {
    if (comment === null && line.trim().startsWith('<!--')) comment = [];
    if (comment !== null) {
      comment.push(line);
      if (line.includes('-->')) {
        const text = comment.join('\n');
        if (/intake only/i.test(text)) {
          const h = comment.find((l) => l.startsWith('## '));
          if (h) out.push(h.slice(3).trim());
        }
        comment = null;
      }
      continue;
    }
    if (line.startsWith('## ')) out.push(line.slice(3).trim());
  }
  if (!out.includes('Provenance')) {
    throw new BuildError('templates/requirement-template.md: no intake-only ## Provenance section found');
  }
  return out;
}

// The lines between the intake-gap-rules markers in spec/SKILL.md, verbatim, with the
// blank lines that pad the markers removed.
export function gapRules(skill) {
  const lines = skill.split('\n');
  const start = lines.findIndex((l) => l.trim().startsWith('<!-- intake-gap-rules'));
  const end = lines.findIndex((l) => l.trim() === '<!-- /intake-gap-rules -->');
  if (start < 0 || end < 0 || end <= start) {
    throw new BuildError('spec/SKILL.md: intake-gap-rules markers missing or out of order');
  }
  const body = lines.slice(start + 1, end).join('\n').replace(/^\n+/, '').replace(/\n+$/, '');
  if (!body.trim()) throw new BuildError('spec/SKILL.md: intake-gap-rules block is empty');
  return body;
}

function shellInt(intake, name) {
  const m = intake.match(new RegExp(`^${name}=([0-9]+)$`, 'm'));
  if (!m) throw new BuildError(`partials/intake.sh: ${name} not found`);
  return Number(m[1]);
}

// POSIX ERE bracket classes used by the chain, and their JS equivalents. A class not in
// this table is a build error, never a silently non-matching regex.
// The negated form comes first so its inner `[:space:]` is not half-translated.
const POSIX_CLASSES = [
  ['[^[:space:]]', '\\S'],
  ['[[:space:]]', '\\s'],
];

export function translatePosix(ere) {
  let src = ere;
  for (const [posix, js] of POSIX_CLASSES) src = src.split(posix).join(js);
  if (/\[:[a-z]+:\]/.test(src)) {
    throw new BuildError(`partials/intake.sh: untranslated POSIX class in redaction regex: ${src}`);
  }
  new RegExp(src, 'g'); // throws on a regex JS cannot compile
  return src;
}

export function redactPattern(intake) {
  const fn = intake.match(/^adlc_intake_redact\(\)[\s\S]*?^}/m);
  if (!fn) throw new BuildError('partials/intake.sh: adlc_intake_redact not found');
  const m = fn[0].match(/sed -i\.bak -E 's\/(.+)\/\[REDACTED\]\/g'/);
  if (!m) throw new BuildError('partials/intake.sh: redaction sed expression not found');
  return translatePosix(m[1]);
}

export function sectionExclusions(intake) {
  const fn = intake.match(/^adlc_intake_sections\(\)[\s\S]*?^}/m);
  if (!fn) throw new BuildError('partials/intake.sh: adlc_intake_sections not found');
  const names = [...fn[0].matchAll(/grep -vxF '([^']+)'/g)].map((x) => x[1]);
  if (!names.length) throw new BuildError('partials/intake.sh: no section exclusions found');
  return names;
}

export function installCommands(readme) {
  const want = ['claude plugin marketplace add ', 'claude plugin install '];
  const lines = readme.split('\n').map((l) => l.trim());
  return want.map((prefix) => {
    const hit = lines.find((l) => l.startsWith(prefix));
    if (!hit) throw new BuildError(`README.md: no line starting "${prefix.trim()}"`);
    return hit;
  });
}

export function collect(root) {
  const template = read(root, 'templates/requirement-template.md');
  const intake = read(root, 'partials/intake.sh');
  const sections = templateSections(template);
  const excluded = sectionExclusions(intake);
  const segmentLines = shellInt(intake, 'ADLC_INTAKE_SEGMENT_LINES');
  const maxSegments = shellInt(intake, 'ADLC_INTAKE_MAX_SEGMENTS');
  return {
    version: read(root, 'VERSION').trim(),
    template,
    templateSections: sections,
    requiredSections: requiredSections(template),
    gapSections: sections.filter((s) => !excluded.includes(s)),
    gapRules: gapRules(read(root, 'spec/SKILL.md')),
    segmentLines,
    maxSegments,
    maxLines: segmentLines * maxSegments,
    redactPattern: redactPattern(intake),
    redactFlags: 'g',
    installCommands: installCommands(read(root, 'README.md')),
  };
}

export function render(data) {
  return `// GENERATED by space/build.mjs from the toolkit at version ${data.version} — do not edit.
// Regenerate with \`node space/build.mjs\`; \`node space/build.mjs --check\` fails on drift (REQ-670 BR-3).
(function (g) {
  var d = ${JSON.stringify(data, null, 2).replace(/\n/g, '\n  ')};
  if (typeof module !== 'undefined' && module.exports) module.exports = d;
  else g.ADLC_TOOLKIT = d;
})(this);
`;
}

// Parse a rendered file back to its data, so --check can name the fields that differ.
export function parseRendered(text) {
  const m = text.match(/var d = (\{[\s\S]*\});\n  if \(typeof module/);
  if (!m) return null;
  try {
    return JSON.parse(m[1]);
  } catch {
    return null;
  }
}

export function diffFields(want, got) {
  if (!got) return ['(unparseable)'];
  const keys = new Set([...Object.keys(want), ...Object.keys(got)]);
  return [...keys].filter((k) => JSON.stringify(want[k]) !== JSON.stringify(got[k])).sort();
}

export function main(argv) {
  const args = argv.slice(2);
  const opt = (name) => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : undefined;
  };
  const root = resolve(opt('--root') ?? join(HERE, '..'));
  const out = resolve(opt('--out') ?? join(root, 'space', 'toolkit-data.js'));
  let text;
  let data;
  try {
    data = collect(root);
    text = render(data);
  } catch (e) {
    if (!(e instanceof BuildError)) throw e;
    process.stderr.write(`space/build.mjs: ${e.message}\n`);
    return 2;
  }
  if (args.includes('--check')) {
    const current = existsSync(out) ? readFileSync(out, 'utf8') : '';
    if (current === text) return 0;
    const fields = diffFields(data, parseRendered(current));
    process.stderr.write(
      `space/build.mjs --check: ${out} differs from the toolkit` +
        ` (${fields.join(', ') || 'formatting'}). Run \`node space/build.mjs\` and commit the result.\n`,
    );
    return 1;
  }
  writeFileSync(out, text);
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv);
}
