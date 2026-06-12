# Architecture — REQ-526: Context-doc truth pass

## Summary

Pure-documentation REQ. No code, no schema, no tests beyond a closing verification grep
(BR-6). The work is a set of surgical edits across five doc/distribution surfaces to make
every claim true against the current tree, plus removal of one project-specific skill
(`/map`) from the distributed skill set with its content preserved in a tombstone note.

There is no runtime architecture to design — the "design" here is the precise per-file
edit plan and the verification that proves the edits landed. Tasks are organized by
business rule, each independently verifiable by its acceptance-criterion grep/ls check.

## Ground-truth findings (verified against the worktree tree at branch base)

- ETHOS.md has **7** numbered principles (`## 1.`–`## 7.`), not 5. #6 "If It's Broken,
  Fix It" and #7 "Skeptical by Default" were added in 3.1.0 / 4.9.0.
- Four "five principles" claims exist: `architecture.md:7`, `architecture.md:25`,
  `project-overview.md:25`, `conventions.md:144`.
- `/map` (`map/SKILL.md`) is hardcoded to the `atelier-map` Obsidian vault and
  `~/Documents/GitHub`/atelier-fashion repos. It is NOT listed in the README skill
  catalog (consistent with M7's "undisclosed"). `install.sh` symlinks the **entire repo
  root** at `~/.claude/skills` (line 190 `ensure_symlink "$REPO_ROOT" "$CLAUDE_DIR/skills"`),
  so there is no per-skill enumeration to edit — removing `map/` from the tree is what
  excludes it from distribution.
- `project-overview.md` lines 7 and 32 falsely claim the toolkit tracks no lessons/bugs;
  the tree has 40 files under `.adlc/knowledge/lessons/` and multiple under `.adlc/bugs/`.
  Line 25 says "Five principles". Lines 38–46 anchor numbering at "local high-water
  REQ-263" / atelier-fashion REQ-380, predating REQ-518's remote-derived allocation and
  the 5.0 portability epoch (VERSION is 5.0.0).
- `CHANGELOG.md` epoch summary list (lines ~21–27) renders order 1, 2, 3, **5, 4** — the
  `5.x` bullet precedes the `4.x` bullet.
- README (lines 31–35) and architecture.md (lines 48–52) enumerate five templates, omitting
  `taxonomy-template.md` (present in `templates/`).
- `partials/README.md` omits `id-alloc.sh`/`id-recheck.sh` from its sourceable-partial list
  and (lines 80–82) claims partial drift detection is "not yet implemented" — but
  `template-drift/SKILL.md` Step 3 ("Detect Partial Drift") fully implements it.

## Disposition of the /map Open Question

The spec's Open Question defaults to relocating `/map` to the atelier project's own skill
directory. The pipeline runs sandboxed inside this repo's worktree and cannot write to a
sibling repo. Per the launch directive, the resolution is: **remove `map/` from the
distribution (BR-2) and preserve its content via a tombstone/migration note** so the
relocation can be completed by hand later. The tombstone lives in CHANGELOG (a migration
note under the unreleased/next section) and the removed skill's intent is recorded there;
the full SKILL.md body remains recoverable from git history (the removal commit).

## Per-file edit plan

| Surface | Edit | BR | AC |
|---|---|---|---|
| `architecture.md:7,25` | "5 principles"/"the five principles" → "the ETHOS principles" (drop the count) | BR-1 | grep clean |
| `architecture.md:48–52` | Template list: add `taxonomy-template.md`, or point at `templates/` as authoritative | BR-5 | matches `ls templates/` |
| `conventions.md:144` | "the five principles (especially #4…#5…)" → "the ETHOS principles (especially…)" | BR-1 | grep clean |
| `project-overview.md:25` | "Five principles injected…" → "ETHOS principles injected…" | BR-1 | grep clean |
| `project-overview.md:7,32` | Remove false "no lessons/bugs" claims; state the toolkit tracks both | BR-3 | no contradicted claim |
| `project-overview.md:38–46` | Reframe numbering as remote-derived (REQ-518); "REQ-263" anchor marked historical; add 4.x/5.0 epoch context; tag dating claims with as-of or point at CHANGELOG/VERSION | BR-3 | no contradicted claim |
| `CHANGELOG.md:~21–27` | Reorder epoch summary list so `4.x` precedes `5.x` (reads 1→5); `[5.0.0]` body untouched. Add a `/map` removal tombstone migration note | BR-4, BR-2 | list reads 1,2,3,4,5 |
| `README.md:31–35` | Template list: add `taxonomy-template.md` (or reference `templates/`) | BR-5 | matches `ls templates/` |
| `partials/README.md:34–51` | Add `id-alloc.sh` + `id-recheck.sh` entries at same depth | BR-5 | documents both |
| `partials/README.md:80–82` | Drop "not yet implemented" — point at `/template-drift` Step 3 | BR-5 | no false drift claim |
| `map/SKILL.md` (+ `map/` dir) | Remove from tree (content preserved via tombstone + git history) | BR-2 | `map/` absent |

## Closing verification (BR-6)

After edits, run the acceptance-criteria greps as a single checkable block:

```sh
grep -rn 'five principles\|5 principles' .adlc/context/ README.md   # → nothing
test ! -d map                                                        # map/ gone
grep -rn 'atelier' README.md install.sh CHANGELOG.md                 # → no skill ref
grep -rn "doesn't track lessons\|don't track lessons\|track lessons or bugs for itself yet" .adlc/context/   # → nothing
# CHANGELOG epoch list source order is 1..5 (visual check)
diff <(ls templates/ | sed 's/\.md$//' ) <(...README/arch template list...)   # match
```

## Risks / notes

- Editing `.adlc/context/` docs changes ground truth loaded into future toolkit-internal
  agent sessions — the upside of the whole REQ. Low risk: edits only correct false claims.
- `architecture.md`/`README.md` template enumeration: prefer "reference the `templates/`
  directory as authoritative" where it reads naturally (BR-5 explicitly allows it), to
  avoid re-introducing the same enumeration-rot the REQ is fixing (LESSON-019).
- Removing `map/` could orphan a cross-reference. Verified: README catalog does not list it;
  grep for `/map` across distributed surfaces is part of BR-6 verification.
- Out of scope: drift *detection* for context docs (REQ-525), any code change.
