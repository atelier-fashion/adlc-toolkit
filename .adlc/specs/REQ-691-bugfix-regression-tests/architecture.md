# REQ-691 — Architecture

## Approach

One stdlib engine, `tools/adlc/regression_check.py`, owns every deterministic decision: reading the project setting, reading bug frontmatter strictly, and classifying bugs. People and CI reach it as `adlc regression-check`. Skill fences reach it through a wrapper partial, `partials/regression-check.sh`, on the `partials/lane-check.sh` pattern. `/bugfix` keeps only the protocol, meaning what to write, in what order, and what to record. That protocol lives in a read-and-follow companion, `bugfix/references/regression-test.md`, behind one-line pointers in the phases it hooks into.

```
.adlc/config.yml ──┐                       ┌── adlc regression-check  (operator, CI)
.adlc/bugs/*.md ───┼── regression_check.py ┤
git index ─────────┘   (stdlib only)       └── partials/regression-check.sh ── bugfix/SKILL.md
                                                                               bugfix/references/regression-test.md
```

## Data model changes

No new artifact kind and no new `.adlc/` file. The changes are additive:

- **Bug frontmatter**: `regression_tests` (flow list of strings) and `regression_waiver` (double-quoted string). `templates/bug-template.md` documents both, and adds a `## Regression Test` body section. Flow form is required. The dataset's strict recognizer (`tools/dataset/frontmatter.py`) drops a bug report whose list is in block form, and `lessons.py` silently loses the items. The waiver is always double-quoted, because both readers cut a plain value at ` #`.
- **Project config**: a top-level `bugfix:` mapping with one key, `regression_test`. `templates/config-template.yml` carries it uncommented as `required`.

## Engine: `tools/adlc/regression_check.py`

Two verbs, one output contract.

| Verb | Prints (first stdout line) | rc |
|---|---|---|
| `mode [--root DIR]` | `regression-test: required` or `regression-test: off` | 0; 2 on an unreadable setting or bad value |
| `check [--root DIR] [--require-recorded] [BUG-nnn ...]` | `regression-check: pass` / `fail` / `off` / `error`, then a counts line `passed=N waived=N legacy=N failed=N`, then one `BUG-nnn: <reason>` line per failure | 0 pass or off; 1 fail; 2 error |

- With no ids, `check` reads every `.adlc/bugs/BUG-*.md` whose status is `resolved` or `closed` (BR-9). With ids, it reads exactly those, whatever their status. An id with no file is a failure (BR-9, AC-15).
- `--require-recorded` turns `legacy` into `failed`. `/bugfix` Phase 6 passes it (BR-13). An operator or CI run does not, so history never fails (BR-9, AC-11).
- `off` short-circuits before any bug report is opened (BR-11).
- The wrapper replaces a missing or unknown first line with `error`, rc 2, as `lane-check.sh` does.

## Key decisions

### ADR-691-A: Read the setting with the stdlib YAML subset, behind a byte prefilter

**Decision.** `mode` first scans the raw bytes: no `regression_test` outside a whole-line comment means `off`, with no parse (the `lane_check.may_carry_lanes` technique). A config that names the key is parsed with `tools/adlc/harness_yaml.loads`, the toolkit's stdlib closed-subset loader. `bugfix` must be a mapping whose only key is `regression_test`, with a value of `required` or `off`. Anything else is rc 2: a `YamlError`, a non-mapping, an unknown key, a wrong value. A missing config file is `off` (BR-1).

**Why.** The template sets the key uncommented (BR-15), so every config copied from it names the key. A PyYAML loader would then make `/bugfix` stop on every plugin install without the delegate venv. BR-17 forbids reading that as `off`, so the stop would be real. The shared PyYAML loader's other consumers, `forge_config.py` and `lane_check.py`, either carve out a missing dependency or need the venv. Neither fits a check that must give the same answer on every machine. `harness_yaml` needs nothing installed and refuses what it does not understand. On 2026-11-04 it parsed both `templates/config-template.yml` and the Embolden platform's real `.adlc/config.yml` cleanly.

**Cost, accepted.** A config using a construct outside the subset (tabs, anchors, `>` folding) can parse under PyYAML and be refused here. The refusal is loud and names the subset, and only a project that has named the key can hit it. This is the safe direction: a stop, never a silent `off`.

### ADR-691-B: A strict frontmatter reader of the engine's own

**Decision.** The engine reads bug frontmatter with its own fail-closed one-line reader, modelled on `partials/lesson-check.sh`. A value continued onto the next line (block list), a key given twice, an unclosed quote, or a flow list not closed on its line makes that bug `failed`, naming the field. A waiver is stripped before it is judged empty (BR-6).

**Why not `lessons.py`.** Its reader is lenient on purpose: last duplicate wins, block-list lines vanish, a quoted all-blank value is kept. Each of those would turn a malformed report into `legacy`, a silent pass. BR-9's wrong-type rule needs the strict semantics.

### ADR-691-C: Judge the working tree and the index, never a ref

**Decision.** A listed path passes when it is repo-relative (no leading `/`, no `..` segment), resolves inside its repo, is not a symlink, is tracked (`git -C <repo> ls-files --error-unmatch -- <path>`), and its working-tree bytes contain the id. The id is matched as `BUG-<n>` not followed by a digit, so BUG-26 never matches BUG-261. No fetch, no remote ref, no diff (BR-12, LESSON-782).

**Why not `lane_check.read_base_config`.** It reads the integration branch's copy on purpose, so a branch cannot loosen its own lane. Here the question is "does this tree still carry its tests", which only the tree can answer. The path rules are the toolkit's usual refusal of a cited path as untrusted input (LESSON-008).

### ADR-691-D: Cross-repo paths are prefixed, and resolved through `repos:`

**Decision.** An entry `<repo-id>:<path>` resolves through `repos.<repo-id>.path`, relative to the primary root, read with the same subset loader. The primary's own id, and an unprefixed path, mean this repo. A prefix naming no declared repo, or a sibling not cloned at its path, is a failure naming it (BR-14, AC-10).

### ADR-691-E: Test first, so the contrast needs no revert

**Decision.** The companion orders Phase 3 as: write the regression test, run it against the unfixed tree and record the failure, then write the fix, run it again and record the pass. When the test needs a seam the code lacks, the seam lands first as a behavior-preserving change, and the test is written against it before the fix. A test that passes before the fix is rewritten or waived; it is never recorded (BR-3, AC-4).

**Why.** "The tree with the fix's non-test changes absent" (BR-3) is then simply the tree before the fix was written. Reverting files after the fact needs a stash or a patch round-trip in a shared checkout, which the toolkit avoids. The remaining load-error case (the spec's assumption) shrinks to a test that imports something only the fix adds. The companion tells the model to record that as a load failure and flag it in the PR body.

### ADR-691-F: The gate runs in the fix worktree, before the merge

**Decision.** Phase 6 gains a step before Step 1's merge: run `adlc_regression_check check --require-recorded BUG-nnn` in the fix worktree. Anything but rc 0 stops `/bugfix` before the merge, with the engine's failure lines. BR-13 is met because `resolved` (Step 3) comes after the merge.

**Why there.** The worktree holds exactly the tree that will land, with the tests tracked, and nothing has been merged yet. After the merge, the integration checkout only has the tests after a pull, and a failure there would leave a merged fix with an unresolvable bug.

### ADR-691-G: The protocol goes in a companion

**Decision.** `bugfix/references/regression-test.md` holds the protocol in sections named for its call sites: Mode (Prerequisites), Write and contrast (Phase 3), Record (Phase 4), PR body (Phase 5) and Gate (Phase 6). Each site in `bugfix/SKILL.md` gets one sentence: "Read the `<section>` section of `bugfix/references/regression-test.md` and follow it before you continue." Off mode is one line at each site: "Skip it when the mode is `off`." The BR-16 sentence goes beside the existing "A reproduce-then-fix sequence is a contrast" line, outside the capture-rules block, so `/wrapup`'s copy stays byte-equal.

**Why.** `bugfix/SKILL.md` is already over the 24,000-byte cap at which Antigravity cuts a skill body. Its Phase 6 is in the part that gets cut, and the 500-line budget leaves 153 lines. A companion is read with a file tool, so it is never cut, and the SKILL.md growth stays to a few pointer lines. No fence in the companion consumes the skill argument, so `companion-templating` allows it.

### ADR-691-H: Every fence re-reads the mode

**Decision.** Each companion fence that branches on the mode calls `adlc_regression_check mode` itself, after the root line and the guarded source. No fence reads a value another fence set (`cross-fence-var`).

## Not changed, on purpose

- `wrapup/SKILL.md`: its capture-rules block must stay byte-equal with `/bugfix`'s.
- `templates/permissions.yml`: the new fences have the same shape as the existing `lane-check.sh` fences. Pre-approving partial-sourcing fences is REQ-682's subject, not this one.
- `presets/ios-firebase-cloudrun.yml`: a preset-copied config has no key and is `off`, like every existing config.
- `/status`: it ignores unknown bug keys, and its attribution reader greps `^introduced_by:` only.

## Lessons applied

- LESSON-603: field names and shapes are checked against the readers that exist (`frontmatter.py`, `lessons.py`), not assumed. Hence flow lists and quoted waivers.
- LESSON-742, LESSON-752: the readers of `bugfix/SKILL.md` by path were inventoried (lint `lesson-check-order` and rules parity, `test_lessons_contract.py`'s Phase 2 slice, `lesson-check.test.sh`'s Step 6 slice). The final tree runs the full `partials/tests/run.sh` and lint, not only the new tests.
- LESSON-782: no committed test compares against `origin/main`. AC-9 builds its two branches in a temp repo.
- LESSON-754: the partial test asserts on the verdict lines produced, never on exit status alone.
- LESSON-023: the wrapper mirrors `lane-check.sh` line by line, with its rationale comments (relative-root refusal, engine-not-in-worktree refusal, verdict-line check).

## Proposed addition to `.adlc/context/architecture.md`

A cross-cutting bullet, **Regression tests (REQ-691)**, summarising the engine, the two verbs, the stdlib-subset config read and why, the `--require-recorded` gate in the fix worktree, and the `off` default for an absent key. Also, the bug-template row in "Template anatomy" gains the two optional fields. TASK-242 writes both.

## Amendments from the verify pass (Phase 5)

The review panel found that the gate as first designed could be loosened by the branch it judges (LESSON-718), and the re-verification found the first amendment's guards could be got past as well. These amend the ADRs above. BR-12 in the spec is amended to match: the setting and `repos:` are read at the integration branch, and `--require-recorded` reads each repo's `HEAD`; bug reports stay worktree-and-index reads.

- **ADR-691-C, amended.** The *setting* and `repos:` are policy, so the Gate reads them from the integration branch (`check --base refs/remotes/origin/<integration-branch>`, read with `ls-tree`/`cat-file` as `lane_check.read_base_config` does). `--base` takes only a full ref under `refs/remotes/` or `refs/heads/`, resolved exactly with `git show-ref --verify`: git resolves a short `origin/main` to a tag of that name before the remote-tracking branch, and plain `rev-parse` falls through from a missing `refs/remotes/origin/main` to `refs/tags/refs/remotes/origin/main`. `HEAD`, `FETCH_HEAD`, `ORIG_HEAD` and a bare sha are usage errors. Bug reports and test files stay worktree-and-index reads (BR-12). Under `--require-recorded` each listed test must also be committed in its repo's `HEAD`, and that copy must cite the id, so a sibling's staged-only test, which the primary's clean-tree guard cannot see, fails.
- **ADR-691-F, amended three times.** One principle: the Gate runs only installed-toolkit code and reads policy only from the integration branch, as a full remote ref; the fix tree supplies data (the bug report and its tests), never code or policy. The fence validates `<bug-id>`, both branch names and `<pr-number>`, and refuses an integration branch equal to the fix branch; `<integration-branch>` is the one `/bugfix` resolved in the primary checkout, never re-read from the fix checkout's config. It sources `adlc-home.sh`, `forge.sh` and `regression-check.sh` from `$ADLC_TOOLKIT_ROOT` through variables behind `[ -f ]` tests, and nothing under `.adlc/partials`. It resolves the forge provider with the installed `forge_config.py`, so the adapter never runs one from the tree, and requires the PR's base to be the integration branch. It fetches the integration branch by explicit refspec with `--no-tags` and no hooks, then reads the mode at `refs/remotes/origin/<integration-branch>`, at the project's own path in the repo, before any guard and before the forge is asked anything; a base with no config is `off` from `git cat-file`, without Python. `off` continues with no guard (BR-1): only a failed fetch can stop it, and Step 1's merge needs `origin` anyway. Only `required` resolves the provider, requires the PR's base to be the integration branch and its head branch the fix branch, fetches the fix branch, checks a clean tree (`git status` with `core.fsmonitor=false`), `HEAD` equal to `refs/remotes/origin/<fix-branch>` and the PR's head commit equal to `HEAD`, then runs `check --require-recorded --base`. A pass prints `regression_gate_head=<oid>`, and Phase 6 Step 1 merges with `--match-head-commit <oid>` (on a forge that cannot pin, it re-reads the PR's head first), so only the certified head merges; a rebase sends Step 1 back to Step 0. Under `--require-recorded` the bug report must equal its committed copy at `HEAD` and each listed test must be committed as a regular file, because `git status` says nothing about a `skip-worktree` or `assume-unchanged` entry. The guarantee holds against the branch's content; code the branch already ran as the operator (its tests in the contrast runs, or a skill sourcing a vendored partial) could have edited the installed toolkit or `.git/config` before the Gate, and only a run from a fresh clone, or in CI, rules that out. The first amendment's checkout-root guard and its diff of `.adlc/partials` and `.adlc/tools` are gone: a symlinked `.adlc`, an ignored file and a `skip-worktree` entry each put code past the diff, and code that never comes from the tree needs no such guard. A pass certifies the head it checked; a rebase in Step 1 means running it again.
- **ADR-691-D, amended.** A relative `repos.<id>.path` resolves from the primary's main checkout (the git common dir's parent), so it means the same thing from a linked fix worktree. Since `repos:` is read at the base, the path is the integration branch's: a sibling's fix branch must be checked out in the clone there, committed and pushed, and an absolute path on the fix branch cannot redirect it.
- **Wrapper.** The install-clone exemption is for `mode` only; containment is also compared case-folded; a `--root` with a `..` segment is judged lexically, as the engine reads it, and never gets the no-config answer; `forge.sh` comes from the installed toolkit only, never `.adlc/partials/forge.sh` from the current directory; a run without `--base` on a project with no config file gets `off` from the wrapper without Python.
- **ADR-691-A, amended.** A config the subset loader refuses is an error only when it could define the setting (a key-shaped `regression_test` or `bugfix`); any `bugfix:` block is always parsed and validated.
- **ADR-691-B, amended.** A waiver must be quoted; a plain value is the wrong type. Indented lines under an open parent block are not misspellings.
