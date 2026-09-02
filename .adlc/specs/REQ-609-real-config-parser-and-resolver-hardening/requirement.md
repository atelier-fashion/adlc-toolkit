---
id: REQ-609
title: "A real config parser behind a strict schema, and shell resolution that never consults shell state"
status: draft
deployable: true
created: 2026-09-01
updated: 2026-09-01
component: "tools/delegate"
domain: "adlc"
stack: [python, yaml, shell]
concerns: [data-governance, security, correctness, fail-closed, test-coverage]
tags: [config-parser, pyyaml, schema, single-source, resolver, kill-switch, differential-oracle, req-603-successor]
---

## Description

REQ-603 removed every authorizing arm from the vendored shell gate so that only Python could
grant delegation. That made `parse_delegate_config` — a hand-written flat reader for one
`delegate:` block — the **sole authority** over whether a developer's source files are sent to
a third-party API. Four adversarial passes then found nine distinct fail-opens in that reader,
six of them introduced by the pass that rewrote it under a tests-first, mutation-proven
discipline. A YAML comment on the section header defeated it. A nested mapping hoisted
`enabled: true` over a written `false`. A tab inside a block truncated it. A second
`delegate:` block was unreachable. Each was a shape the author did not imagine and two
reviewers imagined within the hour. The discipline proved what the author tested; it could
not reach what the author did not.

The structural defect is that the reader **skips** what it does not understand. A recognizer
does the opposite. This REQ replaces the reader with `yaml.safe_load` behind a strict schema,
so that "written" and "read" become the same thing, and adds a **differential oracle** to the
suite so the tests are no longer bounded by one author's imagination.

REQ-515 ADR-3 forbade PyYAML "for three scalar fields". That decision was made while the shell
still had arms of its own. The three scalars now gate exfiltration, the venv already pins
`openai`, and hand parsing has cost nine fail-opens. ADR-3 is amended by this REQ.

The same pass found that REQ-603's shell resolver fix closed a **mechanism** and not a
**class**: functions and aliases resolve to a bare name, so bare names were rejected, but the
shell hash table resolves to an absolute path and the corpus was delivered to a planted
binary. Name resolution that consults shell state cannot answer a filesystem question. This
REQ makes the resolver walk `$PATH` directly and never call `command -v`.

**How this relates to REQ-603.** REQ-603 is being split. Its branch resets to `ee5ca91`, the
state before the parser rewrite, and keeps only the proven-safe pieces of `bc7d584`: the stderr
notice on probe failure, the `export` wording in the docs, the corrected `delegate-pre-pass`
claim, and the regenerated hash pin. It gains the two tests pass 4 named that do not depend on
the parser — the `_MALFORMED` arm's ordering, and malformed-config rows in the parity matrix.
Its BR-14 becomes a known-limitation note pointing here, with the resolver's shell-state
exposure recorded beside it. **This REQ owns the parser and the resolver class fix, and
builds on REQ-603 as landed.**

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ParseOutcome | `kind` | enum | exactly one of `absent` \| `parsed` \| `malformed`; never a fourth state |
| MachineConfig | `document` | mapping | the whole `~/.claude/adlc/config.yml`, loaded once; sections read from it |
| DelegateSection | `enabled` | bool | must be a YAML boolean; a string `"false"` is malformed |
| DelegateSection | `model` | str | optional |
| DelegateSection | `base_url` | str | optional |
| DelegateSection | `api_key_env` | str | optional; an env-var NAME, never a value (REQ-515 BR-3) |
| DelegateSection | any other key | — | malformed |
| DelegateSection | any nested mapping | — | malformed |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `config_absent` | path does not exist and is not a dangling symlink | none — continuity may apply |
| `config_parsed` | regular file, valid YAML, schema satisfied | the validated section |
| `config_malformed` | any other outcome | reason class, never file content |
| `dependency_missing` | PyYAML not importable | stderr line naming the package; outcome is `malformed` |

## Business Rules

- [ ] BR-1: the config is parsed with `yaml.safe_load` and never `yaml.load`. PyYAML is pinned at `>=6.0` in `tools/delegate/requirements.txt` and installed by `install.sh`. The import is lazy so `--help` and a config-less `--version` do not pay for it (LESSON-022, BUG-056).
- [ ] BR-2: a repeated mapping key anywhere in the document is malformed. PyYAML's default loader silently takes the last duplicate; for a governance file that is a silent override, and a second `delegate:` block was an unreachable fail-open in REQ-603's rewrite. A custom loader raises on the repeat.
- [ ] BR-3: the outcome is exactly one of `absent`, `parsed`, `malformed`, and the function never raises. `absent` only when `stat` gives `ENOENT`/`ENOTDIR` **and** `lexists` is false — a dangling symlink is malformed. Every error is malformed: `yaml.YAMLError`, `UnicodeDecodeError`, `OSError`, `ValueError` from a NUL in the path, a document that is not a mapping, and a file over the size cap. The cap is unconditional, because a truncated YAML document can still parse.
- [ ] BR-4: a non-regular file at the path is malformed with **no exceptions**. The `/dev/null` carve-out returned `{}`, which is absence, which falls through to legacy-key continuity — `ADLC_CONFIG=/dev/null` turned delegation on (informed by BUG-205).
- [ ] BR-5: both readers — the config and the rc-file key fallback — open with `O_RDONLY | O_NONBLOCK`, decide `S_ISREG` on `fstat` of the opened descriptor, and read through `fdopen`. The kind is checked on the object actually opened, closing the stat-then-open window a fifo could be swapped into.
- [ ] BR-6: a `delegate` section **absent** from a parsed document means *unconfigured* and yields `{}`, so continuity may apply. "No block found is malformed" was a workaround for a reader that could not tell absent from unrecognised, and it locked out every machine whose shared config carried only a `forge:` section. A real parser can tell the difference, so the rule gets simpler.
- [ ] BR-7: a `delegate` section **present** is validated against the strict schema in the System Model. Not a mapping, a non-bool `enabled`, a non-string for the three strings, an unknown key, or a nested mapping is malformed. Unknown keys refuse deliberately: `enbaled: false` silently ignored costs exfiltration, and forward compatibility can be versioned. A quoted `"false"` is the YAML string `"false"`, which Python treats as true; the schema refuses it as ambiguous rather than lowercasing it into an opt-out the operator never wrote.
- [ ] BR-8: one loader, `load_machine_config()`, reads the whole file once and returns the validated document. The delegate code reads its section from that result and `tools/adlc/forge_config.py` reads its section from the same result. The second hand reader is retired; a multi-section config cannot lock out one consumer by the other's rule.
- [ ] BR-9: if PyYAML is not importable at runtime the outcome is malformed and one stderr line names the missing package. A partial install fails closed, never through to `{}`.
- [ ] BR-10: **the differential oracle.** For every config in a seeded corpus — every shape enumerated by REQ-603's pass-3 and pass-4 reviewers — and for generated variants, a test asserts that `parse_delegate_config`'s `enabled` equals `yaml.safe_load(text)["delegate"]["enabled"]` whenever the latter is a bool, and that `resolve_gate_verdict`, `delegation_enabled`, and `require_delegation_enabled` agree on every file. The oracle is a different implementation; a disagreement is the finding (informed by LESSON-602).
- [ ] BR-11: the shell resolver never calls `command -v`. It walks `$PATH` entries split on `:`, skips any entry that does not begin with `/`, and tests `dir/adlc-read` with `-f` and `-x`; first hit wins. Then `$HOME/bin/adlc-read`, only when `$HOME` begins with `/`. The `timeout` wrapper resolves from a fixed absolute candidate list only, never from `$PATH`. Shell functions, aliases, and the hash table cannot influence either result, because none is consulted (informed by BUG-209).
- [ ] BR-12: the six call-site fences that invoke `"${ADLC_READ_BIN:-adlc-read}"` lose the bare-name fallback. An empty `ADLC_READ_BIN` at the moment the corpus is handed over is a hard error, not a second resolution by a weaker rule.
- [ ] BR-13: `require_delegation_enabled` gains a malformed-config branch that names the config path and the malformed condition. The generic branch tells a locked-out operator to edit the file that is unreadable, and to set an env var that cannot lift the arm.
- [ ] BR-14: REQ-515 ADR-3 is amended in that spec's architecture with the reasoning in the Description. REQ-603's known-limitation note is the pointer here; this REQ's architecture records that it discharges it.
- [ ] BR-15: documentation owned by this REQ is brought to the new contract: the resolver's header comment and `partials/delegate-gate.md` no longer say "the bare name, when it is on PATH"; the rc-reader size cap, the rejection of relative `$PATH` entries, and `--version`'s rc-file read are named in `tools/delegate/README.md`; `test_unparseable_config_reports_shipped_defaults` loses its "fail-SOFT is deliberate" header.
- [ ] BR-16: all shell stays BSD- and zsh-safe: no `\b` in `grep -E` (LESSON-013), no reliance on an unquoted variable word-splitting (LESSON-329 — this bit REQ-603's author four times), no unmatched globs (LESSON-335).

## Acceptance Criteria

- [ ] For each shape in the seeded corpus — header comment, BOM, tab-indented header, quoted key, nested `enabled`, block scalar containing `enabled`, tab inside a space block, duplicate `delegate:` block, duplicate `enabled` key, every non-newline separator `str.splitlines` honours, CRLF endings, `enabled: "false"`, `enabled: ture`, a block past the cap, a header inside the cap with `enabled: false` past it, a directory, a fifo, `/dev/null`, a dangling symlink, an unreadable parent, undecodable bytes, a NUL in the path, an empty file, a file with only a `forge:` section — all three surfaces produce the outcome the System Model specifies, asserted in one parametrised test. (BR-3, BR-4, BR-6, BR-7)
- [ ] The differential oracle passes over the seeded corpus and over a generated corpus, and a mutation that makes the schema disagree with `safe_load` on any bool fails it. (BR-10)
- [ ] With `import yaml` made to raise, every surface refuses and stderr names the package. (BR-9)
- [ ] A document with two `delegate:` keys, or two `enabled` keys under one, is malformed. (BR-2)
- [ ] `forge_config.py` reads its section through `load_machine_config()`; a config with only `forge:` leaves delegation *unconfigured*, not locked out; a config with only `delegate:` leaves forge unconfigured. (BR-6, BR-8)
- [ ] With a shell function, an alias, and a hash-table entry each named `adlc-read` pointing at a planted binary, in bash, zsh, and `/bin/sh`, the gate returns `2 no-binary` when no real file is on an absolute `$PATH` entry, and the planted binary receives nothing. (BR-11)
- [ ] A binary named `timeout` planted on `$PATH` is not invoked; only a path from the fixed list is. (BR-11)
- [ ] With `ADLC_READ_BIN` empty, each of the six call-site fences exits non-zero before any transmission. (BR-12)
- [ ] A malformed config yields a refusal that names the path and does not advise setting `ADLC_DELEGATE_ENABLED=1`. (BR-13)
- [ ] REQ-515's architecture carries an ADR-3 amendment; this REQ's architecture records that it discharges REQ-603's known-limitation note. (BR-14)
- [ ] `grep -rn "bare name" partials/delegate-gate.sh partials/delegate-gate.md` matches only text that says it is rejected. (BR-15)
- [ ] The probe's cost is measured before and after and recorded in Assumptions; the PyYAML import is not paid by `--help`. (BR-1)
- [ ] Both readers survive a fifo swapped in after `stat` and before `open`, returning malformed within one second. (BR-5)
- [ ] `sh partials/tests/run.sh` passes under bash and zsh; the full Python suite passes; every new behaviour is mutation-proven in a scratch copy, with the mutation list in the commit. (BR-16)

## External Dependencies

- PyYAML `>=6.0`, pinned in `tools/delegate/requirements.txt`, installed by `install.sh`. Pure Python; the venv already pins `openai`.
- **REQ-603 as landed under the split plan**: its branch reset to `ee5ca91` plus the cherry-picked safe pieces and the two parser-independent tests. This REQ does not build on `bc7d584`; the parser rewrite there is discarded, and its reviewers' enumerated shapes become this REQ's seed corpus.
- REQ-603's frozen pre-REQ fixtures (`partials/tests/fixtures/`), which remain the parity baseline.

## Assumptions

- **REQ-603 lands first, per the split plan** — reset, cherry-picks, two tests, `/validate`, a human read of the three functions, then its PR. If that ordering changes, this REQ's base changes with it.
- **PyYAML is importable wherever the loader runs.** The delegate CLIs run in `~/.claude/delegate-venv`. Whether `tools/adlc` (`adlc doctor`, `forge_config`) runs in the same interpreter is **unverified** and decides whether BR-8 is a refactor or a new install step. Verify before `/architect`.
- **The import costs roughly thirty milliseconds.** Unmeasured. Against REQ-603's 104-second median delegated step it is noise if true; the AC records the measurement either way.
- **PyYAML 1.1 booleans are acceptable for `enabled`.** `yes`, `no`, `on`, `off` become bools. For this one field that is the intended semantics; the schema refuses strings, so the Norway problem cannot reach an opt-in.
- **id allocated with remote verification** (`ADLC_ALLOC_DEGRADED=0`).

## Open Questions

- [ ] Which interpreter runs `tools/adlc`? See the second assumption.
- [ ] Unknown keys under `delegate:` refuse (BR-7). A newer config on an older toolkit then locks out. Is a `version:` key under `delegate:` wanted now, or deferred until a second key is ever added?

## Out of Scope

- **The three residuals assigned to REQ-603 by the split plan**: the regenerated hash pin, the `_MALFORMED` arm's ordering test, and malformed-config rows in the parity matrix. They do not depend on the parser and land with REQ-603.
- **Migrating the config format** to TOML or JSON. `tomllib` is 3.11+; this repo runs 3.9. JSON has no comments.
- **Bounding a read that blocks on a hung network mount.** `O_NONBLOCK` does not help a regular file on a stalled FUSE or NFS mount; that needs an in-process alarm and is its own change.
- **Schemas for the other sections** (`forge:`, `agents:`). BR-8 gives them one loader; their validation stays where it is.
- **The reason vocabulary.** `disabled-via-config` keeps covering the key-unset case; a distinct reason is a vocabulary change REQ-603 BR-4 forbids.
- **REQ-603's ratified divergences D1–D5.** Preserved as-is.

## Retrieved Context

- BUG-209 (bug, score 17): `ADLC_DISABLE_DELEGATE=1` is inert in the delegate CLIs — the emergency stop lived only in the vendored gate
- REQ-603 (spec, score 15): Single-source the delegation authorization arms — the gate may veto, only Python may authorize
- BUG-206 (bug, score 13): The delegate CLIs never enforce `enabled` themselves
- BUG-205 (bug, score 13): A legacy key silently overrides an explicit `delegate.enabled: false`
- LESSON-008 (lesson, score 10): Delegated output is untrusted data — sanitise, safe tempfiles, redact
- BUG-208 (bug, score 9): The shipped default model was retired; the 404 surfaced as a raw traceback
- REQ-553 (spec, score 8): `--version` on the delegation CLIs must use the real call's resolver
- REQ-426 (spec, score 8): install.sh integrity, reason-string DRY, partials drift detection
- REQ-415 (spec, score 8): Path-traversal regex, credential redaction, launchctl env inheritance
- LESSON-392 (lesson, score 7): An "is it enabled?" probe must run the real call's resolution path
- REQ-522 (spec, score 7): De-brand the delegation surface; single-fence-safe telemetry
- LESSON-010 (lesson, score 7): Delegated bulk reads silently truncate; reconcile coverage
- REQ-414 (spec, score 7): Pilot delegation with mandatory fallback gates and post-hoc validation
- LESSON-603 (lesson, score 6): A spec naming a field states a belief; verify against what emits it
- REQ-436 (spec, score 6): Telemetry helper as a sourceable POSIX partial; no cross-fence shell state
