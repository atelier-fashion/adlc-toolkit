---
name: manifest
description: Remote-derived view of all in-flight ADLC work — open PRs and pushed feat/REQ-* branches across every session — with a coarse component/domain overlap report. Read-only and advisory.
argument-hint: "[REQ-xxx] — optional; mark a REQ as the current session's own (defaults to the current branch's REQ)"
---

# /manifest — In-Flight ADLC Work (cross-session, remote-derived)

You produce a read-only, on-demand **manifest** of all in-flight ADLC work by deriving it from the **remote** — open GitHub PRs plus pushed `feat/REQ-*` branches — enriching each entry with its `component`/`domain`, and flagging coarse overlaps.

Unlike `/status`, which reconstructs its view from the **local** `.adlc/` checkout and is therefore blind to another collaborator's unmerged work on another machine, `/manifest` reflects what every session has published to the shared remote. Use it before starting work to see what else is in flight and avoid stepping on another session.

**This skill is strictly read-only and advisory.** It never creates, edits, pushes, or deletes anything, never writes a stored manifest file, and never blocks, reorders, or gates a pipeline. Surfacing an overlap is informational only — enforcement is a separate, future capability.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Current branch: !`git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "(not a git repo)"`
- Remote feat/REQ-* branches: !`git ls-remote --heads origin 'refs/heads/feat/REQ-*' 2>/dev/null | grep -c . || echo 0`
- gh availability: !`gh auth status >/dev/null 2>&1 && echo "authenticated" || echo "unavailable — will degrade to branch-only"`

## Input

`$ARGUMENTS` (optional): a REQ id (e.g. `REQ-482`) to mark as the current session's own ("self"). If omitted, self defaults to the REQ inferred from the current branch name. When invoked from a pre-flight (`/proceed` Step 0, `/sprint` Step 2) the caller passes the active REQ id(s).

## Prerequisites

- Must run inside a git repository with a reachable `origin`. If `git rev-parse --git-dir` fails, stop with: "Not a git repository — `/manifest` derives in-flight work from the remote and must run inside an ADLC repo."
- `gh` (GitHub CLI) is **optional**. If absent or unauthenticated, the manifest degrades to a remote-branch-only view and says so — it does not fail.

## Instructions

### Steps 1–3: Derive the manifest data (read-only)

Run the following. It syncs remote refs once, enumerates in-flight REQs from open PRs and pushed `feat/REQ-*` branches (deduped by REQ id), and enriches each with `component`/`domain`. It writes nothing to the repo (only auto-removed scratch files) and makes O(1) network calls — at most one fetch and one `gh pr list` (BR-1, BR-2, BR-14).

```sh
# --- /manifest: collect in-flight work from the remote (read-only) ---

# Step 1 — Sync remote refs ONCE. A pre-flight caller (/proceed Step 0,
# /sprint Step 2) has already fetched; it sets MANIFEST_SKIP_FETCH=1 so we
# do not fetch twice (BR-14). Standalone, fetch exactly once.
if [ "${MANIFEST_SKIP_FETCH:-0}" != "1" ]; then
  git fetch origin --quiet 2>/dev/null || echo "/manifest: fetch failed — using cached remote refs" >&2
fi

TAB=$(printf '\t')
raw=$(mktemp -t manifest.XXXXXX) || { echo "/manifest: mktemp failed" >&2; exit 1; }
trap 'rm -f "$raw"' EXIT

# Self = the REQ argument if given, else the REQ inferred from the current branch.
self_req=$(printf '%s' "${ARGUMENTS:-}" | grep -oE 'REQ-[0-9]{3,6}' | head -1)
if [ -z "$self_req" ]; then
  self_req=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -oE 'REQ-[0-9]{3,6}' | head -1)
fi

# gh is optional — degrade to branch-only when absent/unauthenticated (BR-6).
gh_ok=0
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh_ok=1
fi

# Step 2a — open PRs (ONE batched call; includes drafts). Map headRefName -> REQ
# via the feat/REQ-<digits>-<slug> convention; the grep both extracts AND
# validates the id (BR-5). Non-matching branches are silently ignored (BR-4).
if [ "$gh_ok" = "1" ]; then
  gh pr list --state open --limit 200 \
    --json headRefName,author,isDraft,createdAt,url \
    --jq '.[] | [.headRefName, (.author.login // "unknown"), (if .isDraft then "draft" else "ready" end), .createdAt, .url] | @tsv' \
    2>/dev/null | while IFS="$TAB" read -r branch author state created url; do
      req=$(printf '%s' "$branch" | grep -oE '^feat/REQ-[0-9]{3,6}-' | grep -oE 'REQ-[0-9]{3,6}')
      [ -n "$req" ] || continue
      printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$req" "$branch" "$state" "$author" "$created" "$url"
    done >> "$raw"
fi

# Step 2b — pushed feat/REQ-* branches with no open PR (local read against the
# already-fetched refs; no network). Dedup by REQ id — a PR row already wins.
git branch -r --list 'origin/feat/REQ-*' 2>/dev/null | sed 's#^[ *]*origin/##' | while read -r branch; do
  req=$(printf '%s' "$branch" | grep -oE '^feat/REQ-[0-9]{3,6}-' | grep -oE 'REQ-[0-9]{3,6}')
  [ -n "$req" ] || continue
  if cut -f1 "$raw" 2>/dev/null | grep -qxF "$req"; then continue; fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$req" "$branch" "no-pr" "-" "-" "-"
done >> "$raw"

# Step 3 — enrich component/domain: local frontmatter first, then the spec on
# the remote branch (git show), then "unknown". Never drop an entry (BR-11/12).
# Every interpolated branch/path is validated to a safe charset and rejected if
# it contains '..' before any git show (BR-5, LESSON-008).
emit_field() { awk -v k="$1" 'index($0,k)==1{sub(/^[^:]*:[[:space:]]*/,"");gsub(/"/,"");print;exit}'; }
echo "MANIFEST_BEGIN self=${self_req:-none} gh=${gh_ok}"
while IFS="$TAB" read -r req branch state author created url; do
  comp=""
  dom=""
  loc=$(ls .adlc/specs/"$req"-*/requirement.md 2>/dev/null | head -1)
  if [ -n "$loc" ]; then
    comp=$(emit_field "component:" < "$loc")
    dom=$(emit_field "domain:" < "$loc")
  fi
  if [ -z "$comp$dom" ]; then
    case "$branch" in
      *..*) : ;;
      feat/REQ-[0-9]*-*)
        sp=$(git ls-tree -r --name-only "origin/$branch" 2>/dev/null | grep -E "\.adlc/specs/$req-[A-Za-z0-9._-]+/requirement\.md$" | head -1)
        if [ -n "$sp" ]; then
          comp=$(git show "origin/$branch:$sp" 2>/dev/null | emit_field "component:")
          dom=$(git show "origin/$branch:$sp" 2>/dev/null | emit_field "domain:")
        fi
        ;;
    esac
  fi
  [ -n "$comp" ] || comp="unknown"
  [ -n "$dom" ] || dom="unknown"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$req" "$branch" "$state" "$author" "$created" "$comp" "$dom" "$url"
done < "$raw" | sort -u
echo "MANIFEST_END"
[ "$gh_ok" = "1" ] || echo "/manifest: gh unavailable — PR fields shown as '-'; branch-only view (BR-6)." >&2
```

### Step 4: Render the manifest table

Parse the lines between `MANIFEST_BEGIN` and `MANIFEST_END`. Each is TSV with columns: `req`, `branch`, `state`, `author`, `opened` (ISO timestamp — show the date only), `component`, `domain`, `pr-url`. The header line carries `self=<REQ|none>` and `gh=<0|1>`.

Render a markdown table, one row per REQ, sorted by REQ id:

| REQ | Author | Branch / PR | State | Component / Domain | Opened | Self |
|-----|--------|-------------|-------|--------------------|--------|------|

- **Branch / PR**: show the branch; when `pr-url` is not `-`, render it as a markdown link on the branch text.
- **State**: `ready` (open PR), `draft` (draft PR), or `no-pr` (pushed branch, no PR).
- **Component / Domain**: `component / domain`; show `unknown` where enrichment found nothing.
- **Self**: `✓` when `req` equals the header's `self` value; otherwise blank.
- If there are no rows, print: "No in-flight `feat/REQ-*` work found on `origin`."
- If the header shows `gh=0`, add a one-line note that `gh` was unavailable so PR fields are omitted (branch-only view).

### Step 5: Coarse overlap report (advisory)

After the table, compute overlaps among the listed REQs: any pair sharing the **same `component`** OR the **same `domain`** (ignore `unknown` on both sides — an unknown never overlaps). For each overlapping pair, emit one advisory line naming both REQs and **which field matched**, e.g.:

> ⚠️ Advisory: REQ-482 and REQ-491 both touch **component `adlc/sprint`**. No action enforced — coordinate or sequence if they edit the same files.

If the current session's REQ (self) is among the overlaps, call that out first. End the section with an explicit reminder that this is **advisory only — `/manifest` does not block, reorder, or gate anything.** If there are no overlaps, print: "No component/domain overlaps among in-flight work."

### Graceful degradation (must never hard-fail)

- No `gh` / not authenticated → branch-only view, annotated; exit 0 (BR-6).
- Invoked from a pre-flight (`/proceed`, `/sprint`) and any step errors → emit what was gathered (or nothing) and **continue**; never block, halt, or fail the host pipeline (BR-7).

## Quality Checklist

- [ ] Read-only: no repo writes, no branch/PR mutation; `git status` is clean after a run (BR-2); no stored manifest file created (BR-1).
- [ ] Enumerates from BOTH open PRs (incl. drafts) AND pushed `feat/REQ-*` branches, deduped by REQ id (BR-3).
- [ ] Every REQ id / branch / path derived from `gh`/git is validated to a safe charset (and `..` rejected) before shell use (BR-5, LESSON-008).
- [ ] Enrichment falls back local → remote → `unknown` and never drops an entry (BR-11, BR-12).
- [ ] Overlap report is advisory only, labels the matched field, and states no action is enforced (BR-8).
- [ ] O(1) network: one fetch (or reuse) + one `gh pr list`; no per-branch API calls (BR-14).
- [ ] Degrades gracefully without `gh` and never blocks a pre-flight (BR-6, BR-7).
