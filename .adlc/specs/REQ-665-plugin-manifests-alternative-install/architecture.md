# Architecture — REQ-665: plugin manifests as an alternative install

## Approach

Two JSON files and one lint change. `.cursor-plugin/plugin.json` and
`.github/plugin/plugin.json` point Cursor and Copilot at the existing root-level
skill directories with `"skills": "./"`, and switch off their default `agents/`
and `hooks/hooks.json` discovery with `"agents": []` and `"hooks": {}`. The
`plugin-manifest` lint becomes `manifest-parity`, driven by a one-place registry of
the three harnesses. `.claude-plugin/`, `hooks/`, `install.sh`, skills, agents and
partials are not touched. No data model, API or service layer is involved.

Applied lessons: LESSON-012 (structural guard, not prose), LESSON-019 (an armed
check must not disarm when its subject is deleted), LESSON-572 (a remediation must
be executable by its reader), LESSON-395 (stdlib only), LESSON-716 (repeated JSON
keys), LESSON-747/755 (a capability claim comes from the installed binary, so
Cursor and Copilot claims stay marked unverified), LESSON-751 (figures re-measured
at Phase 1: 17 skills, 19 agents).

## Key decisions

### ADR-1: `manifest-parity` absorbs `plugin-manifest` the way `no-harness-path` absorbed `toolkit-path`

`PLUGIN_MANIFEST_CHECK`'s value changes to `"manifest-parity"`. `scan_plugin_manifest`, `check_plugin_manifest`,
`is_plugin_root`, the fixture directory and `test_plugin_manifest.py` keep their
names, so `is_plugin_root`'s seven other callers and the toolkit-path tests are
untouched (REQ-666 TASK-184's precedent). New acceptance tests go in a new file,
`test_manifest_parity.py`, as `test_no_harness_path.py` did. `CHANGELOG.md`'s
older entries stay as history.

**Why not a new check beside the old one:** REQ-669 BR-18 says it absorbs, and two
checks would report one version drift twice.

### ADR-2: one registry, one per-manifest walk

```python
class ManifestEntry(NamedTuple):
    harness: str
    path: str
    companions: tuple[str, ...]
    keys: frozenset[str]   # the keys its vendor documents
    agents: str            # "canonical" | "empty"
    hooks: str             # "default" | "empty"
    name_rules: bool       # its marketplace rules on `name` apply
```

`MANIFEST_REGISTRY` holds `claude`, `cursor`, `copilot` and is the only definition
of the set (BR-1). `_check_plugin_fields` is generalised to walk one entry; the
Claude-only rules (name shape and reserved prefixes, the marketplace entry, the
top-level `bin`) stay. The name rules are read from the entry, `name_rules`, rather
than from its path (LESSON-748).
Adding a harness starts with an entry and its file; the bump in `RELEASING.md` and
`plugin-sandbox.sh`, and the README subsection, follow.

### ADR-3: the rule name leads the message; `Finding.check` stays `manifest-parity`

`file:line: manifest-parity: version-mismatch: …`. Sub-rule ids in `Finding.check`
exist elsewhere (`rules-block-*`), but `_scan` pins one id and AC-3 and AC-12 talk
about one check firing named rules. The remediation stays the clause after the em
dash, naming the file. REQ-669's reserved-name, marketplace and `bin` messages keep
their wording; the rules BR-7 names gain their tag.

### ADR-4: arming is unchanged, so AC-4 was revised

An armed root with no manifests yields one `set-incomplete` per manifest, because
REQ-669's arming (`.claude-plugin/` or a versioned skills root) exists so deleting
the manifests cannot disarm the check (LESSON-019). `is_plugin_root` is not widened.

### ADR-5: `"./"` as the committed form, array form still linted

All three committed manifests use `"skills": "./"`, the container form each
harness documents for a skills path, so a new skill needs no manifest edit. The
array form stays legal, and it is where `skill-missing`, `skill-extra` and
`dangling-entry` fire. Enumerating 17 entries would add edit churn on every skill
and rest on the same unverified reading of "skill directories".

### ADR-6: explicit empties, not omissions, for agents and hooks

Cursor and Copilot both name `agents/` and `hooks/hooks.json` as defaults. Omitting
the keys would let the Claude-format files load. `"agents": []` and `"hooks": {}`
use the documented override. `agents-ref-invalid` and `hooks-ref-invalid` hold the
shape. If a harness treats an empty override as absent, the result equals omitting
the key. If it rejects the empty value, the install fails or the plugin does not
load, which is louder than omitting the key and is the outcome to check first on a
real install (Deferred).

### ADR-7: `.github/plugin/plugin.json` for Copilot

Copilot's legacy lookup finds `.plugin/plugin.json`, `plugin.json`,
`.github/plugin/plugin.json`, then `.claude-plugin/plugin.json`. A root
`plugin.json` or a `.plugin/` directory could be read by other tools; the `.github`
path names Copilot alone. `.github/` is new to this repo and holds no workflow.
`lane_check.py` already blocks `.github/**`, and `.cursor-plugin/**` stays
countable: BR-4 leaves the tuple unchanged. A lite REQ editing a manifest stays
within `manifest-parity`'s guard only because `execution-key` refuses every key that runs, installs or prompts, every inline
definition, and those surfaces at their default locations: a manifest is what a
harness acts on at install, and `path-missing` reads paths, so it could see none of
them (LESSON-749).

### ADR-8: no root `skills/`, enforced

BR-2's ban on a root `skills/` is a lint rule (`skill-extra`), because it is the
first thing a future Gemini attempt would add, and on Claude Code it would double
the catalog with no failure anywhere else.

### ADR-9: `scanned` counts files read

`scan_plugin_manifest`'s second value counts manifests and companions found, so 4
on a complete root. A missing `VERSION` is one finding, not one per manifest.

## Blast radius

- **`tools/adlc/tests/e2e/plugin-sandbox.sh`:** `cmd_set_version` follows RELEASING
  steps 2 and 3, so it writes all three manifests, or its release case fails the lint.
- **`test_plugin_manifest.py`:** fixtures gain the two manifests by overlay at
  `_stage` (from `ok`, with the tree's own `VERSION`), so the seven trees need no
  new files; `scanned` literals become 4; the name-parameter cases edit every
  manifest; line 124's filter must move to the new id or it passes vacuously.
- **`space/build.mjs`:** reads the first `claude plugin …` README lines. New README
  lines must not start with those prefixes before REQ-669's.
- **`README.md`:** not a `no-harness-path` surface, so `~/.cursor` is allowed there,
  and never in tools, partials or templates.

## What is not verified

See the spec's `## Deferred` and `verification.md`. No Cursor, Copilot or Gemini
binary was available, so nothing about those harnesses' runtime is claimed as tested.
