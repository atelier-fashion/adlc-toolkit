"""REQ-666: skill text that means the same thing on every harness.

Executed, not just read (LESSON-329): the fences these tests pull out of the
shipped SKILL.md files run under every shell the toolkit supports, in this repo
and in a bare consumer.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools" / "lint-skills"))
import check as _check  # noqa: E402

# REQ-661 BR-6: the placeholder comes from the one constant `companion-templating`
# matches, so this test and the check cannot name different tokens.
REQUEST_PLACEHOLDER = "'" + _check.ARGUMENT_PLACEHOLDERS[0] + "'"
SHELLS = [s for s in ("bash", "zsh", "sh", "dash") if shutil.which(s)]
SKILLS = sorted(p for p in REPO_ROOT.glob("*/SKILL.md"))


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _fences(text: str):
    """Yield ``(opening_line_index, dedented_body_lines)`` for every ```sh fence,
    indented or not (list-item fences are indented in /spec)."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)```(?:sh|bash)\s*$", lines[i])
        if not m:
            i += 1
            continue
        indent, start, body = m.group(1), i, []
        i += 1
        while i < len(lines) and lines[i].strip() != "```":
            line = lines[i]
            body.append(line[len(indent):] if line.startswith(indent) else line.lstrip())
            i += 1
        yield start, body
        i += 1


def _single_quote(value: str) -> str:
    """conventions.md 'Bash in skills', "Substituting a value into a fence"."""
    return "'" + value.replace("'", "'\\''") + "'"


def _sandbox(tmp_path: Path, *, vendored: bool) -> tuple[Path, dict]:
    """A consumer checkout under ``tmp_path`` and an environment whose HOME holds
    no toolkit, so a fence reads only what the consumer vendored."""
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if vendored:
        shutil.copytree(REPO_ROOT / "partials", repo / ".adlc" / "partials")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ADLC_", "CLAUDE_"))}
    env["HOME"] = str(home)
    return repo, env


# --- BR-1 / AC-1, AC-2: the argument is prose ------------------------------

def test_no_arguments_placeholder():
    """AC-1: no SKILL.md names `$ARGUMENTS` (bare or braced), and no bare
    `$<digit>` either, so the `${1}`/`$(0)` dodges are intact."""
    for skill in SKILLS:
        text = skill.read_text(encoding="utf-8")
        rel = skill.relative_to(REPO_ROOT)
        assert not re.search(r"\$\{?ARGUMENTS", text), rel
        assert not re.search(r"(?<!\$)\$[0-9]", text), rel


def _spec_gate_fence() -> list[str]:
    text = _read("spec/SKILL.md")
    for _start, body in _fences(text):
        if any(f"adlc_intake_detect {REQUEST_PLACEHOLDER}; gate=$?" in line for line in body):
            return body
    raise AssertionError("/spec Step 1.4's gate fence with the '<request>' placeholder is gone")


HOSTILE = "Fix the `date` call in $HOME/app and $(id) -- it's broken"


@pytest.mark.parametrize("shell", SHELLS)
def test_spec_intake_gate_takes_a_hostile_literal(tmp_path, shell):
    """AC-2: the request, substituted by the rule, reaches the detector intact
    and an ordinary request is not intake (`intake_gate=1`) on every shell."""
    repo, env = _sandbox(tmp_path, vendored=True)
    script = "\n".join(_spec_gate_fence()).replace(REQUEST_PLACEHOLDER, _single_quote(HOSTILE))
    out = subprocess.run([shell, "-c", script], cwd=repo, env=env,
                         capture_output=True, text=True, timeout=60)
    assert "intake_gate=1" in out.stdout, (out.stdout, out.stderr)
    assert out.returncode == 0, out.stderr


@pytest.mark.parametrize("shell", SHELLS[:1])
def test_unescaped_apostrophe_breaks_the_probe(tmp_path, shell):
    """The contrast that makes the rule load-bearing: the same request
    single-quoted without the escape never reaches the detector."""
    repo, env = _sandbox(tmp_path, vendored=True)
    script = "\n".join(_spec_gate_fence()).replace(REQUEST_PLACEHOLDER, "'" + HOSTILE + "'")
    out = subprocess.run([shell, "-c", script], cwd=repo, env=env,
                         capture_output=True, text=True, timeout=60)
    assert "intake_gate=" not in out.stdout, out.stdout


def test_lane_flag_prose_is_kept():
    """AC-2: /spec still reads and strips --lite/--full itself, and still stops
    when both are passed, before any id is allocated."""
    text = _read("spec/SKILL.md")
    assert "Lane flags — read and strip these before anything else" in text
    assert "--lite and --full are mutually exclusive" in text


# --- BR-5 / AC-5: the retired harness surface is gone --------------------

# Spelled in pieces so this file is not itself a hit.
_REPO_NAME = "tet" + "on-code"
_RETIRED = re.compile("|".join([
    "tet" + "on", "provenance-" + "safe", "provenance-" + "classifying", "harness-" + "skip",
]), re.IGNORECASE)
# The repo-name residue BR-5 lists, plus the dataset scrub (REQ-671), which names
# the repository as a scrub target.
_REPO_NAME_FILES = {
    "template-drift/SKILL.md", "agents/pipeline-runner.md", "partials/README.md",
    "partials/conflict-bound.sh", "partials/tests/conflict-bound.test.sh",
    "tools/lint-skills/tests/test_architect_footprint_state.py",
    "tools/dataset/denylist.json", "tools/dataset/detectors.py",
}


def test_retired_harness_surface_is_gone():
    """AC-5: outside the repo-name lines, nothing in skills, agents, partials,
    tools or the README names the retired harness, its checks or its markers."""
    hits = []
    roots = list(REPO_ROOT.glob("*/SKILL.md")) + [REPO_ROOT / "README.md"]
    for top in ("agents", "partials", "tools"):
        roots += [p for p in (REPO_ROOT / top).rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    for path in roots:
        rel = str(path.relative_to(REPO_ROOT))
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not _RETIRED.search(line):
                continue
            if rel in _REPO_NAME_FILES and (_REPO_NAME in line.lower() or rel.startswith("tools/dataset/")):
                continue
            hits.append(f"{rel}:{n}")
    assert hits == []
    # Non-vacuous: the repo-name lines are really there and really scanned.
    assert _REPO_NAME in _read("template-drift/SKILL.md")
    check = _read("tools/lint-skills/check.py")
    assert "check_" + "harness_skip" not in check
    assert "check_" + "provenance_safe_fence" not in check
    assert "missing-" + "harness-line" not in check


# --- BR-2, BR-15, BR-16 / AC-3: one run-and-read context fence per skill ----

CONTEXT_MARKER = "# adlc-context"
NO_CONTEXT = {"adversary", "init", "proceed"}  # had no non-ETHOS preamble line


def _context_fences(text: str) -> list[list[str]]:
    return [body for _s, body in _fences(text) if body and body[0].strip() == CONTEXT_MARKER]


def test_each_skill_has_one_context_fence():
    """AC-3: the 14 skills that loaded context through preamble lines carry one
    `# adlc-context` fence each, under `## Context`; the rest carry none."""
    for skill in SKILLS:
        name = skill.parent.name
        text = skill.read_text(encoding="utf-8")
        fences = _context_fences(text)
        if name in NO_CONTEXT:
            assert fences == [], name
            continue
        assert len(fences) == 1, name
        context = text.index("## Context")
        assert context < text.index(CONTEXT_MARKER) < text.index("## Input"), name


def _stub_path(tmp_path: Path) -> str:
    """A PATH whose `gcloud` fails fast, so /canary's reads never reach a network."""
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "gcloud").write_text("#!/bin/sh\nexit 1\n")
    (stub / "gcloud").chmod(0o755)
    return f"{stub}{os.pathsep}{os.environ.get('PATH', '')}"


_NOTICE_RE = re.compile(r"^(?:cat|ls|test -[sf]) (\.adlc\S*).*\|\| echo '([^']*)'$")


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("where", ["repo", "consumer"])
def test_context_fences_run_everywhere(tmp_path, shell, where):
    """BR-2/BR-16: every context fence exits 0 under every shell, in this repo
    and in a bare consumer with no `.adlc/` at all, where each absent file's
    notice is printed instead of an error."""
    repo, env = _sandbox(tmp_path, vendored=False)
    env["PATH"] = _stub_path(tmp_path)
    cwd = REPO_ROOT if where == "repo" else repo
    ran = 0
    for skill in SKILLS:
        for body in _context_fences(skill.read_text(encoding="utf-8")):
            out = subprocess.run([shell, "-c", "\n".join(body)], cwd=cwd, env=env,
                                 capture_output=True, text=True, timeout=60)
            assert out.returncode == 0, (skill, shell, out.stderr)
            ran += 1
            if where == "consumer":
                for line in body:
                    m = _NOTICE_RE.match(line.strip())
                    if m:
                        assert m.group(2) in out.stdout, (skill, m.group(1), out.stdout)
    assert ran == len(SKILLS) - len(NO_CONTEXT)


def _allow_entries() -> list[str]:
    import json
    data = json.loads(_read("templates/claude-settings-template.json"))
    out = []
    for entry in data["permissions"]["allow"]:
        m = re.match(r"^Bash\((.*?)(?::\*)?\)$", entry)
        if m:
            out.append(m.group(1))
    return out


def test_context_commands_are_allowlisted():
    """BR-15: every command a context fence runs is pre-approved by the settings
    template, so no skill invocation gains a prompt. The root line in
    /template-drift's fence is the one every toolkit fence already carries."""
    allow = _allow_entries()
    for skill in SKILLS:
        for body in _context_fences(skill.read_text(encoding="utf-8")):
            for line in body[1:]:
                line = line.strip()
                if not line or line.startswith("ADLC_TOOLKIT_ROOT="):
                    continue
                for segment in re.split(r"\s*(?:&&|\|\|)\s*", line):
                    cmd = re.sub(r"\s*\d?>[>&]?\s*/dev/null", "", segment).strip()
                    assert any(cmd == a or cmd.startswith(a + " ") for a in allow), (skill.parent.name, cmd)


# --- BR-8, BR-9 / AC-8: agents vendored by /init, drift reported ------------

def _fence_after(rel: str, heading: str, needle: str) -> str:
    text = _read(rel)
    start = text.index(heading)
    for line_idx, body in _fences(text):
        if sum(len(x) + 1 for x in text.split("\n")[:line_idx]) < start:
            continue
        if any(needle in line for line in body):
            return "\n".join(body)
    raise AssertionError(f"{rel}: no fence after {heading!r} holding {needle!r}")


@pytest.mark.parametrize("shell", [s for s in SHELLS if s in ("bash", "zsh")])
def test_init_vendors_agents_and_drift_reports_them(tmp_path, shell):
    """AC-8: /init's Step 6 copy creates one `.adlc/agents/` file per
    `agents/*.md`; /template-drift Step 3f reports them synced, an edited one
    stale, and every one missing, naming /init, once the directory is gone."""
    repo, env = _sandbox(tmp_path, vendored=False)
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)  # the root line's first arm: ToolkitRoot = this tree
    init = _fence_after("init/SKILL.md", "### Step 6:", 'cp "$ADLC_TOOLKIT_ROOT/agents"/*.md .adlc/agents/')
    drift = _fence_after("template-drift/SKILL.md", "### Step 3f:", ".adlc/agents/$agent_md")

    def run(script):
        out = subprocess.run([shell, "-c", script], cwd=repo, env=env,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return out.stdout.splitlines()

    run(init)
    agents = sorted(p.name for p in (REPO_ROOT / "agents").glob("*.md"))
    assert sorted(p.name for p in (repo / ".adlc" / "agents").glob("*.md")) == agents
    assert run(drift) == [f"{a}: synced" for a in agents]

    edited = repo / ".adlc" / "agents" / agents[0]
    edited.write_text(edited.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")
    lines = run(drift)
    assert lines[0].startswith(f"{agents[0]}: stale")
    assert lines[1:] == [f"{a}: synced" for a in agents[1:]]

    (repo / ".adlc" / "agents" / "rogue.md").write_text("x\n", encoding="utf-8")
    assert "rogue.md: missing upstream" in "\n".join(run(drift))

    shutil.rmtree(repo / ".adlc" / "agents")
    lines = run(drift)
    assert len(lines) == len(agents)
    assert all(": missing" in ln and "/init" in ln for ln in lines), lines


# --- BR-6, BR-14, BR-17 / AC-6, AC-15: the docs moved with the code ---------

NEW_CHECKS = ("ethos-line", "description-budget", "skills-ref", "dispatch-has-fallback", "no-harness-path")
RETIRED_CHECKS = ("harness-" + "skip", "provenance-" + "safe-fence", "missing-" + "harness-line")


def test_lint_readme_lists_new_checks_only():
    """BR-14: the README's numbered list documents the five new checks and none
    of the retired ones, numbered without a gap."""
    readme = _read("tools/lint-skills/README.md")
    section = readme[readme.index("## What it checks"):readme.index("## Usage")]
    numbers = [int(n) for n in re.findall(r"^(\d+)\. \*\*", section, flags=re.M)]
    assert numbers == list(range(1, len(numbers) + 1)), numbers
    names = set(re.findall(r"^\d+\. \*\*[^*]+\(`([a-z-]+)`\)", section, flags=re.M))
    for check in NEW_CHECKS:
        assert check in names, check
    for check in RETIRED_CHECKS:
        assert check not in readme, check


def test_docs_describe_the_new_shapes():
    """AC-15: architecture.md and conventions.md describe the context block, the
    Input prose and the dispatch paragraph, and carry no paragraph about the
    retired harness."""
    arch = _read(".adlc/context/architecture.md")
    conv = _read(".adlc/context/conventions.md")
    for doc in (arch, conv):
        assert "# adlc-context" in doc
        assert not re.search("tet" + "on", doc, re.IGNORECASE)
        assert "provenance-" + "classifying" not in doc
    assert "**Input**: prose saying the argument is whatever follows the skill name" in arch
    assert "Substituting a value into a fence" in conv
    assert "<!-- dispatch-fallback-sentence -->" in conv and "<!-- dispatch-requires-subagents -->" in conv
    assert ".adlc/agents/" in arch


def test_changelog_names_reversals():
    """AC-6: the entry names each reversed decision and tells consumers to
    re-run /init."""
    log = _read("CHANGELOG.md")
    section = log[log.index("### Reversed decisions (REQ-666 BR-6)"):]
    section = section[:section.index("\n### ", 5)]
    for decision in ("BUG-228", "BUG-230", "REQ-646 BR-15", "REQ-648 BR-3"):
        assert decision in section, decision
    assert "Re-run `/init`" in section
