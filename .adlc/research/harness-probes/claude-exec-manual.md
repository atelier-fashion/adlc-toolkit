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
