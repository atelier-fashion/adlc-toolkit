# Architecture — REQ-609: a real config parser behind a strict schema, and shell resolution that never consults shell state

## Approach

Two independent hardenings, one per layer, joined by the invariant REQ-603 established: **the shell may withhold, only Python may grant**.

**Python.** A new module, `tools/delegate/_machine_config.py`, owns the one loader. It opens the file by descriptor, decides the file kind on `fstat` of what it opened, reads under a cap, parses with `yaml.safe_load` through a loader that refuses repeated keys, and returns a three-state outcome — `absent`, `parsed`, `malformed` — that never raises. `_common.parse_delegate_config` becomes a thin adapter: it asks the loader for the document, validates the `delegate` section against the strict schema, and keeps its existing return convention (`{}` / `{_MALFORMED: True, ...}`) so the cascade in `delegation_enabled()` and the labeller in `resolve_gate_verdict()` do not change. `tools/adlc/forge_config.py` reads its section from the same loader and retires its own flat reader. A differential oracle test compares the adapter against a second, independent implementation over a seeded and a generated corpus.

**Shell.** `partials/delegate-gate.sh`'s resolver walks `$PATH` itself — absolute entries only, `-f` and `-x` on `dir/adlc-read` — and never calls `command -v`. The `timeout` wrapper resolves from a fixed absolute list. Every call-site fence stops falling back to the bare name; an empty `ADLC_READ_BIN` is a refusal, and a `tools/lint-skills` check makes that structural so it cannot rot back.

Everything the spec names as a fail-open on `main` is closed by construction rather than by enumeration: a recognizer that refuses what it does not understand has no "skipped line" to fail open on.

## Data model changes

None outside the process. The config file's *schema* is now enforced (see the REQ's System Model). No new files or persistent state.

## Key decisions

### ADR-1: One loader module in `tools/delegate/`, adapters in both consumers

**Decision.** `load_machine_config(path=None) -> ConfigOutcome` lives in `tools/delegate/_machine_config.py`. `_common.py` imports it directly; `tools/adlc/forge_config.py` imports it by inserting `<repo>/tools/delegate` onto `sys.path` relative to its own file, which is how `tools/adlc/checks.py` already reaches `_common` for its probes and what ASSUME-001 (wrapper `exec` preserves script-relative resolution) relies on.

**Why here and not a third directory.** `tools/delegate/` is where the governance reader lives today, where the venv and `requirements.txt` that pin PyYAML live, and where every test of the reader lives. A `tools/_shared/` would be a new install surface for one module. The `adlc` umbrella already reaches into `tools/delegate` for its delegation checks.

**Outcome shape.** `ConfigOutcome(kind, document, reason, path)`. `kind ∈ {absent, parsed, malformed}`. `document` is the top-level mapping — `{}` for a null document (empty file, comments only) per REQ BR-3. `reason` is a short class string for `malformed` (`not-regular-file`, `dangling-symlink`, `unreadable`, `undecodable`, `over-cap`, `yaml-error`, `duplicate-key`, `not-a-mapping`, `dependency-missing`) plus a human line that may carry a line number, never file content. `parse_delegate_config` maps `malformed` to `{_MALFORMED: True, _MALFORMED_REASON: <reason>, _MALFORMED_PATH: <path>}` so `require_delegation_enabled` can name both (BR-13) while every existing `cfg.get(_MALFORMED) is True` check keeps working.

**Duplicate keys.** A `yaml.SafeLoader` subclass overrides `construct_mapping`: it flattens merges, constructs each key, and raises `ConstructorError` with the second occurrence's mark on a repeat. That is the standard recipe; the mark gives BR-13 its line number. The check is whole-document by design (REQ BR-2).

**Reader.** `os.open(path, O_RDONLY | O_NONBLOCK)` → `os.fstat` → `S_ISREG` or malformed → read through `os.fdopen(fd, "rb")` up to `CAP + 1` bytes → over cap is malformed → strict UTF-8 decode with a single leading BOM stripped. `ENOENT`/`ENOTDIR` on open is `absent` **only if** `os.path.lexists` is false; otherwise it is a dangling symlink and malformed. Any other `OSError`, `ValueError` (NUL in path), `UnicodeDecodeError`, or `yaml.YAMLError` is malformed. The same `_open_regular()` helper backs the rc-file key reader (BR-5), which keeps `errors="replace"` for its decode because a shell rc file is not a governance document and BR-5 mandates only the open pattern.

**Lazy import.** `import yaml` happens inside `load_machine_config`, mirroring the `openai` import inside `get_client()` (LESSON-022 / BUG-056). `ImportError` yields `malformed` with reason `dependency-missing` and one stderr line naming PyYAML (BR-9). `--help` never reaches the loader; a test proves it with a poisoned `yaml` module on `PYTHONPATH`.

**Schema.** `validate_delegate_section(document)`: section absent → `{}` (BR-6). Present → must be a mapping; keys ⊆ `{enabled, model, base_url, api_key_env}`; `enabled` must be `bool` (a `str` `"false"` is refused, BR-7); the three strings must be `str`; any nested mapping or sequence is refused. The allowed-key set is one module constant, and a structural test asserts it equals the keys `tools/delegate/README.md` documents (LESSON-331: a closed schema rots unless a pure structural test pins it to the doc that describes it).

### ADR-2: One managed interpreter where the venv exists; a named carve-out where it does not

**Decision.** The root `install.sh`'s `adlc` shim prefers `~/.claude/delegate-venv/bin/python3` when that file exists and is executable, and falls back to `python3` from `$PATH` otherwise. `tools/adlc/checks.py`'s two config probes select their interpreter the same way. `adlc doctor` gains a `pyyaml` check that reports whether PyYAML imports in the interpreter `adlc` itself runs under, with the copy-pasteable fix (`install.sh --with-delegation`, or `python3 -m pip install --user 'pyyaml>=6.0'`).

**Why not point the shim at the venv unconditionally.** The venv is created only by `--with-delegation` (root `install.sh` line ~206). A shim that `exec`s a missing interpreter breaks `adlc doctor` on exactly the machine that most needs it, and LESSON-395 says bootstrap diagnostics must be dependency-free. `checks.py` therefore imports nothing YAML-related at module level.

**The carve-out.** On a machine with no venv and no system PyYAML, the loader reports `malformed / dependency-missing`. The delegate consumer refuses (BR-9 — and there is no `adlc-read` on such a machine anyway). The forge consumer treats **that one reason** as *unconfigured* after emitting the same stderr line, and refuses on every other `malformed` reason exactly as the delegate does. Rationale: a missing parser is a statement about the machine's install, not about the file; making every `/proceed` PR operation hostage to an install the operator never opted into would be a regression with no governance benefit, because `forge.auth` never carries authority (a key-shaped value is refused at validation, REQ-520). Every file defect stays whole-document and fail-loud for both consumers (REQ BR-2, BR-8). REQ BR-8 is amended by one clause to say "where the venv exists".

### ADR-3: The resolver is a `$PATH` walk with no shell-state input, and call sites carry no second resolver

**Decision.** `_adlc_resolve_read_bin` iterates `$PATH` on `:` using parameter expansion (`${rest%%:*}` / `${rest#*:}`), so it is identical under `sh`, `bash`, and `zsh` with no word-splitting dependence (LESSON-329) and no globbing (LESSON-335). Entries not beginning with `/` are skipped; empty entries are skipped; the first `dir/adlc-read` that is a regular executable file wins; then `$HOME/bin/adlc-read`, only when `$HOME` begins with `/`. The result is always an absolute path or empty. The `timeout` wrapper is chosen from a fixed absolute list (`/usr/bin/timeout`, `/opt/homebrew/bin/timeout`, `/usr/local/bin/timeout`, `/opt/homebrew/bin/gtimeout`, `/usr/local/bin/gtimeout`) and never from `$PATH`. Both invocations go through `command`, so a zsh function defined under an absolute-path name cannot intercept either; the shell test proves it in all three shells.

**Why a walk and not `command -v` with a slash check.** REQ-603's fix rejected bare names, which closes functions and aliases, and the hash table still delivered an absolute path to a planted binary. Any answer sourced from the shell's lookup machinery inherits every table that machinery consults; a filesystem question has to be asked of the filesystem.

**Call sites.** The eight fences that wrote `"${ADLC_READ_BIN:-adlc-read}"` write `"$ADLC_READ_BIN"` and, in the same fence, refuse with a named stderr line when it is empty. A `tools/lint-skills` check (`read-bin-fallback`) rejects any fence containing `ADLC_READ_BIN:-`, the same structural posture as `forge-direct-gh` (LESSON-012). Vendored copies of the old gate in consumer repos still export the bare name on `$PATH` hits until `/init` re-vendors; the new fences then invoke a bare name and the shell resolves it — the pre-REQ-609 state, not a hard failure — and `/template-drift` reports the stale copy (LESSON-441).

### ADR-4: Parity is preserved by registration, not by freezing behaviour

**Decision.** `test_pre_req_gate_parity.py` keeps the frozen pre-REQ-603 fixtures as its baseline. Every behaviour change this REQ introduces on that fixture's corpus is registered as a named divergence `D6…` with `REQ-609` as its source, next to D1–D5, and the malformed-class rows that REQ-603 recorded as *both grant* are flipped to the new outcome with the same registration. The 24-row well-formed matrix is expected to show zero new divergence; a diff there is a finding.

### ADR-5: The oracle is a second implementation, and the corpus is two corpora

**Decision.** The differential test computes its expected value from `yaml.safe_load(text)` directly — not from our loader — and independently detects repeated keys by walking `yaml.compose(text)`'s mapping nodes, so a text with duplicates is asserted as `malformed` rather than compared. The seeded corpus is the shape list in REQ AC-1, one entry per shape, in a corpus module the shell-side tests can also read. The generated corpus is a seeded product of {comment lines, indentation, key order, `enabled` spellings including `"false"`, `yes`, `on`, `1`, unknown keys, a nested mapping, CRLF} with a fixed seed and a few hundred documents. A disagreement is the finding (LESSON-602: an exclusion test needs a working subject; the oracle's working subject is PyYAML itself).

## Proposed additions to `.adlc/context/architecture.md`

Under "Delegation opt-in", one paragraph: the opt-in config is parsed by PyYAML behind a strict schema in `tools/delegate/_machine_config.py`, shared with `tools/adlc/forge_config.py`; the shell resolver asks the filesystem, never the shell; REQ-515 ADR-3's "no PyYAML" is amended by REQ-609. `conventions.md`'s delegation pattern loses the bare-name fallback and gains the `read-bin-fallback` lint mention.

## What this REQ discharges

REQ-603 BR-14 recorded the parser's fail-opens and the resolver's shell-state exposure as a known limitation pointing here. Both halves are closed by ADR-1 and ADR-3; TASK-099 writes the discharge note into REQ-603's spec and amends REQ-515 ADR-3.

## Task graph

```
Tier 1 (parallel):  TASK-094 loader + schema + adapters      TASK-097 shell resolver + timeout list
Tier 2 (parallel):  TASK-095 oracle + parity   TASK-096 forge/doctor/shim   TASK-098 fences + lint
                    (needs 094)                (needs 094)                  (needs 097)
Tier 3:             TASK-099 docs, ADR-3 amendment, discharge note, probe-cost measurement
                    (needs 095, 096, 098)
```

No task has more than three dependencies; no two tasks in a tier edit the same file.

## Lessons applied

LESSON-008 (untrusted paths, no `..`), LESSON-013 (no `\b` in BSD grep), LESSON-022/BUG-056 (lazy imports), LESSON-329/335 (zsh splitting and globs), LESSON-331 (closed schema pinned by a structural test), LESSON-392 (probe shares the real resolver — unchanged, the loader sits beneath it), LESSON-395 (doctor stays dependency-free), LESSON-441 (vendored partials shadow fixes), LESSON-478 (assert outcomes, not exit codes), LESSON-483 (a detected miss refuses, never guesses), LESSON-602 (oracle has a working subject), LESSON-006/017 (installers fail loud, validate before mutate).
