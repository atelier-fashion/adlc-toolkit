---
name: map
description: Regenerate the atelier-map Obsidian knowledge graph (repos ↔ models ↔ fields) from current source, then report what changed. Use when the user says "regenerate the map", "update atelier-map", "refresh the code map", or wants the architecture graph brought up to date with HEAD.
argument-hint: Optional — "no-commit" to skip the commit, or a model name to spot-check
---

# /map — Regenerate the Atelier code map

You regenerate the **atelier-map** Obsidian vault so its graph reflects the current
state of the code, then report what changed. The vault maps every domain model to
the repos and source files that use each of its fields — change-impact analysis as a
navigable graph.

## Ethos

!`sh ~/.claude/skills/partials/ethos-include.sh 2>/dev/null`

## What the map is

- `atelier-map/` is a sibling repo of the Atelier code repos (under the shared
  repos root, default `~/Documents/GitHub`).
- It is **fully generated** from source by `tools/gen-map.py` (config in
  `map.config.json`). Never hand-edit `models/` or `fields/` — they are overwritten.
  `repos/` is hand-curated topology; leave it unless asked.
- Output is deterministic (stable sort, no in-body timestamps), so each regeneration's
  `git diff` is a true record of architecture change.

## Context

- Repos root: !`echo "${REPOS_ROOT:-$HOME/Documents/GitHub}"`
- Vault present: !`test -f "${REPOS_ROOT:-$HOME/Documents/GitHub}/atelier-map/tools/gen-map.py" && echo yes || echo "NO — see Prerequisites"`
- Argument: $ARGUMENTS

## Prerequisites

The vault must already exist at `<repos-root>/atelier-map` with `tools/gen-map.py`.
If "Vault present" above is NO, stop and tell the user the vault isn't set up — this
skill regenerates an existing map, it does not bootstrap one.

## Steps

Run from the repos root. Let `VAULT="${REPOS_ROOT:-$HOME/Documents/GitHub}/atelier-map"`.

1. **Refresh source symlinks** (idempotent; recreates `code/` so links resolve):
   ```bash
   bash "$VAULT/tools/link-sources.sh"
   ```

2. **Regenerate** every model + field note from current source:
   ```bash
   python3 "$VAULT/tools/gen-map.py"
   ```
   It prints `Discovered N domain models` and `Wrote N model + M field notes` to stderr.
   Requires Python 3 and `git` (uses `git grep`). Typical runtime: a few seconds.

3. **Report what changed** — this is the valuable part. Show the diff shape:
   ```bash
   git -C "$VAULT" status --short
   git -C "$VAULT" diff --stat
   ```
   Summarize in prose: new/removed models, fields whose cross-repo footprint changed
   (e.g. "`User.email` gained 2 writers in admin-api"). If a model the user named in
   `$ARGUMENTS` exists, `cat "$VAULT/models/<Name>.md"` and walk its table.

4. **Commit** (unless `$ARGUMENTS` contains `no-commit`, or there are no changes):
   ```bash
   git -C "$VAULT" add -A
   git -C "$VAULT" commit -m "map: regenerate from <source-repo>@<short-sha>

   <one line: N models, M field notes; notable footprint changes>

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
   ```
   Use the **source** repo's short SHA (`git -C "$VAULT/../atelier-fashion" rev-parse --short HEAD`)
   in the message so each map commit is traceable to the code it reflects. Do **not**
   push unless asked.

## Notes

- **Scope / tuning** lives in `map.config.json` (which repos, model source globs, DTO
  suffix excludes, per-repo path mapping, the `generic_fields` noise list, `cap_per_repo`).
  If the user wants more/fewer entities or to de-noise a field, edit config and re-run —
  don't special-case it in the skill.
- **Heuristic, not compiler-grade.** Field usage is `git grep` of both `camelCase` and
  `snake_case`; 🟢 = distinctive name, 🟡 = generic token (over-counts). Say so if a
  count looks surprising rather than treating it as ground truth.
- **Graph defaults** (Orphans off, Attachments off) live in `.obsidian/graph.json`; a
  running Obsidian session owns that file, so changing the default may require setting it
  while Obsidian is closed (or via the in-app graph Filters panel).
