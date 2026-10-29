---
id: ASSUME-005
title: "Every install has a canonical partials/ directory under ToolkitRoot, so the final canonical source arm may stay unguarded"
status: validated
req: REQ-610
created: 2026-09-02
resolved: 2026-09-02
---

## Assumption

On every machine that runs a skill, the installed toolkit's partials directory
exists, so the canonical copy of `partials/<name>.sh` resolves. The guarded spelling
therefore tests only the repo-local copy with `[ -f ]` and dot-sources the canonical
copy unguarded. Its absence means "the toolkit is not installed", which no fallback
can recover, and the right behaviour is a loud failure (fatal under `sh`, an error
line under bash/zsh), not a silent skip.

As written for REQ-610, the canonical copy was `~/.claude/skills/partials/<name>.sh`,
because the only install was the symlink at `~/.claude/skills/`. Since REQ-669 it is
`"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"`, and ToolkitRoot is whichever install is
running (see Resolution).

## Context

REQ-610 BR-1 was amended during reflect to state this explicitly after the reflector
showed the original wording contradicted the mandated spelling. Two things depend on
it: `adlc_recheck_id`'s "cannot source id-alloc.sh" `return 2` is reachable only
under bash/zsh (under `sh` the same condition is the fatal exit), and the
`id-alloc.test.sh` sandboxes had to grow the canonical sibling link so the dash pass
models a real install. `partials/tests/source-guard.test.sh` case (c) encodes the
accepted behaviour: both copies absent must leave a non-empty stderr naming the path.

## Resolution

Validated for the symlink install model on 2026-09-02: `install.sh` creates the
symlink, every skill's ethos macro already depends on the same directory, and the
harness proves the loud-failure behaviour under all four shells. It is **not** true
for a hypothetical vendored-only consumer (a CI box that copied `.adlc/partials/` but
never installed the toolkit); on such a box a fence whose repo-local copy is missing
exits under `sh` with the path on stderr, which is the intended signal. Revisit if a
non-symlink install path is ever added.

### Revisited for REQ-669 (2026-10-28): still validated, now through ToolkitRoot

REQ-669 added that non-symlink install path, the Claude Code plugin, so this record
was revisited as its last line asks. The canonical arm is now ToolkitRoot. A fence's
root line sets `ADLC_TOOLKIT_ROOT` from four arms in order, and the assumption holds
on each machine shape:

- **Symlink only.** Arm 2 picks `$HOME/.claude/skills` when its `partials/` exists,
  which is the original case, unchanged (REQ-669 BR-3).
- **Plugin only.** Arm 1 is the `${CLAUDE_PLUGIN_ROOT}` that Claude Code substitutes
  into plugin skill text, verified on Claude Code 2.1.258 (REQ-669 `verification.md`
  row 1). For text that was not substituted, such as a SKILL.md a subagent reads raw,
  arm 3 reads `~/.claude/adlc/plugin-root`, which the plugin's SessionStart hook writes
  at session start (row 9). The pointer arm is what makes the assumption hold for that
  text. The plugin's cache copy always has `partials/`: the hook refuses to record a
  root without one.
- **Both.** Arm 2 comes before the pointer, so a symlink-route skill still reads the
  clone, and `adlc doctor`'s `doubled-install` check reports the doubling.
- **Neither.** Arm 4 is the literal `$HOME/.claude/skills`, so the source fails loudly
  and names that path, as before.

One new gap: on a plugin-only machine where the hook could not write the pointer,
unsubstituted text falls to arm 4. The failure is still loud, but the path it names is
the symlink route's, which can mislead. `adlc doctor`'s `plugin-route` check reports a
missing or stale pointer and prints the command that rewrites it.
`partials/tests/toolkit-root.test.sh` runs every shape above under bash, zsh, `/bin/sh`
and dash, including `case_neither_install_fails_loud`. The vendored-only CI box remains
the one known shape where the assumption does not hold, with the same intended signal.
