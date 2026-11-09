"""fence-run: the one admitted entry point (REQ-682 BR-3, BR-5, BR-6, BR-9, BR-11, AC-5, AC-6)."""

import io
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import exec_matcher as em  # noqa: E402
import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import recording_stubs as rs  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
SHIM = os.path.join(TOOLKIT, "tools", "adlc", "fence-run")

#: A value for every argument a runner fence takes: what a well-behaved model would pass.
SAMPLES = {
    "worktree": "{cwd}", "root": "{cwd}", "spec": "{cwd}/spec.md", "state": "{cwd}/state.json",
    "tasks": "{cwd}/tasks", "integrationBranch": "main", "branch": "feat/REQ-901-thing",
    "component": "adlc/proceed", "task": "TASK-901", "mode": "", "phase": "1", "attempt": "1",
    "loops": "0", "terminal": "blocked", "reason": "", "repo": "o/r", "title": "A title",
    "pr": "101", "prNumber": "101", "id": "REQ-901", "slug": "a-slug",
    "mark": "adlc-transcript-mark-0123456789abcdef", "ids": "NO_ENTRY", "req": "REQ-901",
    "req_ids": "", "flag": "{cwd}/adlc-skill-flag.abc123", "REQ": "REQ-901", "LESSON_NUM": "901",
    "FINAL_TITLE": "A title",
}
FILE_SAMPLES = {"NEW_BODY": "A body.\n", "lane_escalated": "a reason", "MAPPER_PATHS": "a/b.py\n"}
HOSTILE = ("$(touch {s})", "`touch {s}`", "x;touch {s}", "x\ntouch {s}", "--force", "main",
           "HEAD:main", "../x", "-x")


@pytest.fixture(scope="module")
def records():
    return fc.census(TOOLKIT)


@pytest.fixture
def cached(monkeypatch, records):
    """The census once per test module: every fence-run call recomputes it otherwise, which is
    the property ``test_census_recomputed_every_call`` holds; here it only costs time."""
    real = fc.census
    memo = {}

    def census(root, adapter=None):
        if root not in memo:
            memo[root] = real(root, adapter)
        return memo[root]
    monkeypatch.setattr(fc, "census", census)
    return records


def _by_route(records, route):
    return [r for r in records if r["route"] == route]


def _run(fid, argv, cwd, environ=None, root=TOOLKIT):
    err = io.StringIO()
    env = dict(os.environ if environ is None else environ)
    rc = fr.run(fid, argv, root, environ=env, cwd=str(cwd), err=err)
    return rc, err.getvalue()


def _sample_argv(rec, cwd, hostile=None, target=None):
    argv = []
    for arg in rec["placeholders"]:
        if arg in FILE_SAMPLES:
            path = os.path.join(str(cwd), "arg-%s.txt" % arg)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(hostile if arg == target and hostile is not None else FILE_SAMPLES[arg])
            argv += ["--arg-file", "%s=%s" % (arg, os.path.basename(path))]
        else:
            value = hostile if arg == target and hostile is not None else SAMPLES[arg]
            argv += ["--arg", "%s=%s" % (arg, value.replace("{cwd}", str(cwd)))]
    return argv


@pytest.fixture
def wc(tmp_path):
    path = tmp_path / "wc"
    (path / ".adlc" / "specs").mkdir(parents=True)
    return path


# ------------------------------------------------------------------------ refusals (BR-9)
def test_refusal_is_one_loud_line_exit_3(cached, wc, tmp_path):
    sentinel = tmp_path / "S"
    direct = _by_route(cached, "direct")[0]["id"]
    engine = _by_route(cached, "engine")[0]["id"]
    excised = _by_route(cached, "excised")[0]["id"]
    runner = _by_route(cached, "runner")[0]["id"]
    stale = runner.rsplit(":", 1)[0] + ":00000000"
    for fid, why in ((direct, "route is direct"), (engine, "route is engine"),
                     (excised, "route is excised"), (stale, "changed since it was shown"),
                     ("validate/SKILL.md#99:00000000", "unknown fence"),
                     ("README.md#1:00000000", "not in the exec file set"),
                     ("x; touch %s" % sentinel, "not a fence id")):
        rc, err = _run(fid, [], wc)
        assert rc == fr.REFUSED, (fid, rc)
        lines = err.splitlines()
        assert len(lines) == 1 and lines[0].startswith("opaque_entry_refused: "), err
        assert why in lines[0], (fid, lines[0])
    assert not sentinel.exists()
    out = subprocess.run([SHIM, "run", excised], cwd=str(wc), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, universal_newlines=True)
    assert out.returncode == 3 and out.stderr.startswith("opaque_entry_refused: "), out.stderr


def test_valid_run_exits_with_fence_status(cached, wc):
    """Benign path: a valid run is the fence's own exit status, 0 or not."""
    ctx = next(r for r in cached if r["id"].startswith("validate/SKILL.md#1:"))
    rc, err = _run(ctx["id"], [], wc)
    assert rc == 0 and "opaque_entry_refused" not in err
    check = next(r for r in cached if r["id"].startswith("wrapup/SKILL.md#") and
                 r["sources"] == ["lesson-check"])
    rc, err = _run(check["id"], ["--arg", "id=901", "--arg", "slug=missing"], wc)
    assert rc not in (0, fr.REFUSED) and "opaque_entry_refused" not in err


def test_census_recomputed_every_call(monkeypatch, wc):
    calls = []
    real = fc.census

    def counting(root, adapter=None):
        calls.append(root)
        return real(root, adapter)
    monkeypatch.setattr(fc, "census", counting)
    fid = next(r["id"] for r in real(TOOLKIT) if r["route"] == "excised")
    _run(fid, [], wc)
    _run(fid, [], wc)
    assert len(calls) == 2


# ------------------------------------------------------------------------ BR-3, BR-5
def test_run_reads_only_toolkit_text(cached, wc, tmp_path):
    """A working copy's vendored partials and forge_config.py never run under the runner."""
    sentinel = tmp_path / "S"
    (wc / ".adlc" / "partials").mkdir(parents=True)
    for name in os.listdir(os.path.join(TOOLKIT, "partials")):
        if name.endswith(".sh"):
            (wc / ".adlc" / "partials" / name).write_text("touch '%s'\n" % sentinel)
    for rel in ("tools/adlc/forge_config.py", ".adlc/tools/adlc/forge_config.py"):
        (wc / rel).parent.mkdir(parents=True, exist_ok=True)
        (wc / rel).write_text("open(%r, 'w').write('x')\n" % str(sentinel))
    env = dict(os.environ, ADLC_FORGE_MOCK="1", ADLC_DISABLE_DELEGATE="1",
               ADLC_REPOS_ROOT=str(tmp_path))
    ran = 0
    for rec in _by_route(cached, "runner"):
        if not set(rec["sources"]) & {"forge", "lessons", "delegate-gate", "id-recheck"}:
            continue
        _run(rec["id"], _sample_argv(rec, wc), wc, environ=env)
        ran += 1
    assert ran >= 5
    assert not sentinel.exists()


def test_one_way_fences_refused_whatever_the_env(cached, wc):
    """No fence that reaches a one-way move is `runner`, and the refusal reads toolkit text
    only: the same under every value of ADLC_EXEC_RUN, or with it gone."""
    excised = _by_route(cached, "excised")
    assert excised
    base = dict(os.environ)
    base.pop("ADLC_EXEC_RUN", None)
    for rec in excised:
        seen = set()
        for env in (base, dict(base, ADLC_EXEC_RUN="REQ-901"), dict(base, ADLC_EXEC_RUN="other"),
                    dict(base, ADLC_EXEC_RUN="", ADLC_FENCE_TOOLKIT_ONLY="0")):
            rc, err = _run(rec["id"], [], wc, environ=env)
            assert rc == fr.REFUSED
            seen.add(err)
        assert len(seen) == 1, rec["id"]
    for rec in cached:
        assert not (rec["route"] == "runner" and "adlc_forge_pr_merge" in " ".join(
            rec.get("reach", []))), rec["id"]


def test_refusal_holds_against_env_defeats(cached, wc):
    """AC-6, runner side: nothing a caller sets survives into the fence's environment, so an
    earlier `unset`, an env prefix or a second source cannot change what the runner does.
    Claude refuses the model's side of each defeat (TASK-243's matcher, probe rows 2, 9, 13)."""
    hostile = dict(os.environ, ADLC_FENCE_TOOLKIT_ONLY="0", ADLC_TOOLKIT_ROOT="/evil",
                   ADLC_ARG_state="/evil", ADLC_ARG_x="1", CLAUDE_PLUGIN_ROOT="/evil")
    phs = [fc.PLACEHOLDERS["state"]]
    env = fr.child_env(hostile, phs, {"state": ["/ok"]}, TOOLKIT)
    assert env["ADLC_FENCE_TOOLKIT_ONLY"] == "1" and env["ADLC_TOOLKIT_ROOT"] == TOOLKIT
    assert env["ADLC_ARG_state"] == "/ok" and "ADLC_ARG_x" not in env
    echo = next(r for r in cached if r["id"].startswith("agents/pipeline-runner.md#") or
                r["id"].startswith("validate/SKILL.md#1:"))
    rc, _err = _run(echo["id"], [], wc, environ=hostile)
    assert rc == 0
    for defeat in ("unset ADLC_FENCE_TOOLKIT_ONLY; %s run x" % fr.runner_path(TOOLKIT),
                   "ADLC_FENCE_TOOLKIT_ONLY=0 %s run x" % fr.runner_path(TOOLKIT),
                   ". %s/partials/forge.sh; adlc_forge_pr_merge 1" % TOOLKIT):
        assert not em.admits({"allow": ["Bash(%s:*)" % fr.runner_path(TOOLKIT)]}, defeat)


def test_safe_forge_fences_run_under_mock(cached, wc):
    """Benign path: pr_create, pr_view and pr_edit fences run against the forge mock and
    refuse nothing."""
    env = dict(os.environ, ADLC_FORGE_MOCK="1", ADLC_DISABLE_DELEGATE="1")
    forge = [r for r in _by_route(cached, "runner") if "forge" in r["sources"] and
             r["id"].split("#")[0] in fc.PIPELINE_FILES]
    assert len(forge) >= 2
    for rec in forge:
        rc, err = _run(rec["id"], _sample_argv(rec, wc), wc, environ=env)
        assert "opaque_entry_refused" not in err, (rec["id"], err)
        assert rc == 0, (rec["id"], rc, err)


def test_azure_devops_backend_refused_under_the_runner(cached, wc, tmp_path):
    """BR-5: `az repos pr` is an exec deny, and the forge's ADO arm refuses under the flag."""
    log = str(tmp_path / "calls.jsonl")
    stubs = rs.install(str(tmp_path / "bin"), log)
    env = dict(os.environ, PATH=stubs + os.pathsep + os.environ["PATH"],
               ADLC_FORGE_PROVIDER_OVERRIDE="azure-devops", ADLC_DISABLE_DELEGATE="1")
    env.pop("ADLC_FORGE_MOCK", None)
    rec = next(r for r in _by_route(cached, "runner")
               if r["id"].startswith("proceed/phase-0-setup.md#") and "forge" in r["sources"])
    rc, _err = _run(rec["id"], _sample_argv(rec, wc), wc, environ=env)
    assert rc != 0
    assert not [c for c in rs.calls(log) if c["cmd"] == "az"]


# ------------------------------------------------------------------------ BR-6, AC-5
def test_hostile_values_never_run_code(cached, wc, tmp_path):
    """Every runner fence x every value it takes x every BR-6 hostile value: refused by its
    pattern, or bound as data. No sentinel, and no recorded argv a deny-tier rule matches."""
    sentinel = str(tmp_path / "S")
    log = str(tmp_path / "calls.jsonl")
    stubs = rs.install(str(tmp_path / "bin"), log)
    env = dict(os.environ, PATH=stubs + os.pathsep + os.environ["PATH"], ADLC_FORGE_MOCK="1",
               ADLC_DISABLE_DELEGATE="1", ADLC_REPOS_ROOT=str(tmp_path))
    import exec_adapter as ea
    adapter = ea.load("claude", TOOLKIT)
    policy = fc.exec_policy(TOOLKIT, adapter)
    cases = refused = 0
    for rec in _by_route(cached, "runner"):
        for arg in rec["placeholders"]:
            for raw in HOSTILE:
                value = raw.replace("{s}", sentinel)
                rc, err = _run(rec["id"], _sample_argv(rec, wc, value, arg), wc, environ=env)
                cases += 1
                refused += rc == fr.REFUSED and "opaque_entry_refused" in err
    assert cases > 50 and refused > 0
    assert not os.path.exists(sentinel)
    for call in rs.calls(log):
        assert not em.deny_hits(policy, rs.command_text(call)), call


def test_value_reaches_the_fence_only_as_data(tmp_path):
    """A value full of shell syntax reaches the fence byte for byte, never run."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    path = os.path.join(root, "validate", "SKILL.md")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('\n```sh\nprintf \'%s\' "$NEW_BODY"\n```\n')
    fid = [r for r in fc.census(root) if r["id"].startswith("validate/SKILL.md#")][-1]["id"]
    wc = tmp_path / "wc"
    wc.mkdir()
    sentinel = tmp_path / "S"
    value = "$(touch %s) `touch %s` ; touch %s\n'\"\\ end" % (sentinel, sentinel, sentinel)
    (wc / "body.txt").write_text(value, encoding="utf-8")
    out = subprocess.run([os.path.join(root, "tools", "adlc", "fence-run"), "run", fid,
                          "--arg-file", "NEW_BODY=body.txt"], cwd=str(wc),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout == value
    assert not sentinel.exists()


def test_arg_file_bounds(tmp_path):
    wc = tmp_path / "wc"
    wc.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    (wc / "link").symlink_to(outside)
    (wc / "dir").mkdir()
    (wc / "big").write_bytes(b"x" * (fr.MAX_ARG_FILE + 1))
    (wc / "ok").write_text("a 'quoted'\nvalue $(x)\n")
    for bad in ("../outside.txt", "link", "dir", "big", ""):
        with pytest.raises(fr.Refusal):
            fr.read_arg_file(bad, str(wc))
    assert fr.read_arg_file("ok", str(wc)) == "a 'quoted'\nvalue $(x)\n"


# ------------------------------------------------------------------------ BR-11, AC-8
def test_delegation_off_takes_fallback(tmp_path, monkeypatch):
    """With ADLC_DISABLE_DELEGATE=1, or no opt-in, a delegating fence takes its fallback,
    and the runner adds no ADLC_DELEGATE_* variable to the fence's environment."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    path = os.path.join(root, "validate", "SKILL.md")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n```sh\n" + fc.ROOT_LINE + "\nif [ -f .adlc/partials/delegate-gate.sh ]; then "
                 ". .adlc/partials/delegate-gate.sh; else . \"$ADLC_TOOLKIT_ROOT/partials/"
                 "delegate-gate.sh\"; fi\nadlc_delegate_gate_check; printf 'gate=%s\\n' \"$?\"\n```\n")
    fid = [r for r in fc.census(root) if r["id"].startswith("validate/SKILL.md#")][-1]["id"]
    wc = tmp_path / "wc"
    wc.mkdir()
    base = {k: v for k, v in os.environ.items()
            if not k.startswith("ADLC_DELEGATE") and k not in ("KIMI_API_KEY", "MOONSHOT_API_KEY")}
    shim = os.path.join(root, "tools", "adlc", "fence-run")
    for env in (dict(base, ADLC_DISABLE_DELEGATE="1"), base):
        out = subprocess.run([shim, "run", fid], cwd=str(wc), env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() in ("gate=1", "gate=2"), out.stdout
    env = fr.child_env(base, [], {}, root)
    assert not [k for k in env if k.startswith("ADLC_DELEGATE")]


# ------------------------------------------------------------------------ show
def test_show_refuses_outside_the_set_and_rewrites_fences(cached, capsys):
    err = io.StringIO()
    assert fr.show("README.md", TOOLKIT, err=err) == fr.REFUSED
    assert err.getvalue().startswith("opaque_entry_refused: show README.md:")
    assert fr.show("validate/SKILL.md", TOOLKIT) == 0
    out = capsys.readouterr().out
    for rec in cached:
        if rec["id"].startswith("validate/SKILL.md#") and rec["route"] == "runner":
            assert "%s run %s" % (fr.runner_path(TOOLKIT), rec["id"]) in out
    assert "\n" + fr.runner_path(TOOLKIT) + " run " in out          # unquoted absolute root
    assert "if [ -f .adlc/partials/" not in out
    assert not [ln for ln in out.split("\n") if ln.startswith("!")]
    assert fr.show("proceed/phases-lite.md", TOOLKIT) == 0
    assert "     ls -t .adlc/knowledge/lessons\n" in capsys.readouterr().out


def test_root_outside_the_charset_refuses_to_start(monkeypatch):
    monkeypatch.setattr(fr.tkr, "toolkit_root", lambda: "/a b/tk")
    err = io.StringIO()
    assert fr.main(["show", "validate/SKILL.md"], err=err) == fr.REFUSED
    assert "cannot match" in err.getvalue()


def test_path_values_stay_in_the_working_copy_or_a_spec_dir(cached, wc, tmp_path):
    """A path value cannot aim a fence's write or read outside the working copy (BUG-265):
    a state file must sit under it, or be a REQ spec directory's pipeline-state.json."""
    r2 = next(r for r in cached if r["id"].startswith("proceed/phases-telemetry.md#2:"))
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n")
    for bad in (str(outside), "/etc/hosts", str(tmp_path / "x" / ".adlc" / "specs" / "REQ-901-a"
                                                 / "settings.json")):
        rc, err = _run(r2["id"], ["--arg", "state=%s" % bad, "--arg", "phase=1",
                                  "--arg", "attempt=1"], wc)
        assert rc == fr.REFUSED and "outside the working directory" in err, (bad, err)
    assert outside.read_text() == "{}\n"
    spec_dir = tmp_path / "primary" / ".adlc" / "specs" / "REQ-901-a-thing"
    spec_dir.mkdir(parents=True)
    (spec_dir / "pipeline-state.json").write_text("{}\n")
    rc, err = _run(r2["id"], ["--arg", "state=%s" % (spec_dir / "pipeline-state.json"),
                              "--arg", "phase=1", "--arg", "attempt=1"], wc)
    assert rc == 0, err
    assert "validateAttempts" in (spec_dir / "pipeline-state.json").read_text()
