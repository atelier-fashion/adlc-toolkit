// Loads the sentinel-delimited PURE section of a self-contained workflow script and
// evaluates it with runtime globals absent, returning its module.exports. This is how
// node:test covers pure logic inlined into a workflow file (the Workflow runtime has no require).
//
// The PURE section is wrapped in a function whose parameters shadow the Workflow
// runtime globals (agent/parallel/pipeline/log/phase/args/budget) to `undefined`
// — proving the section is pure (it must not reach for them) — and is given a
// `module` to populate. We evaluate via `vm.runInThisContext` (NOT a fresh VM
// realm) so object/array literals the helpers return get the HOST realm's
// prototypes; otherwise node:assert's prototype-sensitive deepStrictEqual would
// reject cross-realm values that are structurally identical. (REQ-474)
const fs = require('node:fs');
const vm = require('node:vm');
const BEGIN = '// ==== BEGIN PURE ====';
const END = '// ==== END PURE ====';
module.exports = function loadPure(workflowPath) {
  const src = fs.readFileSync(workflowPath, 'utf8');
  const a = src.indexOf(BEGIN), b = src.indexOf(END);
  if (a < 0 || b < 0 || b < a) throw new Error('PURE sentinels not found in ' + workflowPath);
  const pure = src.slice(a + BEGIN.length, b);
  // Runtime globals are parameters left unbound (undefined) so the pure section
  // cannot lean on them; `module` is the only thing passed in.
  const factory = vm.runInThisContext(
    '(function(module, agent, parallel, pipeline, log, phase, args, budget){\n'
    + pure
    + '\n})',
    { filename: workflowPath },
  );
  const mod = { exports: {} };
  factory(mod);
  return mod.exports;
};
