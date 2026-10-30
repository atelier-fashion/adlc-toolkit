---
name: template-drift
description: Detect drift between the copies `/init` vendored into a project's `.adlc/` (templates, partials, agents, ETHOS, workflow runtime) and the running toolkit install. Use when the user says "check template drift", "template drift", "are my templates out of date", or wants to know whether toolkit template, partial, agent, ETHOS, or workflow-engine updates have landed in this project yet. Reports each file synced, stale, missing or customized, and flags stale `*.test.js` files under `.adlc/workflows/`.
argument-hint: Optional template name (e.g., "requirement-template") to scope the check to a single file
---

# /template-drift — Template Drift Detector

You are checking whether the project's local copies of every **vendored sync surface** still match the canonical versions in the adlc-toolkit. These surfaces are copied per-repo (unlike skills/agents, which load from the install itself), so they drift over time. Some drift is **intentional** (project-specific customization); some is **accidental** (toolkit updated and the project never pulled the change). This skill surfaces both and helps you decide what to reconcile.

## Vendored sync surfaces

<!-- sync-surfaces: template-drift -->
`/template-drift` checks drift on **all seven** of these surfaces. Six are written into the project
by `/init` (see `init/SKILL.md`'s matching `<!-- sync-surfaces: init -->` list); the seventh,
`workflow-test-landmine`, is a `/template-drift`-only check for a drift *symptom* `/init`
deliberately does NOT copy.

- `templates` — `.adlc/templates/*.md` vs `$ADLC_TOOLKIT_ROOT/templates/*.md` (Step 2, template-posture)
- `partials` — `.adlc/partials/*.sh` vs `$ADLC_TOOLKIT_ROOT/partials/*.sh` (Step 3, partials-posture)
- `agents` — `.adlc/agents/*.md` vs `$ADLC_TOOLKIT_ROOT/agents/*.md` (Step 3f, partials-posture)
- `ethos` — `.adlc/ETHOS.md` vs `$ADLC_TOOLKIT_ROOT/ETHOS.md` (Step 3c, template-posture + missing-principle)
- `workflow-runtime` — `.adlc/workflows/adlc-sprint.workflow.js` + `README.md` vs `$ADLC_TOOLKIT_ROOT/workflows/` (Step 3d, partials-posture)
- `workflow-test-landmine` — stale `*.test.js`/`*.spec.js` under `.adlc/` from an older `/init` (Step 3b, always stale; template-drift-only)
- `harness-config` — the rendered project layer (`.claude/settings.json`, and when the project has them `.github/hooks/adlc.json`, `.cursor/cli.json`, `.cursor/permissions.json`) vs a fresh `adlc harness render` (Step 3g, template-posture + missing deny-tier rule)
<!-- /sync-surfaces -->

**Cross-reference invariant (BR-4):** every surface `/init` copies MUST have a matching check here.
Adding a new vendored surface to `/init` without adding a check here is a silent gap — the toolkit's
`tools/lint-skills` `sync-surface-parity` check fails the build when the two lists disagree.

## Ethos

!`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo No ethos found — run /init, or /adlc:init on the plugin install, to vendor .adlc/ETHOS.md`

## Context

This skill checks seven vendored sync surfaces (see "Vendored sync surfaces" above): templates, partials, agents, ethos, workflow-runtime, the workflow-test landmine, and harness-config.

Run this block first, with your shell tool, and read its output before you continue. Each read prints a notice instead of failing when its file is absent.

```sh
# adlc-context
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
echo '--- Project templates dir'
ls .adlc/templates/ 2>/dev/null || echo 'No .adlc/templates/ directory — run /init (/adlc:init on the plugin install) first'
echo '--- Project ETHOS'
test -f .adlc/ETHOS.md && echo 'present' || echo 'absent — run /init (/adlc:init on the plugin install)'
echo '--- Project agent checklists'
ls .adlc/agents/ 2>/dev/null || echo 'no .adlc/agents/ — run /init (/adlc:init on the plugin install)'
echo '--- Project workflow runtime'
ls .adlc/workflows/ 2>/dev/null || echo 'no .adlc/workflows/ runtime — run /init (/adlc:init on the plugin install)'
echo '--- Current directory'
pwd
echo '--- Toolkit templates'
echo "ToolkitRoot: $ADLC_TOOLKIT_ROOT"
ls "$ADLC_TOOLKIT_ROOT/templates/" 2>/dev/null || echo "Toolkit templates not found at $ADLC_TOOLKIT_ROOT/templates/"
```

The fence names ToolkitRoot, the running install's toolkit directory (the plugin's cache copy on the plugin route, the clone behind the skills symlink on the symlink route), and lists its templates. It reads the toolkit from a fence because a preamble line cannot read under the plugin root, which is not an allowed working directory, and one that uses a `$VAR` is refused under `claude -p`, which silently drops the whole skill (REQ-669 `verification.md` N1, N2).

The steps below name toolkit files as `$ADLC_TOOLKIT_ROOT/<path>`. Bash calls share no shell state, so a command you run that reads one starts with the same root line, or uses the absolute ToolkitRoot path this fence printed. A command you **propose to the user** always uses that absolute path, written out where Step 5 and Step 6 show `<ToolkitRoot>`: `$ADLC_TOOLKIT_ROOT` is not set in the user's shell.

## Input

The scope is the argument: whatever follows `/template-drift` in the invocation (on Claude Code it can also arrive as an `ARGUMENTS:` line appended to this text), optionally one template name. With none, every template is checked.

## Prerequisites

1. `.adlc/templates/` must exist in the current project. If it does not, stop and tell the user: "This project has no local templates — it uses toolkit templates directly. No drift to check." (New projects per the `/init` Step 6 policy don't copy templates locally.)
2. `$ADLC_TOOLKIT_ROOT/templates/` must exist (the context fence lists it). If it does not, stop and tell the user: "The adlc toolkit was not found at <ToolkitRoot>. On the plugin route, reinstall it with `claude plugin install adlc@adlc-toolkit`. On the symlink route, check that the skills symlink points at a toolkit clone, and re-run that clone's `./install.sh`."

## Instructions

### Step 0a: Verify the Canonical Baseline (do this first — everything is measured against it)

Whatever ToolkitRoot currently contains is what every comparison below calls "canonical".
If the baseline is wrong, every verdict is wrong — and it fails in the worst direction: a
consumer that is correctly in sync gets reported `stale`, and the proposed remedy is to
copy the older file over it. The skill would then be **driving a regression** with full
confidence. What ToolkitRoot is depends on the install route (REQ-669 ADR-8):

- **Symlink route — a checkout.** ToolkitRoot is the skills symlink, and the symlink points
  at a **working checkout of the toolkit repo**. That is not a release artifact: the
  checkout can be on a feature branch, mid-rebase, or dirty.
- **Plugin route — a released copy.** ToolkitRoot is the plugin's cache copy of one pinned
  version. It has no `.git` (REQ-669 `verification.md` row 11), so it has no branch to be
  wrong about. Its baseline is named by the version in its own
  `.claude-plugin/plugin.json`: `adlc plugin <version>`.

The fence tells the two apart by what ToolkitRoot is, not by which arm of the root line
found it. A root with `.git` is a checkout and gets the checkout checks whichever route
loaded it, which includes a plugin installed from a local-path marketplace, because that
runs from its source checkout (`verification.md` N3). A root without `.git` is a released
copy. Establish the baseline before measuring anything against it. **Run this fence as
written, in one Bash call, before any other read of ToolkitRoot.** Do not read
`.claude-plugin/plugin.json` yourself instead: the fence's parse is what turns a missing or
malformed manifest into `unverified-baseline`, and a version you read by hand skips it
(LESSON-716).

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
TOOLKIT="$ADLC_TOOLKIT_ROOT"
if [ -e "$TOOLKIT/.git" ]; then
  # A checkout (the symlink route): BUG-204's checks, unchanged. This branch
  # prints nothing of its own, exactly as before REQ-669.
  git -C "$TOOLKIT" fetch --prune origin
  TK_BRANCH=$(git -C "$TOOLKIT" branch --show-current)
  TK_DEFAULT=$(git -C "$TOOLKIT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
  TK_DEFAULT=${TK_DEFAULT:-main}
  TK_DIRTY=$(git -C "$TOOLKIT" status --porcelain | wc -l | tr -d ' ')
  TK_BEHIND=$(git -C "$TOOLKIT" rev-list --count "HEAD..origin/$TK_DEFAULT" 2>/dev/null)
else
  # A released copy (the plugin route): the version its own manifest names,
  # parsed with repeated keys rejected (LESSON-716). Any failure names its
  # reason on stderr and leaves TK_VERSION empty.
  TK_VERSION=$(python3 -c 'import json,re,sys; sys.excepthook=lambda t,e,tb: sys.stderr.write("plugin.json unreadable: %s: %s\n" % (t.__name__, e)); m=json.load(open(sys.argv[1],encoding="utf-8"),object_pairs_hook=lambda p: dict(p) if len(dict(p))==len(p) else sys.exit("plugin.json unreadable: a repeated JSON key (LESSON-716)"),parse_constant=lambda c: sys.exit("plugin.json unreadable: %s is not a JSON value" % c)); v=m.get("version") if isinstance(m,dict) and m.get("name")=="adlc" else None; print(v) if isinstance(v,str) and re.fullmatch(r"[0-9A-Za-z.+-]+",v) else sys.exit("plugin.json unreadable: no adlc version string")' "$TOOLKIT/.claude-plugin/plugin.json")
  if [ -n "$TK_VERSION" ]; then
    echo "baseline: adlc plugin $TK_VERSION ($TOOLKIT)"
  else
    echo "baseline: unverified-baseline — no adlc plugin version could be read from $TOOLKIT/.claude-plugin/plugin.json; report every drift verdict as unverified-baseline"
  fi
fi
```

Report the baseline in the header **always**.

**Plugin route (no `.git`).** The fence prints the baseline line. Put it in the header as
printed: `adlc plugin <version>`. That line is the only source of the header's baseline:
if the fence did not run, run it now rather than report a version from anywhere else. When it says `unverified-baseline`, the manifest is
missing or unreadable, repeats a key, names another plugin, or has no version string.
Then downgrade every `stale` verdict to `unverified-baseline`, and say why in the header.
Never fall back to another copy as the baseline: not the skills symlink's clone, not
another cached version, not the project's own files. A drift detector may say it could
not establish a trustworthy baseline, but it never quietly substitutes another one
(BUG-204).

**Checkout (symlink route).** The fence prints nothing and leaves `TK_BRANCH`,
`TK_DEFAULT`, `TK_DIRTY` and `TK_BEHIND` set; print them in the same Bash call. Warn
loudly when any of these hold:

- `TK_BRANCH` != `TK_DEFAULT` — the baseline is a feature branch, not canonical
- `TK_BEHIND` > 0 — the checkout is behind the toolkit's default branch
- `TK_DIRTY` > 0 — uncommitted local edits are being treated as canonical

When any warning fires, say so **before** the tables and state the consequence plainly:
*"Baseline is `<branch>`, N commits behind `origin/<default>` — surfaces reported `stale`
may in fact be ahead of this baseline, and copying from it would regress them."* Prefer
comparing against `git -C "$TOOLKIT" show "origin/$TK_DEFAULT:<path>"` rather than the
working tree when the checkout is not clean-and-current; if you cannot, downgrade every
`stale` verdict to `unverified-baseline` rather than asserting drift you cannot stand
behind.

This is not hypothetical. It produced a false `stale` for `infrastructure`'s `forge.sh`
on 2026-08-28: the toolkit checkout sat on a feature branch cut before `BUG-201` merged,
so the consumer — which correctly carried the newer fix — was reported as the stale one.

### Step 0: Resolve the Pipeline Branch Set

**Every comparison in Steps 1–3d runs once per pipeline branch, not once per checkout.**

In a repo with a promotion pipeline (`dev` → `staging` → `main`), a vendored file is not
one thing — it is one thing *per branch*, and they routinely disagree. A sync PR lands on
the integration branch and reaches `main` only at the next promotion; a change promoted
to `main` reaches `dev` only at the next reverse-sync. Comparing whichever branch happens
to be checked out therefore answers a question nobody asked, and answers it
**confidently**: it reports drift on repos that are merely awaiting promotion, and
reports clean on repos whose other branches are stale. Under-reporting is the exact
failure this skill exists to prevent (BR-4), so a single-branch check is not a smaller
version of the job — it is a wrong answer wearing the costume of a complete one.

Resolve the branch set once, here, and reuse it for every surface:

1. **Fetch, then read refs — never trust a stale local ref (LESSON-036).**
   ```bash
   git fetch --prune origin
   ```
2. **Determine the integration branch** using the *same* rule as `/proceed` step 4 —
   do not invent a second detection rule:
   1. If `.adlc/config.yml` declares `branches.integration`, that value is the
      integration branch outright (a `dev` → `staging` → `main` repo names `dev` here;
      the signals below would wrongly pick `staging`). Stop here.
   2. Otherwise detect the branch model from signals; any one is sufficient:
      - `.adlc/config.yml` declares `gcp.staging_project` (or otherwise indicates a
        staging-first deploy), OR
      - a `.github/workflows/*` enforces a `verify-head-ref` / branch-protection head-ref
        check, OR
      - `CLAUDE.md` describes a "two-branch" / "staging-first" / "staging → main promotion"
        pipeline.

      If any signal is present the integration branch is `staging` (unless the project
      names another); otherwise it is the default branch.
3. **Enumerate the long-lived branches that actually exist on the remote.** Do not assume
   the full triad — `teton-code` has only `main`, `admin-api` has `staging` + `main`,
   `atelier-fashion` has all three:
   ```bash
   DEFAULT_BRANCH=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
   DEFAULT_BRANCH=${DEFAULT_BRANCH:-main}
   # Dedupe in-shell (DEFAULT_BRANCH may itself be dev/staging). Deliberately no
   # awk: its whole-line field reference is a bare positional, which Skill
   # argument templating clobbers inside a fence (lint rule `arg-templating`).
   SEEN=""
   for b in dev staging "$DEFAULT_BRANCH"; do
     case " $SEEN " in *" $b "*) continue ;; esac
     SEEN="$SEEN $b"
     git show-ref --verify --quiet "refs/remotes/origin/$b" && echo "$b"
   done
   ```
   An explicit `pipeline.branches: [dev, staging, main]` in `.adlc/config.yml` overrides
   this detection when present — projects with non-standard names say so rather than
   being guessed at.
4. **Read file content per branch** with `git show`, never from the working tree:
   ```bash
   git show "origin/$BRANCH:.adlc/partials/forge.sh"
   ```
   A path absent on that branch is `missing` **for that branch**, not for the repo.
5. **Also check the working tree**, as its own scope, and report it alongside the
   branches. Uncommitted local edits to a vendored file are themselves drift, and are
   invisible to any `git show`.

**Degrade, never guess.** If the directory is not a git repo, has no `origin`, or the
fetch fails (offline, auth), fall back to **working-tree-only** — the pre-existing
behavior — and say so explicitly in the report header: `branch scope: working tree only
(<reason>)`. A degraded run must still produce its report; it must never silently present
a one-branch result as full coverage.

**Single-branch repos are unchanged.** When the enumeration yields one branch, the output
is materially what it was before, minus the false confidence.

### Step 1: Enumerate Templates to Compare

1. If the user passed a scope argument (e.g. `requirement-template`), only check `.adlc/templates/<scope>.md` vs `$ADLC_TOOLKIT_ROOT/templates/<scope>.md`.
2. Otherwise list every `*.md` file in `.adlc/templates/` AND every `*.md` file in `$ADLC_TOOLKIT_ROOT/templates/`. Compare the union of both sets — this catches templates that exist in the toolkit but not in the project (new templates added upstream) and templates in the project but not in the toolkit (legacy or custom-to-project files).

### Step 2: Detect Template Drift

For each template in the comparison set, run `diff -u "$ADLC_TOOLKIT_ROOT/templates/<name>.md" .adlc/templates/<name>.md`. Capture:
- **Missing upstream**: template exists locally but not in toolkit (legacy or custom)
- **Missing locally** (a.k.a. `missing`): template exists in toolkit but not in project (upstream added, not yet copied)
- **Identical** (a.k.a. `synced`): no diff (drift = 0)
- **Drifted** (a.k.a. `stale`): diff output — count added/removed lines

Also compute a rough drift size: total lines added + total lines removed (excluding context lines). This gives a "how much has changed" number for the summary table.

### Step 3: Detect Partial Drift

Partials (`*.sh` files) are a second sync surface alongside templates. Unlike templates, partials are copied per-repo for portability but are **not** intended for project-specific customization — they are shared executable code (e.g., `ethos-include.sh` injects the toolkit's ETHOS preamble into every skill). The classification vocabulary matches Step 2 (`synced`, `stale`, `missing`) so the final report can use one unified summary line.

**Rationale — why no "intentional customization" classification for partials**:

Partials are shared executable code, not customizable content; intentional consumer-side modification of a partial would shadow the toolkit's gate logic and is the threat model `/template-drift` is meant to detect. Therefore any drift in partials is reported as `stale` with no customization classification. This is a security posture: a consumer with a modified `ethos-include.sh` could silently strip the ETHOS preamble from every skill invocation, and a consumer with a modified gate partial could bypass ADLC phase gates. Treating every partial diff as `stale` (and surfacing it loudly) is the correct default.

For each `*.sh` file in `$ADLC_TOOLKIT_ROOT/partials/` (use a POSIX-safe glob — guard with `[ -e "$f" ]` so that an empty toolkit partials directory does not iterate the literal pattern), compare against `.adlc/partials/<basename>`:

- Run `diff -q .adlc/partials/<basename> "$ADLC_TOOLKIT_ROOT/partials/<basename>"`.
- Exit 0 → `synced` (both exist, identical)
- Exit 1 → `stale` (both exist, content differs)
- Consumer file absent (`.adlc/partials/<basename>` does not exist) → `missing` (toolkit has it, consumer doesn't — consumer needs to re-run `/init` (`/adlc:init` on the plugin install) to copy it down)

Also check the reverse direction: any `*.sh` in `.adlc/partials/` that does NOT exist in `$ADLC_TOOLKIT_ROOT/partials/` should be reported as `missing upstream` (legacy or rogue partial — flag it; do not auto-delete).

If `.adlc/partials/` does not exist at all in the consumer project, report every toolkit partial as `missing` and recommend running `/init` (`/adlc:init` on the plugin install).

### Step 3b: Detect Stale Workflow Test Files (Jest landmine)

A third sync surface is `.adlc/workflows/`. The current `/init` policy vendors **only** the runtime files (`adlc-sprint.workflow.js` + `README.md`) and deliberately does **not** copy the toolkit's `workflows/tests/` directory. Those are `node:test` unit tests (CommonJS `require('node:test')`) for the inlined pure helpers — toolkit-internal, with no purpose in a consumer repo.

An **older** `/init` did `cp -R` of the whole `workflows/` tree and left `.adlc/workflows/tests/helpers.test.js` behind. In any `"type":"module"` repo running Jest, Jest's default testMatch (`**/?(*.)+(spec|test).[jt]s?(x)`) discovers that `*.test.js`, runs it as ESM, and fails it with `ReferenceError: require is not defined` — reddening `npm test` and any CI gate. This is pure accidental staleness (never an intentional customization), so `/template-drift` flags it loudly.

Scan `.adlc/` for any test file that Jest would collect:

```sh
# Any *.test.js / *.spec.js anywhere under .adlc/ is the landmine. The known
# offender is the workflows/tests/ tree from an older `cp -R` /init.
find .adlc -type f \( -name '*.test.js' -o -name '*.spec.js' \) 2>/dev/null
# Also surface a lingering tests/ dir (may also hold _load-pure.js, a .md, etc.):
[ -d .adlc/workflows/tests ] && echo ".adlc/workflows/tests/ present (stale — remove)"
```

Classification is always **stale** — there is no "intentional customization" path here (same posture as partials in Step 3: this is toolkit-internal code a consumer should never carry). Each hit is reported in Step 5 and offered for removal in Step 6. If there are no hits, report `.adlc/` workflow test files as `clean` (one line) and move on.

### Step 3c: Detect ETHOS Drift (the injected constitution)

A fourth sync surface is `.adlc/ETHOS.md` — the principles `/init` copies from `$ADLC_TOOLKIT_ROOT/ETHOS.md` and that **every skill injects at invocation time** via `ethos-include.sh`. This surface is the most consequential to keep in sync: `ethos-include.sh` resolves the **project copy first**, so a stale `.adlc/ETHOS.md` silently runs an outdated constitution in every skill invocation — and the toolkit has shipped new principles more than once (principle #6 "If It's Broken, Fix It" and #7 "Skeptical by Default" were added after the original five). Drift here is therefore reported **prominently**, near the top of the report.

**Classification follows the *template* posture** (intentional customization vs accidental staleness): a project may legitimately tailor its constitution (e.g. add a project-specific principle), so a diff is not automatically `stale`. Read both full versions and judge per the Step 4 signals, treating an added project-specific principle as intentional and a structurally-older copy as accidental.

**Mandatory missing-principle sub-check (the dangerous case, reported loudly regardless of classification):** enumerate the canonical principle headings present upstream and flag any that are **absent** from the project copy. Principle headings are the `## <n>. <title>` lines:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
# Canonical principles present upstream:
grep -E '^## [0-9]+\. ' "$ADLC_TOOLKIT_ROOT/ETHOS.md"
# Project's principles:
grep -E '^## [0-9]+\. ' .adlc/ETHOS.md
# A canonical heading absent from the project copy is a MISSING PRINCIPLE —
# the consumer is silently running an outdated constitution. Report it loudly,
# naming each missing principle by its heading text, even if the file is
# otherwise classified "intentional".
```

Heading-level comparison (not line-level body text) keeps this robust to legitimate body rewording while still catching a wholesale-missing principle. If `.adlc/ETHOS.md` is absent entirely, report `ethos` as `missing` and recommend `/init` (`/adlc:init` on the plugin install). If identical, report `ethos` as `clean` (one line).

### Step 3d: Detect Workflow-Runtime Drift (the sprint engine)

A fifth sync surface is the workflow **runtime** itself — `.adlc/workflows/adlc-sprint.workflow.js` and its vendored `.adlc/workflows/README.md`. This is **distinct from Step 3b**: Step 3b only finds stale *test* files an old `/init` left behind; Step 3d diffs the *runtime file content* against canonical. A consumer's copy is frozen at init time while the toolkit's sprint engine keeps evolving, so a stale runtime silently runs an outdated orchestrator.

**Classification follows the *partials* posture**: this is shared executable code, not customizable content. Every diff is reported as **`stale`** with a loud warning and no customization track — a consumer-modified sprint engine is exactly the silent-divergence threat the partials rationale (Step 3) already names. Use exit-code-only comparison (the only remediation is "copy from toolkit"); show the full diff only if the user asks for `--verbose`:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
for wf in adlc-sprint.workflow.js README.md; do
  if [ ! -f ".adlc/workflows/$wf" ]; then
    echo "$wf: missing (toolkit has it, project does not — run /init (/adlc:init on the plugin install))"
  elif diff -q ".adlc/workflows/$wf" "$ADLC_TOOLKIT_ROOT/workflows/$wf" >/dev/null 2>&1; then
    echo "$wf: synced"
  else
    echo "$wf: stale (workflow runtime diverged from toolkit — copy from toolkit)"
  fi
done
```

If `.adlc/workflows/` does not exist at all, report `workflow-runtime` as `missing` and recommend `/init` (`/adlc:init` on the plugin install). If both files are identical, report `workflow-runtime` as `clean` (one line).

### Step 3f: Detect Agent-Checklist Drift (the inline arm's checklists)

The sixth surface is `.adlc/agents/`, the agent checklists `/init` copies so a dispatch paragraph's inline arm can read them where ToolkitRoot is out of reach (REQ-666 BR-8). **Partials posture**, for the reason Step 3 gives: a checklist is the review or implementation contract, and a consumer-modified one would silently weaken it. Every difference is `stale`, with no customization track. That includes a copy whose only difference is the `model:` line that `adlc agents render` stamps (REQ-516): the copy is a snapshot, and `stale` is correct. The Step 0a baseline rule applies as it does to partials (BUG-204). `find`, not a glob, so an empty or absent directory does not abort zsh (LESSON-335):

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
find "$ADLC_TOOLKIT_ROOT/agents" -maxdepth 1 -name '*.md' 2>/dev/null | sort | while IFS= read -r f; do
  agent_md=$(basename "$f")
  if [ ! -f ".adlc/agents/$agent_md" ]; then
    echo "$agent_md: missing (toolkit has it, project does not — run /init (/adlc:init on the plugin install))"
  elif diff -q ".adlc/agents/$agent_md" "$f" >/dev/null 2>&1; then
    echo "$agent_md: synced"
  else
    echo "$agent_md: stale (agent checklist diverged from toolkit — copy from toolkit)"
  fi
done
find .adlc/agents -maxdepth 1 -name '*.md' 2>/dev/null | sort | while IFS= read -r f; do
  agent_md=$(basename "$f")
  [ -f "$ADLC_TOOLKIT_ROOT/agents/$agent_md" ] || echo "$agent_md: missing upstream (not in the toolkit — flag it, do not delete)"
done
```

If every file is `synced`, report `agents` as `clean` (one line). If `.adlc/agents/` does not exist, every agent prints `missing`; report the surface as `missing` and recommend `/init` (`/adlc:init` on the plugin install).

### Step 3g: Detect Harness-Config Drift (the rendered allowlist and hooks)

The seventh surface is the harness project layer `/init` Step 8 renders (REQ-657 BR-11): `.claude/settings.json`, from the toolkit's `templates/permissions.yml` and `templates/hooks.yml` through `harness/claude.yml`, plus, in a project that opted in with `/init --harness` (`/adlc:init --harness` on the plugin install), `.github/hooks/adlc.json` (Copilot CLI) and `.cursor/cli.json` and `.cursor/permissions.json` (Cursor, REQ-656). `--opted-in` compares those only when one of the harness's files exists, so a project that never asked for them gets no `missing` row. It is **re-rendered, not diffed against a copy**: `adlc harness drift` renders the project layer fresh and compares it with the project's file by set, with **template posture**, because a project may legitimately add its own commands:

- `synced` — every canonical rule and hook is present, and nothing else differs;
- `customized` — nothing canonical is missing; the project added entries (named);
- `stale` — something canonical is missing: a routine rule, the `defaultMode`, a hook, or the whole `hooks` block (a project initialised before REQ-657 shows exactly that, and nothing else);
- `missing` — the file is absent.

**Every deny-tier rule the project copy lacks is named explicitly, whatever the classification** (the REQ-525 "missing principle" rule applied to the allowlist): a missing `ask` entry means a one-way move that no longer stops for a person. The Step 0a baseline rules apply: the render is made from ToolkitRoot, so when Step 0a warned that the baseline is not clean and current, downgrade every `stale` here to `unverified-baseline` (BUG-204, BUG-203).

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
python3 "$ADLC_TOOLKIT_ROOT/tools/adlc/adlc.py" harness drift --harness claude --opted-in
```

The command is read-only and exits 1 when anything is `stale` or `missing`. Its reconciliation is a re-render, never a hand copy: `adlc harness render --harness <name> --force`, naming the harness on the report's row, overwrites the file (project additions are lost, so offer it only for a `stale` file and say so), or the user adds the named missing entries by hand.

### Step 3e: Classify Each Surface's Drift Across the Pipeline (promotion state)

Per-branch results are not yet an answer. A surface stale on `main` but in sync on
`staging` needs **no new work at all** — the fix is already committed and simply has not
been promoted. Opening a sync PR for it duplicates a commit that is on its way, and
branching that PR off the wrong base can leave the pipeline with two divergent copies of
the same fix.

For each surface, fold its per-branch results into exactly one verdict. `I` = integration
branch, `D` = the default/production branch, `U` = an upstream branch (`dev`) that
receives work by reverse-sync:

| Per-branch pattern | Verdict | Correct action |
|---|---|---|
| in sync everywhere | `clean` | none |
| stale on **every** branch | `needs-sync` | one sync PR based on **`I`**, then promote normally |
| in sync on `I`, stale on `D` | **`pending-promotion`** | **no sync PR** — open/await the `I` → `D` promotion |
| in sync on `I` and `D`, stale on `U` (`dev`) | **`needs-reverse-sync`** | the project's reverse-sync path (e.g. `scripts/git/sync-staging-to-dev.sh`), **not** a hand-rolled PR |
| in sync on `D`, stale on `I` | `regression` | flag loudly — `I` is *behind* `D`, so the next promotion would undo the fix |
| absent on some branches only | `partial-missing` | report per branch; do not treat as repo-wide `missing` |
| working tree differs from its own branch | `uncommitted` | local edit — commit, revert, or explain |

Two rules that follow, and that a single-branch check cannot express:

- **Never propose a sync PR for a `pending-promotion` surface.** The commit exists; the
  gap is a promotion, not authorship.
- **Never propose a plain PR for `needs-reverse-sync`.** If the project ships a
  reverse-sync script, name it — it exists because the merge must preserve ancestry, and
  a hand-rolled squash breaks the idempotency check that script relies on.

`regression` deserves its own emphasis: it is the one pattern where doing nothing is
actively unsafe, because the pipeline is primed to *remove* a change that is currently
live.

### Step 4: Classify Template Drift as Intentional vs Accidental

(This step applies to the two **template-posture** surfaces — templates and `ethos` (Step 3c). Partials and `workflow-runtime` have no customization classification, per Step 3 / Step 3d. For `ethos`, apply these same intentional-vs-accidental signals to the *body*, but remember the missing-principle sub-check in Step 3c fires loudly regardless of how the file is classified here.)


For each drifted template, **read both full versions** (not just the diff) and make a judgment call. The goal is to separate:

**Intentional customization signals** (do NOT reconcile without explicit user consent):
- Added sections that are domain-specific to this project (e.g. `## System Model`, `## Entities`, `## Permissions`, `## Business Rules` added to a project's local `.adlc/templates/requirement-template.md`)
- Added field names in frontmatter that reference project-specific concepts
- Rewritten wording that reflects a deliberate editorial choice
- Any change that appears in `git log` with a commit message indicating project-specific intent

**Accidental staleness signals** (SHOULD reconcile):
- Toolkit added a new section or field and the project's copy is structurally older
- Cosmetic-only differences (whitespace, placeholder text like `YYYY-MM-DD` vs `[date]`)
- Toolkit renamed/removed a section that the project still has dangling
- Toolkit tightened a rule (e.g. locking a naming convention) and the project's copy still shows the old rule

When in doubt, classify as "needs human review" — do not silently reconcile.

### Step 5: Produce the Drift Report

Read `template-drift/references/drift-report.md` and follow it before you continue. It holds the report's shape: the summary covering all seven surfaces, the per-branch tables with their verdicts, and the per-file sections. Nothing in this file replaces it.

### Step 6: Offer Reconciliation Actions

Read `template-drift/references/reconciliation.md` and follow it before you continue. It holds how each Step 3e verdict is routed to an action, the numbered action list, the rule that nothing is applied without explicit approval, and how to re-verify across the branch set. Nothing in this file replaces it.

### Step 7: Recommend Follow-Up

At the end of the report:
- If all seven surfaces are in sync or intentionally customized: "All vendored surfaces (templates, partials, agents, ethos, workflow runtime, workflow tests, harness config) are in sync or intentionally customized. No action needed."
- If drift remains after user-approved actions: list what's still drifted (by surface) and suggest running `/template-drift` again after a toolkit update.
- If intentional customizations were found (templates or ethos): remind the user to update their project CLAUDE.md or a project-local NOTES file so future toolkit updates don't accidentally overwrite them during a merge.
- If a **missing ETHOS principle** was found and NOT reconciled: warn explicitly that every skill is running an outdated constitution until it is copied.

## What This Skill Does NOT Do

- It does not modify toolkit templates — changes to the canonical version go through the adlc-toolkit repo via PR.
- It does not rename or delete project template files — only copies or reports.
- It does not touch `.adlc/templates/` in other **projects** — it's scoped to the current repo. Within that repo it now reads **every pipeline branch** (Step 0), not only the checked-out one.
- It does not push, merge, or promote anything. It reports verdicts and proposes branch-correct actions; opening the sync PR, running the reverse-sync script, and merging the promotion remain the caller's steps.
- It does not check drift of skills or agents — those load from the install itself (the skills symlink, or the plugin cache), so drift is structurally impossible.

## Implementation Notes

- Use `diff -u` for readable unified diffs. Fall back to `git diff --no-index` if preferred.
- `wc -l` on the diff output is a decent proxy for drift size, but prefer counting `^+` and `^-` lines excluding the `+++`/`---` headers.
- When running under `/status`, this skill should produce a one-line summary only that still names **all seven surfaces** (e.g. "Templates: 2 drifted, 1 missing. Partials: 1 stale, 0 missing. Agents: 1 stale, 0 missing. ETHOS: drifted (1 missing principle). Workflow runtime: 1 stale. Workflow tests: 1 stale (Jest landmine). Harness config: stale (hooks missing)."). A clean surface is shown as `clean` rather than dropped (BR-3 — never silently omit a surface). Detect this mode by checking whether the argument contains `--brief`. The "Workflow tests" clause may be omitted only when no landmine files are found; the other six surfaces are always reported (clean or drifted).
- Partial comparison uses `diff -q` (quiet, exit-code-only) rather than `diff -u` because per-file unified diffs are not actionable for partials — the only remediation is "copy from toolkit". Show the diff only if the user asks for `--verbose`.
- Do not invoke `/template-drift` recursively against the adlc-toolkit's own `.adlc/` (would always report drift against itself by construction).
