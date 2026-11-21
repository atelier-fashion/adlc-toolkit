"""`architect/SKILL.md` Step 5 — the footprint-publish fence resolves
`pipeline-state.json` for THIS REQ only.

The fence resolves `state` in two tiers. With `$REQ` set it looks under
`.adlc/specs/*/<REQ>-*/`; with `$REQ` unset it takes the lone
`.adlc/specs/*/REQ-*/pipeline-state.json`. The bug this suite pins: the second
tier used to run whenever the first came back empty, so a standalone
`/architect` run for a REQ with no state (REQ-611 in teton-code) resolved to an
unrelated REQ's state (REQ-544) and would have published REQ-611's footprint
into REQ-544's draft PR.

The fence body is extracted from the real `SKILL.md` through the linter's own
fence iterator and executed verbatim in a sandbox under every shell the partial
harness drives (`bash`, `zsh`, `/bin/sh`), with `.adlc/partials/forge.sh`
replaced by a recording stub, so the assertions hold for the fence the skill
actually ships — not a copy.

Cases:
  (a) $REQ set, that REQ has no state, another REQ does  -> skip line, no PR edit
  (b) $REQ set, that REQ has state                       -> publishes to ITS PR
  (c) $REQ unset, exactly one state                      -> any-REQ fallback still publishes
  (d) $REQ unset, no state at all                        -> skip line, no PR edit

BUG-288: the fence hands the forge `$prNumber` and no other number. The state
file, which a `/sprint --exec` session writes, only says which repo the number
belongs to, so a number read from it never chooses the PR. One run publishes one
repo's footprint into one PR, and the cross-repo loop is the caller's:
  (e) $prNumber unset, or not the state file's number     -> exit 2, no PR read or edit
  (f) cross-repo, one run per repo ($REPO_ID)             -> each PR gets its own repo's lines
  (g) run from a sibling's worktree ($PRIMARY_WORKTREE)   -> the spec is found in the primary
  (h) textual pin: every forge call takes "$prNumber"
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK_PY = REPO_ROOT / "tools" / "lint-skills" / "check.py"
ARCHITECT = REPO_ROOT / "architect" / "SKILL.md"

SHELLS = [s for s in ("bash", "zsh", "/bin/sh") if shutil.which(s) or Path(s).is_file()]


def _load_check_module():
    spec = importlib.util.spec_from_file_location("_lint_check_footprint", CHECK_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_check = _load_check_module()


def _footprint_fence() -> str:
    """The one shell fence in `architect/SKILL.md` that resolves the state file
    and publishes the footprint. Asserting on exactly one match means a future
    split or duplicate of the fence fails loudly here instead of silently
    testing the wrong block."""
    text = ARCHITECT.read_text(encoding="utf-8")
    hits = []
    for _lang, _idx, _start, body in _check._iter_fences(text):
        joined = "\n".join(line for _lineno, line in body)
        if "pipeline-state.json" in joined and "adlc-footprint" in joined:
            hits.append(joined)
    assert len(hits) == 1, f"expected exactly one footprint fence, found {len(hits)}"
    return hits[0]


def _spec(cwd: Path, req: str, slug: str, pr: int | None) -> Path:
    """A spec dir for `req`; with `pr` it also gets a /proceed-shaped
    pipeline-state.json (one repo, primary, with a prNumber) and one task file
    that attributes a path, so the publish path has something to publish."""
    specdir = cwd / ".adlc" / "specs" / f"{req}-{slug}"
    (specdir / "tasks").mkdir(parents=True)
    if pr is not None:
        state = {"req": req, "repos": {"solo": {"primary": True, "prNumber": pr}}}
        (specdir / "pipeline-state.json").write_text(json.dumps(state, indent=2) + "\n")
        (specdir / "tasks" / "TASK-001.md").write_text(
            "---\nrepo: solo\n---\n"
            "## Files to Create/Modify\n"
            f"- `src/{req.lower()}.py` — the file\n"
            "## Notes\n"
        )
    return specdir


def _stage(tmp_path: Path):
    """Sandbox cwd with a recording forge stub in `.adlc/partials/forge.sh`
    (so the fence's repo-local source branch wins) and an empty `$HOME` (so the
    `~/.claude/skills/...` fallback can never reach the real machine)."""
    cwd = tmp_path / "cwd"
    (cwd / ".adlc" / "partials").mkdir(parents=True)
    (cwd / ".adlc" / "specs").mkdir()
    home = tmp_path / "home"
    home.mkdir()
    edits = tmp_path / "pr-edits"  # one line per adlc_forge_pr_edit call: "<pr>\t<body-file-copy>"
    (cwd / ".adlc" / "partials" / "forge.sh").write_text(
        "adlc_forge_pr_view() { printf '%s\\n' \"$1\" >> \"$ADLC_TEST_EDITS.views\"; "
        "printf 'Existing body\\n'; return 0; }\n"
        "adlc_forge_pr_edit() {\n"
        '  pr=$1; shift\n'
        '  while [ $# -gt 0 ]; do\n'
        '    if [ "$1" = "--body-file" ]; then bf=$2; shift; fi\n'
        '    shift\n'
        '  done\n'
        '  cp "$bf" "$ADLC_TEST_EDITS.$pr"\n'
        '  printf \'%s\\n\' "$pr" >> "$ADLC_TEST_EDITS"\n'
        "  return 0\n"
        "}\n"
    )
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home),
        "TMPDIR": str(tmp_path),
        "ADLC_TEST_EDITS": str(edits),
    }
    return cwd, env, edits


def _run(staged, shell: str, req: str | None, pr: int | str | None = None, *,
         repo: str | None = None, primary: Path | None = None, cwd: Path | None = None):
    """Run the fence verbatim under `shell`. `pr` is `$prNumber`, `repo` is
    `$REPO_ID`, `primary` is `$PRIMARY_WORKTREE`, and `cwd` is where it runs
    (the staged directory unless given)."""
    staged_cwd, env, edits = staged
    env = dict(env)
    if req is not None:
        env["REQ"] = req
    if pr is not None:
        env["prNumber"] = str(pr)
    if repo is not None:
        env["REPO_ID"] = repo
    if primary is not None:
        env["PRIMARY_WORKTREE"] = str(primary)
    run_in = cwd or staged_cwd
    script = run_in / "fence.sh"
    script.write_text(_footprint_fence() + "\n")
    proc = subprocess.run(
        [shell, str(script)], cwd=str(run_in), env=env,
        capture_output=True, text=True, timeout=60,
    )
    edited = edits.read_text().split() if edits.exists() else []
    return proc, edited, edits


def _viewed(edits: Path) -> list[str]:
    """The PR numbers `adlc_forge_pr_view` was called with."""
    views = Path(f"{edits}.views")
    return views.read_text().split() if views.exists() else []


@pytest.mark.parametrize("shell", SHELLS)
def test_req_set_without_own_state_skips_and_never_borrows_another_reqs_pr(tmp_path, shell):
    """(a) The observed bug. REQ-611 has no state; REQ-544 does and has a PR.
    The fence must print the standalone skip and exit 0 without touching #544's PR."""
    staged = _stage(tmp_path)
    cwd = staged[0]
    _spec(cwd, "REQ-544", "teton-code-charter", pr=544)
    _spec(cwd, "REQ-611", "standalone-thing", pr=None)
    proc, edited, _ = _run(staged, shell, req="REQ-611")
    assert proc.returncode == 0, proc.stderr
    assert "standalone run, skipping footprint publish" in proc.stdout, proc.stdout
    assert "REQ-611" in proc.stdout, "skip line should name the REQ it declined for"
    assert edited == [], f"fence published into another REQ's PR: {edited}"


@pytest.mark.parametrize("shell", SHELLS)
def test_req_set_with_own_state_publishes_to_its_own_pr(tmp_path, shell):
    """(b) The fix must not break the pipeline path: with REQ=REQ-544 and both
    specs present, exactly #544 is edited and the body carries 544's task path."""
    staged = _stage(tmp_path)
    cwd = staged[0]
    _spec(cwd, "REQ-544", "teton-code-charter", pr=544)
    _spec(cwd, "REQ-611", "other-with-state", pr=611)
    proc, edited, edits = _run(staged, shell, req="REQ-544", pr=544)
    assert proc.returncode == 0, proc.stderr
    assert edited == ["544"], (proc.stdout, proc.stderr)
    assert _viewed(edits) == ["544"]
    body = Path(f"{edits}.544").read_text()
    assert "```adlc-footprint" in body
    assert "solo:src/req-544.py" in body
    assert "req-611" not in body
    assert "published footprint of repo solo to PR #544" in proc.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_req_unset_falls_back_to_the_lone_state(tmp_path, shell):
    """(c) The any-REQ fallback is kept for the $REQ-unset case."""
    staged = _stage(tmp_path)
    cwd = staged[0]
    _spec(cwd, "REQ-544", "teton-code-charter", pr=544)
    proc, edited, _ = _run(staged, shell, req=None, pr=544)
    assert proc.returncode == 0, proc.stderr
    assert edited == ["544"], (proc.stdout, proc.stderr)


@pytest.mark.parametrize("shell", SHELLS)
def test_req_unset_with_no_state_skips(tmp_path, shell):
    """(d) Nothing to resolve at all -> standalone skip, exit 0, no PR edit."""
    staged = _stage(tmp_path)
    cwd = staged[0]
    _spec(cwd, "REQ-611", "standalone-thing", pr=None)
    proc, edited, _ = _run(staged, shell, req=None)
    assert proc.returncode == 0, proc.stderr
    assert "standalone run, skipping footprint publish" in proc.stdout
    assert edited == []


def test_fence_text_never_falls_through_from_req_to_any_req():
    """Textual pin, independent of execution: the any-REQ `find` must sit on an
    `else` branch of the `$REQ` test, not after it as an unconditional fallback."""
    body = _footprint_fence()
    lines = body.splitlines()
    any_req = [i for i, l in enumerate(lines) if '-path "*/REQ-*/pipeline-state.json"' in l]
    assert len(any_req) == 1, "expected exactly one any-REQ find"
    i = any_req[0]
    # Walk back to the nearest branch keyword; it must be `else`, not `fi`.
    for j in range(i - 1, -1, -1):
        stripped = lines[j].strip()
        if stripped in ("else", "fi") or stripped.startswith("if "):
            assert stripped == "else", (
                "the any-REQ find is not on the else branch of the $REQ test — "
                f"found {stripped!r} above it"
            )
            break
    else:
        raise AssertionError("no branch keyword found above the any-REQ find")


# --------------------------------------------------------------------------- BUG-288
def _cross_spec(cwd: Path) -> Path:
    """REQ-700's spec in `cwd` (the primary's worktree): two repos, `web`
    primary with PR 11 and `api` with PR 22, one task each, and one task with no
    `repo:` field, which attributes to the primary."""
    specdir = cwd / ".adlc" / "specs" / "REQ-700-cross"
    (specdir / "tasks").mkdir(parents=True)
    state = {"req": "REQ-700", "repos": {
        "web": {"primary": True, "prNumber": 11},
        "api": {"primary": False, "prNumber": 22}}}
    (specdir / "pipeline-state.json").write_text(json.dumps(state, indent=2) + "\n")
    for name, front, path in (("TASK-001", "repo: web\n", "web/app.ts"),
                              ("TASK-002", "repo: api\n", "api/routes.py"),
                              ("TASK-003", "", "web/shared.ts")):
        (specdir / "tasks" / f"{name}.md").write_text(
            f"---\n{front}---\n## Files to Create/Modify\n- `{path}` — the file\n## Notes\n")
    return specdir


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("pr", [None, "", 611, "544x", "5 44"])
def test_bug288_a_pr_number_the_state_file_does_not_record_publishes_nothing(tmp_path, shell, pr):
    """(e) The state file records PR 544 for the repo. With `$prNumber` unset,
    empty, another PR's number or not a number, the fence exits 2 with one line
    on stderr and makes no forge call at all: the state file's own number is
    never a fallback."""
    staged = _stage(tmp_path)
    _spec(staged[0], "REQ-544", "teton-code-charter", pr=544)
    proc, edited, edits = _run(staged, shell, req="REQ-544", pr=pr)
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "footprint NOT published" in proc.stderr and "#544" in proc.stderr, proc.stderr
    assert len(proc.stderr.strip().splitlines()) == 1, proc.stderr
    assert edited == [] and _viewed(edits) == [], (edited, _viewed(edits))


@pytest.mark.parametrize("shell", SHELLS)
def test_bug288_one_run_publishes_one_repo_into_the_pr_it_is_given(tmp_path, shell):
    """(f) Cross-repo: the loop is the caller's. A run with no `$REPO_ID`
    publishes the primary's lines (its own tasks and the one with no `repo:`)
    into PR 11 and nothing into PR 22; a run with `REPO_ID=api` publishes only
    `api`'s lines into PR 22. A repo's number given for the other repo is
    refused, and so is a repo the state file does not know."""
    staged = _stage(tmp_path)
    _cross_spec(staged[0])
    proc, edited, edits = _run(staged, shell, req="REQ-700", pr=11)
    assert proc.returncode == 0 and edited == ["11"], (proc.stdout, proc.stderr)
    body = Path(f"{edits}.11").read_text()
    assert "web:web/app.ts" in body and "web:web/shared.ts" in body and "api:" not in body, body
    proc, edited, edits = _run(staged, shell, req="REQ-700", pr=22, repo="api")
    assert proc.returncode == 0 and edited == ["11", "22"], (proc.stdout, proc.stderr)
    body = Path(f"{edits}.22").read_text()
    assert "api:api/routes.py" in body and "web:" not in body, body
    assert _viewed(edits) == ["11", "22"]
    proc, edited, edits = _run(staged, shell, req="REQ-700", pr=22)
    assert proc.returncode == 2 and edited == ["11", "22"], (proc.stdout, proc.stderr)
    proc, edited, edits = _run(staged, shell, req="REQ-700", pr=11, repo="api")
    assert proc.returncode == 2 and edited == ["11", "22"], (proc.stdout, proc.stderr)
    proc, edited, edits = _run(staged, shell, req="REQ-700", pr=11, repo="other")
    assert proc.returncode == 0 and "has no draft PR" in proc.stdout, (proc.stdout, proc.stderr)
    assert edited == ["11", "22"] and _viewed(edits) == ["11", "22"]


@pytest.mark.parametrize("shell", SHELLS)
def test_bug288_a_run_in_a_siblings_worktree_finds_the_spec_in_the_primary(tmp_path, shell):
    """(g) The forge adapter takes the repository from the directory the fence
    runs in, so a sibling's footprint is published from the sibling's worktree.
    The spec lives in the primary alone: `$PRIMARY_WORKTREE` names it. Without
    it the sibling's worktree holds no state, and the run skips as standalone."""
    staged = _stage(tmp_path)
    primary = staged[0]
    _cross_spec(primary)
    sibling = tmp_path / "api-worktree"
    (sibling / ".adlc" / "partials").mkdir(parents=True)
    shutil.copy(primary / ".adlc" / "partials" / "forge.sh",
                sibling / ".adlc" / "partials" / "forge.sh")
    proc, edited, edits = _run(staged, shell, req="REQ-700", pr=22, repo="api", cwd=sibling)
    assert proc.returncode == 0 and "standalone run" in proc.stdout, (proc.stdout, proc.stderr)
    assert edited == []
    proc, edited, edits = _run(staged, shell, req="REQ-700", pr=22, repo="api",
                               primary=primary, cwd=sibling)
    assert proc.returncode == 0 and edited == ["22"], (proc.stdout, proc.stderr)
    assert "api:api/routes.py" in Path(f"{edits}.22").read_text()


def test_bug288_every_forge_call_takes_the_callers_pr_number():
    """(h) Textual pin: each `adlc_forge_pr_*` call in the fence takes
    `"$prNumber"` as its first argument, the fence never assigns `prNumber`,
    and no forge call sits in a loop over the state file's lines."""
    body = _footprint_fence()
    code = [l for l in body.splitlines() if not l.lstrip().startswith("#")]
    calls = [l for l in code if "adlc_forge_pr_" in l]
    assert len(calls) == 2, calls
    for line in calls:
        for part in line.split("adlc_forge_pr_")[1:]:
            assert part.split()[1] == '"$prNumber"', line
    assert not any("prNumber=" in l for l in code), "the fence must not assign prNumber"
    assert "prnum" not in body
    assert not any("$repos_prs" in l and "| while" in l for l in code)
