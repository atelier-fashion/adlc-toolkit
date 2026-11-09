# Claude Code: the exec engine's manual runs (REQ-659)

Date 2026-10-31, `claude` 2.1.258 on darwin arm64. `claude auth status` read
`loggedIn: false`, so no run reached a model and none spent quota. Every row is a
logged-out `claude -p` in a throwaway repo with a local bare `origin`, two linked
worktrees and a throwaway `HOME`, launched with `env -i`. LESSON-759 is why this
is worth doing: a logged-out run still reads settings, fires hooks, starts MCP
servers and writes a transcript.

`tools/adlc/tests/e2e/claude-exec-manual.sh` reruns the table and prints one line
per row.

| Row | Run | Result |
|---|---|---|
| stdin-json | prompt on stdin, `--output-format json`, `--allowedTools A B --disallowedTools C` | exit 1; one JSON object on stdout with `type`, `session_id`, `is_error: true`, `num_turns`, `result`, `permission_denials`, `terminal_reason: api_error`, `total_cost_usd: 0`. The flags are accepted in that spelling |
| resume-same-cwd | `--resume <id>` from the first worktree | the same `session_id` |
| resume-sibling | `--resume <id>` from a second worktree of the repo | the same `session_id` |
| resume-unrelated | `--resume <id>` from a directory outside the repo | the same `session_id` |
| resume-control | `--resume` with a uuid that never ran | exit 1, stdout empty, stderr `No conversation found with session ID` |
| isolate | `--setting-sources user --settings <file> --strict-mcp-config` beside a planted `.claude/settings.json` hook and `.mcp.json` server | neither sentinel appeared |
| isolate-control | `--setting-sources project,local`, same tree | both sentinels appeared |
| default-launch | no `--setting-sources`, no trust entry | both sentinels appeared: hooks and `.mcp.json` servers run in an untrusted worktree |
| unknown-flag | `--no-such-flag` | exit 1, stderr `error: unknown option '--no-such-flag'` |
| trust-key-worktree | `projects["<worktree>"].hasTrustDialogAccepted: true` in the throwaway `.claude.json`, run from that worktree | still printed `Ignoring 2 permissions.allow entries from .claude/settings.json`, and the message names the **main repo root** as the key to set |
| trust-key-root | the same entry on the main repo root, run from the linked worktree | stderr empty |

## What these do not show

Nothing here exercises a tool call, so these stay owed to the first logged-in run:

- that `--allowedTools` applies in an untrusted workspace;
- that `--disallowedTools` beats a matching allow;
- whether a multi-statement fence matches any allow entry (`fence-vs-allowlist`);
- that a model's `permission_denials` reach the result as the engine reads them;
- a `--resume` that continues a real conversation, rather than finding its file.

`adlc harness probe claude` was not rerun: every probe that needs a model would read
`unknown` again while the CLI is logged out.

## The new forge ops against the real `gh`

Read-only, against this repo, with `gh` 2.103.3. `adlc_forge_pr_view 245 --fields
state,number,url,headRefName,headRefOid,baseRefName,isCrossRepository,files,mergeCommit`
returned every key, and showed a null `mergeCommit` printing as `None`, since fixed to empty.
`adlc_forge_pr_list --head <branch> --state all --json ...` returned the array the plan reads.
`adlc_forge_commit_prs <full sha of main>` returned `243`, and a short sha an `error_class`
block, not an empty answer. `adlc_forge_branch_protection main` returned `unprotected`, so a
real `--exec` run in this repo needs `--allow-unprotected`, or branch protection first.

## The engine against the real binary

One `adlc sprint-exec` launch with the real logged-out `claude` in place of the test harness, in
a throwaway repo with the mock forge. The binary took the whole 115-element argv, both tiers
included, with nothing on stderr, and exited 1. The engine read `Not logged in` from the JSON
result, kept the session id, classed the exit `error`, and ended the run `failed` with that line
in `notes`. So the launch path is proven as far as the first API call, and no further.

## Logged-in rows (2026-11-02)

`tools/adlc/tests/e2e/claude-exec-live.sh`, `claude` 2.1.258 logged in through claude.ai (Max), the
operator's real `HOME`, a throwaway repo with a local bare origin. Every launch uses the engine's own
argv from `exec_adapter.launch_argv`. The operator's `~/.claude/settings.json` allows 60 commands,
including `Bash(git push:*)` and `Bash(git add:*)`, and `claude -p` reads it, so the effective policy is
that list plus the engine's tiers.

| Row | Result | What it shows |
|---|---|---|
| `allow-untrusted` | pass | `git add` ran in a never-trusted folder (also allowed by the user's settings) |
| `allow-engine-only` | pass | `git config user.name`, allowed only by the engine's tier, ran: `--allowedTools` holds untrusted (ASSUME-020) |
| `outside-tier` | pass | `chmod` was denied under `-p`, not prompted: one denial, file unchanged (ASSUME-021b) |
| `deny-over-allow` | pass | an added deny matching the same command as an allow won: the remote did not move (ASSUME-021a) |
| `force-own-branch` | **ran**, then pass after BUG-260 | `git push -u origin <branch> --force` force-pushed the REQ's branch: the deny `git push --force:*` does not catch a flag after the refspec |
| `extra-refspec-main` | **ran**, then pass after BUG-260 | `git push -u origin <branch> main` pushed `main`: the allow `git push -u origin <branch>:*` admits a second refspec, so the model could update the integration branch without `/sprint approve` |
| `fence` | **fail** | the multi-statement partial-sourcing fence was denied: neither `Bash(ADLC_TOOLKIT_ROOT=:*)` nor `Bash(if [ -f .adlc/partials/:*)` admits it (ASSUME-022 false) |
| `resume-sibling` | pass | `--resume` from a sibling worktree recalled a word given in the first session (ASSUME-023) |
| `file-scope-write` | pass | 2026-11-09, claude 2.1.316: `Write` created a file in the working copy and was refused a new file outside it; before BUG-265 the tier's bare `Write` wrote outside |
| `file-scope-read` | pass | 2026-11-09: `Read` of a file outside the working copy and ToolkitRoot was refused, and its nonce is absent from the run's output (BUG-265) |

Those two rows were a gap with two causes (BUG-260). The `{branch}` push entries in
`harness/claude.yml` were prefix rules, so anything could follow them. And `claude -p` read the
operator's `~/.claude/settings.json` and the project's committed `.claude/settings.json`, both of
which allow `Bash(git push:*)`, so removing the engine's prefix alone did not stop the push: the
first rerun after that change still pushed `main`. With the entries exact and every launch
passing `--setting-sources "" --settings <runDir>/settings.json --strict-mcp-config`, the rerun
on 2026-11-02 denied both pushes and left the origin unchanged. Every other row read the same.
`fence` still fails: that is ASSUME-022, open as a design question for the engine.

## File-tool scope (BUG-265), 2026-11-09

A bare tool name in the allow list admits that tool on every path: with the tier's bare
`Write`, a launch under the engine's isolation flags wrote a file outside its working directory,
while `cp`, `touch` and `mkdir` with matching allows were refused there by Claude's path check.
Scoped rules hold, in the dogfood layout (working copy at `<tk>/.worktrees/REQ-x`):

- `Edit(//<wc>/**)` admits `Write` and `Edit` in the working copy; without it the same write is
  refused (the control). It refuses `<tk>/partials/f.sh`, a `<wc>/../` path and a write through a
  symlink out of the working copy.
- `Read(//<tk>/**)` admits `Read` (and `cat`) of the toolkit; a file outside every root is refused
  to `Read`, `cat`, `grep`, `head`, `find` and `ls`.
- A rule is matched against the path as written: a rule on `/private/var/...` did not cover a write
  to `/var/...` (macOS's symlinked spelling), so the engine emits both spellings of a root.
- `Glob` and `Grep` are not tools in 2.1.316; their names in `allow_tools` were inert.
