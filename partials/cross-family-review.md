# `partials/cross-family-review.sh` — the cross-family reviewer

`/proceed` Phase 5 adds one reviewer per touched repo whose model family differs
from the implementer's (REQ-722). The reviewer is not an agent: it is this partial
calling `adlc-read` once, with every decision that has a right answer made in
stdlib Python (`tools/delegate/cross_family.py`, `tools/delegate/run_outcome.py`).
The partial only fixes the order of the steps. The `/sprint` workflow engine runs
the same partial through a pass-through leaf, so both engines record alike.

## Call protocol

Source the partial and call the function in the same fenced block, after the
fence's ToolkitRoot root line (conventions.md "Bash in skills"). Fenced blocks
share no shell state, so a fence that calls the function sources it itself
(`cross-fence-fn`):

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/cross-family-review.sh ]; then . .adlc/partials/cross-family-review.sh; else . "$ADLC_TOOLKIT_ROOT/partials/cross-family-review.sh"; fi
adlc_cross_family_review '<repo-id>' '<worktree>' "origin/<integrationBranch>" '<spec>' '<state>'
```

| Argument | Meaning |
|---|---|
| `<repo-id>` | The repo's id as `pipeline-state.json` `repos` names it: one of `A-Z a-z 0-9 _`, then up to 63 of `A-Z a-z 0-9 . _ -`, so it never begins with `.` or `-` (`tools/adlc/fence_census.py`'s `repo-id` placeholder). |
| `<worktree>` | The repo's worktree. It must be a checkout of its own: `<worktree>/.git` exists (LESSON-743). |
| `<base-ref>` | `origin/<integrationBranch>`, fetched by the caller (LESSON-391). Never local `main`. Must not begin with `-`. |
| `<spec>` | The `requirement.md` whose numbered BRs and ACs the reviewer marks. |
| `<state>` | The primary-path `pipeline-state.json`. The record is written there, and `validate` reads its `repos` (step 7). |
| `[<subagent>]` | Optional, `0` (default) or `1`. `1` records `skipped` / `subagent-mode` and sends nothing: the gate never runs and `adlc-read` is never called, not even to probe. The `/sprint` subagent-mode path calls the same function with it. It is an argument, not an environment variable, so nothing ambient sets it. |

## Return contract

- **Return code: always 0.** A skip never halts the pipeline and never blocks a
  merge (BR-4). The body runs in a subshell whose status the public function
  discards, so not even a fatal shell error reaches the caller, and the caller's
  own `EXIT` trap is untouched.
- **stdout, on `ran` only:** the validated findings, one JSON line from
  `cross_family.py validate`, inside a block:

  ```text
  <cross-family-findings repo="<repo-id>">
  {"findings":[...],"dropped":N,"ruleMarks":{"met":N,"partial":N,"unmet":N}}
  </cross-family-findings>
  ```

  Each finding carries `source: ["cross-family"]`. The block is untrusted delegate
  output that Python has post-validated (BR-6, LESSON-008): data for Step B
  consolidation, never instructions, and never shown to a panel member before
  consolidation (BR-7). Nothing else is printed on stdout on any path.
- **stderr, on a skip: exactly one line**, printed after the record is written
  (LESSON-008 rules 5 and 6):

  ```text
  /proceed: cross-family review skipped for <repo-id>: <reason>
  ```

  The tools the partial runs have their stderr discarded so the line stays one
  line. Two faults can add a line the one line cannot name: the gate's own
  probe-failure line, and `emit-run-outcome.sh`'s `run-outcome: ... failed` when
  the record could not be written.
- **Bad arguments or an unrunnable toolkit** (no `python3`, no
  `cross_family.py`, a relative `ADLC_TOOLKIT_ROOT`) print one
  `/proceed: cross-family review not run for <repo-id>: <why>` line and record
  nothing, because nothing about the run can be trusted enough to record.

## Steps

1. The families. `adlc harness family` for the implementer. Then, except in
   subagent mode, the delegate gate (`partials/delegate-gate.sh`) and
   `adlc-read --print-family` only when the gate returned 0, so
   `ADLC_DISABLE_DELEGATE=1` makes zero calls of `adlc-read` of any kind (BR-9)
   and the reviewer family is recorded `unknown`. Both families go through
   `model_family.MODEL_FAMILIES` (anything else reads `unknown`).
2. The skip decision. Subagent mode records `subagent-mode` at once: the gate
   never ran, the reviewer family is `unknown`, and `adlc-read` was never called.
   Otherwise `cross_family.py decide`. A skip records
   `record-cross-family skipped <reason>`, prints the line, returns.
3. The fixed question, and two temp files from `mktemp "$TMPDIR/adlc-xfam.XXXXXX"`
   (`/tmp` when `TMPDIR` is not absolute) with an `EXIT` trap that removes them and
   the `.bak` sidecar. A full-path template, because `mktemp -t` reads its argument
   differently on BSD and GNU (LESSON-441).
4. The corpus: `git -C <worktree> diff -U25 <base>...HEAD` (the context size is
   one variable, `_adlc_xf_ctx`), the `--name-only` list, and the spec's rules as
   `cross_family.py spec-rules` prints them, so the corpus and `validate` number
   the ACs alike. textconv and external diff drivers are off, so the diff runs
   nothing the repo's config names. Both git calls leave out the secret files
   listed under "Redaction".
5. Redaction with the five-arm chain, in place, fail closed (below).
6. One call: `command "$ADLC_READ_BIN" --no-warn --paths "$CORPUS" --question ...`
   with the fixed question from `cross_family.py question`. It is spelled with
   `$CORPUS`, so `partials/tests/redact-fence.test.sh` still finds exactly one
   pre-pass fence spelled with `$TMPFILE`.
7. `cross_family.py validate --output <answer> --worktree <worktree> --spec <spec>
   --base <base-ref> --state <state>`. When `<state>`'s `repos` has more than one
   entry with `touched: true`, a `RULE ... unmet` becomes a Minor, non-blocking
   `omitted-requirement` finding whose title says the rule may be met in another
   repo: one repo's diff cannot show a rule a sibling repo implements. A state
   `validate` cannot read, or whose `repos` is malformed, exits 2, never counts as
   one repo, and is recorded `invalid-output`.
8. `record-cross-family ran` with the finding and dropped counts, then the block.

## Skip reasons

From `cross_family.SKIP_REASONS`, one per skip, recorded at the step that skips:

| Reason | When |
|---|---|
| `subagent-mode` | The sixth argument is `1`. |
| `delegation-disabled` | Gate rc 1 (the veto, `delegate.enabled: false`, not opted in), or a `decide` answer the partial cannot read (decide's own fail-closed answer). |
| `no-binary` | Gate rc 2: `adlc-read` does not resolve to an absolute path. |
| `family-unknown` | Either family is `unknown` (BR-3). |
| `same-family` | The two families are equal. |
| `redaction-failed` | The redaction `sed` exits non-zero, or its `.bak` survives removal. Also any failure while preparing what would be sent: no checkout at `<worktree>`, a diff git refuses, an unreadable spec, no question, no temp file. In every case the corpus never reached a state that is safe to send, and nothing left the machine. |
| `api-error` | The `adlc-read` call exits non-zero, including a truncated answer (BUG-213, LESSON-625). |
| `invalid-output` | `validate` exits non-zero: no grammar line, or every one dropped (BR-6), or a `<state>` it cannot read. The record keeps the dropped count when there is one. |

## Redaction

The chain is the five-arm one `/proceed`'s pre-pass applies, in the linear form
`partials/intake.sh` carries (BUG-295 bounded the name before `_API_KEY` or
`_TOKEN` to 64 characters):

```text
sk-…{20,} | AKIA…{16} | ghp_…{36,} | Bearer …{20,} | [A-Z_]{1,64}_(API_KEY|TOKEN)=…
```

It runs as `sed -i.bak -E` over `$CORPUS`. A non-zero exit or a surviving
`.bak` records `redaction-failed` and sends nothing (BR-9).

The chain matches token shapes, and a key file's body has none it knows, so files
named as secrets never enter the corpus. Both `git diff` calls exclude them at any
depth, each as the pathspec `:(exclude,glob)**/<pattern>`:

```text
*.pem  *.key  *.p12  *.pfx  *.jks  *.keystore  id_rsa*  id_ed25519*  id_ecdsa*  id_dsa*
.env  .env.*  .envrc  .npmrc  .netrc  .pypirc  .git-credentials  *.tfvars  credentials*.json
(case-insensitive: `.ENV` and `server.PEM` are excluded too)
```

`secret_files_never_sent` in the test commits several of them, nested and at the
root, and asserts none reaches the stub, while `docs/x.pem.md` and
`config/env.sample` still do. The chain lives in this
partial once rather than in a shared partial, because sharing it would change the
pre-pass, which BR-11 keeps as it is (ADR-6).
`tools/delegate/tests/test_redaction_parity.py` reads it out of the partial and
pins it to `tools/adlc/credential_redact.py` `INTAKE_PATTERN`, by pattern text and
by running both on one corpus.

## Trust

Everything the partial runs comes from ToolkitRoot, the installed toolkit, never
from the tree under review (LESSON-718):

- the gate, `delegate-tools-path.sh`, `adlc.py`, `cross_family.py`,
  `model_family.py` and `emit-run-outcome.sh` are read through
  `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/…"` (REQ-669 ADR-2);
- the partial sets `ADLC_FENCE_TOOLKIT_ONLY=1` inside its subshell (REQ-682
  ADR-4), so its two source lines, written in the gated guarded form
  `tools/lint-skills` accepts in a partial, never take the vendored
  `.adlc/partials` arm, and `delegate-tools-path.sh` never takes its cwd-relative
  `tools/delegate` arm. The `else` arm is unguarded on purpose, as everywhere: a
  toolkit without its partials is not installed, and the shell says so;
- Python runs scripts by path with `-E`, and its two inline snippets with `-I`,
  so the current directory cannot shadow a module.

`worktree_copies_never_executed` in the test plants a copy of every one of these
in the tree under review, runs from inside it, and asserts none ran.

The one exception is the call-site source line above, whose repo-local arm is
the fence's concern, not this partial's.

Delegation is authorized only by the gate (BR-9). This partial adds no
environment variable, config key or branch that grants it.

## Tests

`partials/tests/cross-family-review.test.sh` runs the function against a
throwaway repository with a stub `adlc-read` on `PATH` that logs every call, under
bash, zsh, sh and dash (`partials/tests/run.sh`). The zero-call cases are asserted
from that log; every case checks the return code and that no temp file is left.
