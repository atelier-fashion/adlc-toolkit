# harness/codex — the Codex CLI adapter (REQ-655, REQ-662)

`harness/codex.yml` is data, validated by `tools/adlc/harness_adapter.py` and rendered by
`tools/adlc/harness_render.py`. The install steps, the "What is lost" table and the
declared residuals are in the root `README.md`, where `tools/lint-skills`'
`harness-loss-table` holds them to this adapter. The evidence is in the REQ-655 spec's
Assumptions and in `.adlc/research/harness-probes/codex.json`.

| Surface | Where | How |
|---|---|---|
| agents | `$HOME/.codex/agents/<name>.toml` | rendered TOML roles, user-level only: `adlc harness install --harness codex` or `adlc agents render --harness codex`. `.codex/agents/` is never written |
| permissions | `.codex/rules/adlc.rules` (project), `$HOME/.codex/rules/adlc.rules` (user) | `allow` for the routine tier, `prompt` for the deny tier; the user file holds the three delegation rules and is written only with delegation installed |
| hooks | `.codex/hooks.json` (project) | `SessionStart` carries `ethos-inject` and `session-record`, `SubagentStart` carries `ethos-inject`. Inert until a person reviews them |
| config | `.codex/config.toml` (project), `$HOME/.codex/config.toml` (user) | merged; the project file owns `sandbox_mode` and `approval_policy`, and the user file's one owned key is written only by `--writable-root` |
| instructions | `AGENTS.md`, `$HOME/.codex/AGENTS.md` | the project file is the canonical one; the user file takes the delegation routing block |
| skills | `$HOME/.agents/skills` | mounted by `install.sh` (REQ-654); nothing here |

`rendered/` holds the goldens `render-parity` compares: `adlc.rules`, `hooks.json`,
`config.toml`, and `agents.json`, which records which agents carry the restraint sentence
in place of a `tools:` line. `adlc harness render --write-goldens` rewrites them.

## The exec block (REQ-662)

The `exec:` block is how `adlc sprint-exec run --harness codex` launches Codex headless. Its
facts are `codex-cli 0.166.0`: `codex.json` (run at `2026-11-17T23:49:29Z`), `codex exec
--help` and `codex exec resume --help`, and the real launches and resumes in
`.adlc/research/harness-probes/codex-exec-manual.md` (2026-11-18). What the engine does on
Codex, what is lost there and the declared residuals are in the root `README.md`, "Codex
CLI under `/sprint --exec`". The surfaces it writes:

| Surface | Where | How |
|---|---|---|
| exec rule file | `.codex/rules/adlc-exec.rules` (working copy) | rendered per run from `templates/permissions.yml`: `allow` for the routine tier and the fence runner's absolute path, `forbidden` for the deny tier and `engine_deny`. Never committed; checksummed before launch and resume, and again when the harness exits, where a change blocks the run |
| working-copy config | `.codex/` (working copy) | rendered whole for each launch and resume: the exec rule file and the project render of `config.toml`, and nothing else; `hooks.json` and `adlc.rules` are absent and a stray file is deleted |
| user policy file | `$HOME/.codex/rules/adlc-exec.rules` | the deny tier and `engine_deny` as `forbidden`, never an allow; written by `adlc harness install --exec --harness codex` or a run's pre-flight, beside the operator's own rule files, which exec never edits. It applies in every project and in the operator's own sessions |
| trust entry | `$HOME/.codex/config.toml` | one `[projects."<working copy>"]` block per run, appended before launch and removed when the harness exits (`tools/adlc/exec_trust.py`). The block is TOML, so the loader accepts `trust_grant: user-config-entry` only where `formats.config` is a format whose trust entry is known (`codex-config-toml`) |
| close-out state | `pipeline-state.json` (close-out working copy) | `codex exec resume` takes no extra directory, so the engine copies the primary checkout's state file in before the close-out resume and carries the session's changes back after it as data, never its `status`, `exec` or `approval`, nor `lessons`, `harness`, `validateAttempts` or `verify` where the primary copy already holds them |
| exec fence census | `exec-fence-census.json` (here) | every fence an exec model can meet and its route under `matcher: none`: no `direct` route, and the Step 0 branch push is a `runner` fence (REQ-662 ADR-9). `python3 tools/adlc/fence_census.py --check` holds it fresh |

`exec.status` and `exec.probes` are caches of `tools/adlc/exec_verify.py`'s verdict over
`codex.json`, which the engine recomputes at every launch: a cache that disagrees reads
`unverified`. When `adlc harness probe codex` records a new result, copy each row's `status`
and `ran_at` into `exec.probes`; a new binary version also changes `exec.harness_version`.
