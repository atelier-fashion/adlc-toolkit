#!/usr/bin/env python3
"""exec_prompt — the bytes an exec run delivers on stdin (REQ-659 BR-6, BR-7, BR-14, BR-24).

The prompt is derived from skills that change every week, so it fails closed. Each
excision is a heading-to-delimiter cut, and each rewrite an ``(old, new)`` pair whose
``old`` must occur exactly once: a changed sentence stops the launch and fails the test,
naming the anchor, rather than leaving a merge instruction in front of an unattended
model. The scan then reads the final bytes.

Every allowlist is a full-line regex, never a substring and never a line number, so an
edit that shifts lines neither hides a new mention nor strands an old one.

Sources are read from the toolkit install and the primary path, never a working copy
(BR-17). The one ``!`` line is replaced by its text, not run. Standard library only.
"""

import os
import re

PIPELINE_SOURCES = ("proceed/phases-state.md", "proceed/phases-telemetry.md",
                    "proceed/phase-0-setup.md", "proceed/phases-1-3-validation.md",
                    "proceed/phase-4-implementation.md", "proceed/phases-6-8-ship.md",
                    "proceed/phases-lite.md")

#: Tokens no prompt may hold, with an empty allowlist (BR-24).
EMPTY_ALLOWLIST = ("adlc_forge_pr_merge", "gh pr merge", "az repos pr", "you own the merge",
                   "report `merged`", "pr-ready", "{merged")
#: The close-out prompt's further tokens (BR-14), plus the stored deploy command.
CLOSEOUT_EMPTY = ("worktree remove", "branch -D", "--force-with-lease", "./deploy.sh",
                  "terraform apply", "terraform destroy")

ETHOS_LINE = re.compile(r"^!`test -s \.adlc/ETHOS\.md && cat \.adlc/ETHOS\.md .*`$")

#: token -> full-line regexes that may carry it, pipeline prompt.
PIPELINE_ALLOW = {
    "/wrapup": (
        r"\*\*Applies when\*\*: Running `/proceed`, `/wrapup`, or any multi-phase skill\..*",
        r"- Strip a `--full` flag from the argument before any REQ-id parsing "
        r"\(the `/wrapup --close-out` precedent\)\..*",
        r"actor — `/wrapup --close-out` writes `status: \"ok\"`; the orchestrator that invoked it",
        r"flag; `lessonsWritten` the `/wrapup` lesson outcome \(recorded at the end of its Step 4\).*",
        r"4\. \*\*Determine the integration branch, then fetch it in each touched repo\.\*\*.*"
        r"`/wrapup`, `/template-drift`.*",
        r"   # /wrapup call sites\. Derivation \+ renumber message live in partials/id-recheck\.sh\.",
        r"   \*\*Then stamp the harness \(REQ-648 BR-10\)\*\*: .*even when `/wrapup` or `/sprint`.*",
        r"   were: they are the record of what triage decided, and `/wrapup`'s escalation",
    ),
    "worktree remove": (
        r"       git -C '<repo-path>' worktree remove '<path>' .*",
    ),
}

#: The close-out prompt's: log prefixes and mentions, each anchored on its own content.
CLOSEOUT_ALLOW = {
    "/wrapup": (
        r"The target is the argument: whatever follows `/wrapup` in the invocation .*",
        r"Close-out mode exists for the actor that \*\*performed a merge it did not implement\*\*.*",
        r"   - `repos\[<id>\]\.merged = true` for every touched repo whose PR is merged .*",
        r"- Name files: `ASSUME-xxx-slug\.md`\. Determine the next ID .*",
        r"  The reservation is PER-REPO scoped \(BR-12\): .*",
        r"   \*\*A miss refuses; it never falls back\.\*\* .*",
        r"           command \"\$ADLC_READ_BIN\" --no-warn --paths \"\$TMPFILE\" --question .*",
        r"           echo \"/wrapup: .*",
        r"           case \"\$ADLC_READ_BIN\" in .*",
        r"   Capture stdout as the draft\. \*\*If `adlc-read` exits non-zero\*\*.*",
        r"6\. The success line `/wrapup: Lessons Learned drafted via the delegate` is emitted .*",
        r"- Emit `/wrapup: adlc-read unavailable — Claude drafting lesson directly` to stderr.*",
        r"A /wrapup lesson has a contrast only when a Phase-5 finding or a failing test backs it.*",
        r"- \*\*Allocate the next ID atomically via the global .*",
        r"- \*\*rc 0\*\* — the lesson passes\. On the delegated path, .*",
        r"Step 4's lesson outcome is now settled: .*",
    ),
}


class PromptBuildError(ValueError):
    """An anchor did not match, or a source is missing: nothing launches."""


class PromptRefused(ValueError):
    """The scan found a token: nothing launches (BR-24)."""

    def __init__(self, token, lineno, line):
        ValueError.__init__(self, "prompt refused: %r at line %d: %s"
                            % (token, lineno, line.strip()[:160]))
        self.token = token
        self.lineno = lineno
        self.line = line


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise PromptBuildError("cannot read %s: %s" % (rel, exc))


def strip_frontmatter(text):
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5:].lstrip("\n")
    return text


def rewrite(text, rel, pairs):
    """Apply ``(old, new)`` pairs, each of which must occur exactly once."""
    for old, new in pairs:
        count = text.count(old)
        if count != 1:
            raise PromptBuildError("%s: anchor matched %d times, expected once: %s"
                                   % (rel, count, old[:90]))
        text = text.replace(old, new)
    return text


def cut_lines(text, rel, start, end=None):
    """Remove from the line equal to or starting with ``start`` up to ``end``.

    ``end`` is a predicate on a line: the first line after ``start`` for which it holds
    survives. With none the cut runs to the end of the text.
    """
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if ln == start or ln.startswith(start)]
    if len(hits) != 1:
        raise PromptBuildError("%s: section anchor matched %d times, expected once: %s"
                               % (rel, len(hits), start[:90]))
    first = hits[0]
    last = len(lines)
    if end is not None:
        for i in range(first + 1, len(lines)):
            if end(lines[i]):
                last = i
                break
        else:
            raise PromptBuildError("%s: no end for section %s" % (rel, start[:90]))
    return "\n".join(lines[:first] + lines[last:])


GATE_TEXT = """### The merge gate

**Gate**: `currentPhase` must be `8` and `7` must be in `completedPhases`.

You stop here, before any trial merge. The orchestrator that launched you performs every
one-way move after an operator approves it: you never merge, deploy, force-push or remove a
worktree, in either topology.

1. On a REQ still on the lite lane, run **The lane check** (`proceed/phases-lite.md`) first, so
   the halted state already reflects it. A failure escalates.
2. Write `status: "awaiting_approval"` and this `approval` object to `pipeline-state.json`:
   `{ "action": "merge", "repos": [<every touched repo id>], "prs": [<every touched repo's PR
   url>], "deploy": <true when the spec says deployable, else false>, "requestedAt": "<now>" }`.
   Everything you write there is display data: the orchestrator recomputes what it will do.
3. Do **not** append `8` to `completedPhases`, leave `completed` at `false`, and never set
   `repos[<id>].merged`. Those belong to the actors that perform the steps.
4. Exit. The first line of your final report is `Terminal state: awaiting_approval`, and it
   carries your Phase-5 findings, task list and PR URLs, which the close-out will draw on.

Your terminal vocabulary is `{awaiting_approval, blocked, failed}`. A blocker that needs a human
ends `blocked`, with `blockers` populated. Anything past automatic recovery ends `failed`, with
the detail in `notes`.
"""

_SKILL_PAIRS = (
    ("3. **Merge conflicts during rebase** (Phase 8 / wrapup) — surface conflicts and wait.",
     "3. **Merge conflicts during the Phase 7 rebase** — surface conflicts and stop."),
    ("# Merge order for Phase 8 when this repo is primary. If omitted, defaults to",
     "# Merge order when this repo is primary. If omitted, defaults to"),
    ("touched/untouched repos, prune untouched-sibling worktrees, rebuild",
     "touched/untouched repos, leave untouched-sibling working copies in place (the\n"
     "orchestrator removes them at cleanup), rebuild"),
    ("the **authoritative** gate is Phase 8 pre-merge.",
     "the **authoritative** gate is the orchestrator's, at approval."),
)

_STATE_PAIRS = (
    ("`mergeOrder` is the list of touched repo ids in the order Phase 8 will merge them",
     "`mergeOrder` is the list of touched repo ids in the order the orchestrator will merge them"),
    ("7. **Per-repo writes during Phases 6–8**: when a PR is created, write its URL to "
     "`repos[id].prUrl`. When a PR merges, set `repos[id].merged = true`. These writes let a "
     "mid-Phase-8 interruption resume merges in order without double-merging.",
     "7. **Per-repo writes during Phases 6–7**: when a PR is created, write its URL to "
     "`repos[id].prUrl`. Never write `repos[id].merged`: the orchestrator does."),
    ("8. **On completion**: After Phase 8 (Wrapup) finishes, set `\"completed\": true` in the "
     "state file.",
     "8. **At the merge gate**: leave `\"completed\"` at `false`. The actors after you write it."),
)

_TELEMETRY_PAIRS = (
    ("engine (`solo` for a direct `/proceed`, `legacy` in subagent mode), a halt token,",
     "engine (`exec` in this run), a halt token,"),
    ("**R5 — the line itself.** Run it once at each terminal this run reaches: after\n"
     "Step 8b for `merged`, after Step 8c's note for `pr-ready`, at each legitimate\n"
     "halt before you stop (`blocked`, with the halt's token below), and on a `failed`\n"
     "terminal. A resumed run that reaches another terminal emits again; readers keep\n"
     "the latest line per REQ.",
     "**R5 — the line itself.** Run it at each legitimate halt before you stop\n"
     "(`blocked`, with the halt's token below) and on a `failed` terminal. The merge\n"
     "gate is not a terminal, so it writes no line."),
    ("--terminal <merged|pr-ready|blocked|failed> --engine <solo|legacy> --reason",
     "--terminal <blocked|failed> --engine exec --reason"),
)

_PHASE0_PAIRS = (
    ("Post-Phase-2, untouched repos will be marked `touched: false` and their worktrees removed.",
     "Post-Phase-2, untouched repos will be marked `touched: false`, and the orchestrator "
     "removes their working copies at cleanup."),
    ("`integrationBranch` is the value resolved in step 4 — Phase 6 (PR base) and Phase 8 "
     "(merge target) MUST read it from state, never re-derive or assume `main`.",
     "`integrationBranch` is the value resolved in step 4 — Phase 6 (PR base) MUST read it from "
     "state, never re-derive or assume `main`."),
)

_VALIDATION_PAIRS = (
    ("set `touched: false` and remove its worktree using the absolute path recorded in state: "
     "`git -C <repo-path> worktree remove <repos[<id>].worktree>`.",
     "set `touched: false` and rebuild `mergeOrder`; leave the working copy in place, the "
     "orchestrator removes it at cleanup."),
)

_SHIP_PAIRS = (
    ("# /proceed — Phases 6–8: Ship", "# /proceed — Phases 6–7: Ship"),
    ("into PRs (one per touched repo), sanity-check each PR, then merge in\n"
     "configured order, deploy, and capture knowledge via `/wrapup`. SKILL.md\n"
     "keeps a one-paragraph summary of each; the per-step PR body templates,\n"
     "merge sequencing, and terminal-state contract live here.",
     "into PRs (one per touched repo), sanity-check each PR, then stop at the\n"
     "merge gate. SKILL.md keeps a one-paragraph summary of each; the per-step\n"
     "PR body templates live here."),
    ("**Lite lane (REQ-652):** these phases run on a lite REQ too, with three\n"
     "differences, all detailed in `proceed/phases-lite.md`: Phase 6 uses the lite PR\n"
     "body (a `## Lane` section, no Tasks, Architecture or Reflection sections); Phase\n"
     "7 re-runs the lane check if it added commits; Phase 8 re-runs the lane check\n"
     "immediately before the trial-merge gate. A failed check escalates (or, for a\n"
     "forced-lite REQ in a solo run, is legitimate halt #4).",
     "**Lite lane (REQ-652):** these phases run on a lite REQ too, with three\n"
     "differences, all detailed in `proceed/phases-lite.md`: Phase 6 uses the lite PR\n"
     "body (a `## Lane` section, no Tasks, Architecture or Reflection sections); Phase\n"
     "7 re-runs the lane check if it added commits; the check runs last, immediately\n"
     "before `awaiting_approval` is written. A failed check escalates."),
    ("Continue to Phase 8 immediately.", "Continue to the merge gate immediately."),
)

_LITE_PAIRS = (
    ("  → Phase 8 (+ lane check before the trial merge) → /wrapup",
     "  → lane check → `awaiting_approval` (the merge gate)"),
    ("| Phase 8, immediately before the trial-merge gate | always; it is cheap and idempotent |\n"
     "| Phase 8, after any conflict-resolution commit | always, together with the trial-merge "
     "gate it re-runs |",
     "| Immediately before `awaiting_approval` is written | always; it is cheap and idempotent |"),
    ("because Phase 8 merges the remote head and a check of anything else certifies",
     "because the orchestrator merges the remote head and a check of anything else certifies"),
    ("non-primary repo: set `touched: false`, remove its worktree with the absolute\n"
     "   path from state, and skip its draft PR; rebuild `mergeOrder` as the primary\n"
     "   alone. If an escalation's Phase 2 later puts a task in a sibling, Phase 2's\n"
     "   reconcile step marks it touched again; create its worktree then exactly as\n"
     "   Step 0 item 5 does.",
     "non-primary repo: set `touched: false`, leave its working copy in place, the\n"
     "   orchestrator removes it at cleanup, and skip its draft PR; rebuild `mergeOrder`\n"
     "   as the primary alone. If an escalation's Phase 2 later puts a task in a sibling,\n"
     "   Phase 2's reconcile step marks it touched again."),
    ("### Phases 6–8 on the lite lane", "### Phases 6–7 on the lite lane"),
    ("- **Phase 8**: run **The lane check** immediately before the pre-merge\n"
     "  trial-merge gate. `/wrapup` then runs as usual; it writes an escalation\n"
     "  lesson only for a REQ that escalated (BR-14).",
     "- **The merge gate**: run **The lane check** immediately before\n"
     "  `awaiting_approval` is written."),
)

_PAIRS = {"proceed/phases-state.md": _STATE_PAIRS, "proceed/phases-telemetry.md": _TELEMETRY_PAIRS,
          "proceed/phase-0-setup.md": _PHASE0_PAIRS,
          "proceed/phases-1-3-validation.md": _VALIDATION_PAIRS,
          "proceed/phases-6-8-ship.md": _SHIP_PAIRS, "proceed/phases-lite.md": _LITE_PAIRS}

_UNATTENDED_PAIRS = (
    ("You are in SUBAGENT MODE — execute all phases sequentially, do not dispatch sub-agents.\n",
     ""),
    ("Use the WORKTREE PATH above verbatim for `git worktree add` in Phase 0. All later phases",
     "The orchestrator has created that worktree on branch `{branch}`, so Step 0 item 4b takes "
     "its same-branch reuse path; you never run `git worktree add`. All later phases"),
    ("The only sanctioned operation against the parent repo path is `gh pr merge` in Phase 8 "
     "single-repo topology; every other read/write/cd belongs inside the worktree. (See "
     "`agents/pipeline-runner.md` \"Worktree Isolation\" section for the canonical rules.)",
     "No operation against the parent repo path is sanctioned in this run; every read, write "
     "and cd belongs inside the worktree."),
    ("Follow all /proceed phases (0-8) exactly as documented.",
     "Follow all /proceed phases (0-7) exactly as documented."),
    ("Phase 8 merge ownership follows REQ topology: single-repo REQs — you own the merge and "
     "report `merged`. Cross-repo REQs — stop after Phase 7 and report `pr-ready` so the "
     "orchestrator can sequence merges per `mergeOrder`. Your final report MUST lead with one "
     "of `{merged, pr-ready, blocked, failed}`.",
     "You never merge. Stop at the merge gate; your final report MUST lead with "
     "`Terminal state: <awaiting_approval|blocked|failed>`."),
)

_EXEC_NOTES = """The argument to this pipeline is {req}, on branch `{branch}`.
Every companion file the text names is inlined in this prompt, so do not look for them on disk.
`git -C` is not on your allowlist: where the text writes `git -C <worktree> <command>`, run `<command>` from your working copy.
"""


def ethos_text(toolkit, primary):
    """The primary path's vendored ETHOS, else the toolkit's own (BR-17)."""
    for path in (os.path.join(primary, ".adlc", "ETHOS.md"), os.path.join(toolkit, "ETHOS.md")):
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if text.strip():
            return text
    raise PromptBuildError("no ETHOS text at the primary path or in the toolkit")


def _render_bang_lines(text, rel):
    out = []
    for line in text.split("\n"):
        if line.startswith("!"):
            if not ETHOS_LINE.match(line):
                raise PromptBuildError("%s: a `!` line the engine does not render: %s"
                                       % (rel, line[:90]))
            out.append("(The ETHOS text is at the top of this prompt.)")
        else:
            out.append(line)
    return "\n".join(out)


def _proceed_body(toolkit):
    rel = "proceed/SKILL.md"
    text = strip_frontmatter(_read(toolkit, rel))
    text = _render_bang_lines(text, rel)
    text = rewrite(text, rel, _SKILL_PAIRS)
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if ln == "### Phase 8: Wrapup"]
    if len(hits) != 1:
        raise PromptBuildError("%s: the Phase 8 heading matched %d times" % (rel, len(hits)))
    end = next((i for i in range(hits[0] + 1, len(lines)) if lines[i] == "---"), None)
    if end is None:
        raise PromptBuildError("%s: no delimiter after Phase 8" % rel)
    lines[hits[0]:end] = GATE_TEXT.split("\n")
    text = "\n".join(lines)
    text = cut_lines(text, rel, "- **Merge conflicts**: If any feature branch has conflicts",
                     lambda ln: not ln.startswith("- **Merge conflicts**"))
    text = rewrite(text, rel, (("- **Partial merge recovery**: If the pipeline is interrupted "
                                "mid-Phase-8, resume by reading `pipeline-state.json` — the merge "
                                "loop walks `mergeOrder` and skips any repo where `merged: true`.",
                                "- **Merge conflicts**: A conflict at the Phase 7 rebase stops the "
                                "run: record it in `blockers` and stop. You never resolve one."),))
    return text


def _companion(toolkit, rel):
    text = strip_frontmatter(_read(toolkit, rel))
    text = rewrite(text, rel, _PAIRS.get(rel, ()))
    if rel == "proceed/phases-6-8-ship.md":
        marker = "\n---\n\n### Phase 8: Wrapup\n"
        if text.count(marker) != 1:
            raise PromptBuildError("%s: the Phase 8 section anchor moved" % rel)
        text = text[:text.index(marker)] + "\n"
    if rel == "proceed/phase-0-setup.md":
        text = cut_lines(text, rel, "9. When the pipeline completes",
                         lambda ln: ln.startswith("**Preflight verified**"))
    if rel == "proceed/phases-telemetry.md":
        text = cut_lines(text, rel, "**R4 — carry the run's state**",
                         lambda ln: ln.startswith("**R5 — the line itself.**"))
        text = rewrite(text, rel, (("R1 to R5; each is run where that step says",
                                    "R1 to R5, R4 being the orchestrator's; each is run where "
                                    "that step says"),))
    return text


def unattended_block(toolkit, req, branch, repo_path, worktree):
    rel = "sprint/SKILL.md"
    text = _read(toolkit, rel)
    match = re.search(r"^```\nWORKTREE PATH \(mandatory\): <absolute-path>\n\n(.*?)^```$", text,
                      re.M | re.S)
    if match is None:
        raise PromptBuildError("%s: the dispatch block moved" % rel)
    block = match.group(1)
    pairs = [(old, new.replace("{branch}", branch)) for old, new in _UNATTENDED_PAIRS]
    block = rewrite(block, rel, pairs)
    block = rewrite(block, rel, (("Run the /proceed skill for REQ-xxx in the repository at "
                                  "[current repo path].",
                                  "Run the /proceed pipeline below for %s in the repository at %s."
                                  % (req, repo_path)),))
    head = "WORKTREE PATH (mandatory): %s\n\n" % worktree
    notes = _EXEC_NOTES.replace("{req}", req).replace("{branch}", branch)
    return head + block + notes


def scan(text, kind="pipeline", extra_tokens=()):
    """Every refused ``(token, lineno, line)`` in ``text`` (BR-24)."""
    allow = PIPELINE_ALLOW if kind == "pipeline" else CLOSEOUT_ALLOW
    empty = EMPTY_ALLOWLIST + (CLOSEOUT_EMPTY if kind == "close-out" else ()) + tuple(extra_tokens)
    compiled = {t: [re.compile(r) for r in rs] for t, rs in allow.items()}
    hits = []
    for lineno, line in enumerate(text.split("\n"), 1):
        if line.startswith("!"):
            hits.append(("!", lineno, line))
        for token in empty:
            if token and token in line:
                hits.append((token, lineno, line))
        for token, regexes in compiled.items():
            if token in line and not any(r.fullmatch(line) for r in regexes):
                hits.append((token, lineno, line))
    return hits


def _finish(text, kind, extra_tokens=()):
    hits = scan(text, kind, extra_tokens)
    if hits:
        raise PromptRefused(*hits[0])
    return text.encode("utf-8")


def pipeline_prompt(toolkit, primary, req, branch, repo_path, worktree, answer=None):
    """The exact bytes of a first launch, or of an ``answer`` relaunch (BR-6, BR-14)."""
    parts = [ethos_text(toolkit, primary), _proceed_body(toolkit)]
    for rel in PIPELINE_SOURCES:
        parts.append("<!-- %s -->\n%s" % (rel, _companion(toolkit, rel)))
    parts.append(unattended_block(toolkit, req, branch, repo_path, worktree))
    if answer is not None:
        parts.append("This is a relaunch of a run that ended `blocked`. Read "
                     "`pipeline-state.json` and resume from its `currentPhase`. The operator's "
                     "answer:\n\n--- BEGIN OPERATOR ANSWER ---\n%s\n--- END OPERATOR ANSWER ---\n"
                     % answer)
    return _finish("\n\n".join(parts), "pipeline")


_CLOSEOUT_PAIRS = (
    ("push; open a PR through `adlc_forge_pr_create` titled the same; merge it with "
     "`adlc_forge_pr_merge <url> --squash --delete-branch` and check `branch_deleted` (BUG-195). "
     "Lesson ids were allocated and rechecked in Step 4, so this push is collision-safe. The "
     "caller removes the close-out worktree afterwards. If the chore PR cannot be merged (policy, "
     "conflict), leave it open, report its URL, and exit non-zero so the caller records "
     "`closeOut.status: failed`.",
     "push; open the chore PR via `adlc_forge_pr_create`, titled the same, then stop, reporting "
     "line 1 `Terminal state: closed-out` and line 2 `Chore PR: <url>`. Lesson ids were allocated "
     "and rechecked in Step 4, so this push is collision-safe. The orchestrator gates and merges "
     "the chore PR and removes the close-out worktree."),
    ("In close-out mode the summary is the mode's return value and the skill ends after the "
     "close-out commit (Close-out mode rules 5–6); Steps 6–8 below do not run.",
     "In close-out mode the summary is the mode's return value and the skill ends after the "
     "close-out commit (Close-out mode rules 5–6)."),
)


def _section(text, heading, level):
    """One section by its exact heading, up to the next heading at ``level`` or above."""
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if ln == heading]
    if len(hits) != 1:
        raise PromptBuildError("wrapup/SKILL.md: heading matched %d times: %s"
                               % (len(hits), heading))
    pat = re.compile(r"^#{1,%d} " % level)
    fence = False
    out = [lines[hits[0]]]
    for line in lines[hits[0] + 1:]:
        if line.startswith("```"):
            fence = not fence
        if not fence and pat.match(line):
            break
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def closeout_prompt(toolkit, req, branch, worktree, evidence, deploy_command=""):
    """The resumed close-out's bytes, built by section (BR-14)."""
    rel = "wrapup/SKILL.md"
    text = strip_frontmatter(_read(toolkit, rel))
    sections = [_section(text, "## Context", 2), _section(text, "## Input", 2),
                _section(text, "## Prerequisites", 2),
                _section(text, "## Close-out mode (`--close-out`)", 2),
                _section(text, "### Step 1: Identify the Feature", 3),
                _section(text, "### Step 3: Update ADLC Artifact Statuses", 3),
                _section(text, "### Step 4: Capture Knowledge", 3),
                _section(text, "### Step 5: Generate Ship Summary", 3)]
    body = rewrite("\n".join(sections), rel, _CLOSEOUT_PAIRS)
    body = re.sub(r"\n#* ?### Step [2678]\b", "\n", body)
    head = ("WORKTREE PATH (mandatory): %s\n\nYou are resuming this REQ's own session. Run "
            "the close-out mode below for %s (the argument carries `--close-out`), in that "
            "worktree, on branch `%s`, which the orchestrator created from the integration "
            "branch. It is unattended: no operator is present. You never merge.\n\n"
            % (worktree, req, branch))
    tail = "\n--- RUN EVIDENCE ---\n%s\n--- END RUN EVIDENCE ---\n" % evidence
    tokens = (deploy_command,) if deploy_command else ()
    return _finish(head + body + tail, "close-out", tokens)
