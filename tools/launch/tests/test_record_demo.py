"""The recording script, with fake ``asciinema``, ``agg`` and ``gh`` (REQ-672 BR-4, ADR-6, TASK-282).

No recording is made and no real binary answers. ``record_demo.py`` runs as a child with
``PATH`` set to the fakes' directory plus ``/usr/bin:/bin`` (a directory of those holding
a banned name is mirrored without it), and each test reads the fakes' own logs. The fake
``asciinema`` answers ``--version`` with the version the test chose, and never runs the
command ``rec`` is given: it writes a synthetic 400-second cast (v2, or v3 when the test
says) that holds the fake login, a temp path and a home path in its header, and writes the
driver status the test chose. The fake ``agg`` writes a GIF of the size the test chose,
sparse so a large one costs nothing. The fake ``gh`` answers ``api user`` with
:data:`LOGIN`, which must appear in no output and no file the script writes.

These tests show the script's refusals, post-processing and both-or-neither writing. They
do not show that a real recording passes, nor what a real asciinema prints or writes: only
the maintainer's run shows that (LESSON-899).
"""
import json
import os
import pathlib
import re
import shlex
import shutil
import stat
import subprocess
import sys

import pytest

import fakes
import quickstart_steps as qs
import record_demo as rd
import recording_check as rc

SCRIPT = os.path.join(rd.HERE, "record_demo.py")
#: The repository holding this file, found from it: a run must never write its docs pair.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
LOGIN = "fake-login-123"
REPO = LOGIN + "/adlc-demo-e2e"
MODEL_CANARY = "canary-model-credential-0001"
GH_CANARY = "canary-github-credential-0002"

#: What every fake does first: read its config, then log its argv and environment names.
PREAMBLE = r'''
import json
import os
import shutil
import sys

with open(@CONFIG@, encoding="utf-8") as handle:
    CONFIG = json.load(handle)
ARGS = sys.argv[1:]
with open(os.path.join(CONFIG["state"], "@NAME@.log"), "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": ARGS, "env": sorted(os.environ)}) + "\n")
'''

ASCIINEMA = r'''
if ARGS == ["--version"]:
    sys.stdout.write(CONFIG["version"] + "\n")
    sys.exit(CONFIG["version_exit"])
if (len(ARGS) < 5 or ARGS[:2] != ["rec", "--overwrite"] or ARGS[-3] != "--command"
        or ARGS[2:-3] not in ([], ["--output-format", "asciicast-v2"])):
    sys.stderr.write("fake asciinema: unexpected call\n")
    sys.exit(3)
with open(ARGS[-1], "w", encoding="utf-8") as handle:
    handle.write(CONFIG["cast"])
if CONFIG["status"] is not None:
    with open(os.environ[CONFIG["status_var"]], "w", encoding="utf-8") as handle:
        handle.write(CONFIG["status"] + "\n")
sys.exit(CONFIG["exit"])
'''

AGG = r'''
if len(ARGS) != 2 or not os.path.isfile(ARGS[0]):
    sys.stderr.write("fake agg: unexpected call\n")
    sys.exit(3)
shutil.copyfile(ARGS[0], os.path.join(CONFIG["state"], "agg-input.cast"))
with open(ARGS[1], "wb") as handle:
    handle.write(b"GIF89a")
    handle.truncate(CONFIG["size"])
sys.exit(CONFIG["exit"])
'''

GH = r'''
if ARGS == ["api", "user", "-q", ".login"] and CONFIG["exit"] == 0:
    sys.stdout.write(CONFIG["login"] + "\n")
    sys.exit(0)
sys.stderr.write("fake gh: no answer\n")
sys.exit(CONFIG["exit"] or 4)
'''


def install_fake(bin_dir, state, name, source, config):
    config_path = os.path.join(str(state), name + ".config.json")
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(dict(config, state=str(state)), handle)
    path = os.path.join(str(bin_dir), name)
    script = (PREAMBLE + source).replace("@CONFIG@", repr(config_path)).replace("@NAME@", name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("#!%s\n" % sys.executable + script)
    os.chmod(path, 0o755)


def home_path(*rest):
    """A macOS home-directory path, built so that this file holds none."""
    return "/".join(["", "Users", "someone"] + list(rest))


def line_text(step, line, login, extra):
    if (step, line) in extra:
        return extra[(step, line)]
    if line == 0:
        return "\x1b[1m$ step %d\x1b[0m\r\n" % step
    special = {
        (2, 3): "remote: https://github.com/%s/adlc-demo-e2e/pull/1\r\n" % login,
        (3, 1): "To https://github.com/" + login[:8],     # the login split across two events
        (3, 2): login[8:] + "/adlc-demo-e2e.git\r\n",
        (4, 5): "working in /tmp/adlc-quickstart-e2e.k2j3/work/adlc-quickstart\r\n",
        (5, 7): "Successfully installed plugin: adlc@adlc-toolkit\r\n",
    }
    return special.get((step, line), "\x1b[32mline %d of step %d\x1b[0m\r\n" % (line, step))


def raw_recording(login=LOGIN, extra=None):
    """``(header, events)``: 400 seconds, ten steps of a 10-second idle wait then twenty
    lines 1.5 seconds apart; the header holds the command line, a home path and the login."""
    header = {"version": 2, "width": 100, "height": 30, "timestamp": 1763856000,
              "command": "sh -c " + home_path("adlc-toolkit", "quickstart_e2e.py") + " " + login,
              "title": login + " quickstart", "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"}}
    events, clock = [], 0.0
    for step in range(10):
        for line in range(21):
            clock += 10.0 if line == 0 else 1.5
            events.append((round(clock, 6), "o", line_text(step, line, login, extra or {})))
    return header, events


def cast_text(header, events):
    return "".join(json.dumps(item) + "\n" for item in [header] + [list(e) for e in events])


def v3_text(header, events):
    """The same recording as asciinema 3 writes it by default: asciicast v3, ``term`` in
    the header, times as intervals, a comment line and an exit event."""
    head = {key: value for key, value in header.items() if key not in ("width", "height")}
    head.update(version=3, term={"cols": header["width"], "rows": header["height"],
                                 "type": header["env"]["TERM"]})
    starts = [0.0] + [time for time, _, _ in events]
    lines = [json.dumps([round(time - start, 6), code, data])
             for start, (time, code, data) in zip(starts, events)]
    return "\n".join([json.dumps(head), "# made by the fake"] + lines + ['[0.5, "x", "0"]']) + "\n"


def joined(events):
    return "".join(data for _, code, data in events if code == "o")


def repo_recording():
    """The repository's own ``docs/demo.cast`` and ``docs/demo.gif``: bytes, or None."""
    paths = [pathlib.Path(REPO_ROOT, "docs", name) for name in ("demo.cast", "demo.gif")]
    return [path.read_bytes() if os.path.lexists(str(path)) else None for path in paths]


class Rig(object):
    """The fakes on an offline PATH, an output and a temp directory, canary credentials."""

    def __init__(self, tmp_path, missing=(), cast=None, status="0", asciinema_exit=0,
                 gif_size=4096, agg_exit=0, login=LOGIN, gh_exit=0, version="asciinema 2.4.0",
                 version_exit=0):
        self.tmp, self.repo_before = tmp_path, repo_recording()
        self.bin, self.state, self.out, self.tmpdir = (
            tmp_path / name for name in ("bin", "state", "out", "tmpdir"))
        for folder in (self.bin, self.state, self.out, self.tmpdir):
            folder.mkdir(parents=True)
        self.raw = cast_text(*raw_recording()) if cast is None else cast
        fakes_ = {"asciinema": (ASCIINEMA, {"cast": self.raw, "status": status,
                                            "exit": asciinema_exit, "status_var": rd.STATUS_VAR,
                                            "version": version, "version_exit": version_exit}),
                  "agg": (AGG, {"size": gif_size, "exit": agg_exit}),
                  "gh": (GH, {"login": login, "exit": gh_exit})}
        for name, (source, config) in fakes_.items():
            if name not in missing:
                install_fake(self.bin, self.state, name, source, config)
        path = fakes.offline_path(self.bin, tmp_path / "mirror")
        for name in fakes_:
            assert (shutil.which(name, path=path) is None) == (name in missing), name
        self.env = {"PATH": path, "HOME": os.environ["HOME"], "LANG": "en_US.UTF-8",
                    "TMPDIR": str(self.tmpdir), "ANTHROPIC_API_KEY": MODEL_CANARY,
                    "GH_TOKEN": GH_CANARY}

    def run(self, *args, **env):
        merged = {k: v for k, v in dict(self.env, **env).items() if v is not None}
        done = subprocess.run([sys.executable, SCRIPT] + list(args), cwd=str(self.tmp),
                              env=merged, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
        self.output = done.stdout + done.stderr
        for secret in (MODEL_CANARY, GH_CANARY, LOGIN):
            assert secret not in self.output
        return done

    def full(self, *extra, **env):
        return self.run("--with-model", "--throwaway-repo", REPO, "--out-dir", str(self.out),
                        *extra, **env)

    def log(self, name):
        return fakes.read_log(self.state, name)

    def recs(self):
        """The fake asciinema's ``rec`` calls, without its ``--version`` calls."""
        return [call for call in self.log("asciinema") if call["argv"][:1] == ["rec"]]

    def written(self):
        """Every file the script left in the output and temp directories."""
        found = []
        for folder in (self.out, self.tmpdir):
            for root, _, files in os.walk(str(folder)):
                found += [os.path.join(root, name) for name in files]
        return found


def assert_nothing_written(rig):
    assert rig.written() == []
    assert rig.log("agg") == []
    assert repo_recording() == rig.repo_before, "the repository's docs pair was written"


def keep_target(rig, kind):
    """A ``--keep-raw`` target of ``kind`` the script must refuse."""
    target = rig.tmp / "keep" / "sub" / "raw.cast"
    if kind != "no-dir":
        target.parent.mkdir(parents=True)
    if kind == "symlink":
        (rig.tmp / "aim").write_text("aim\n", encoding="utf-8")
    if kind in ("symlink", "dangling"):
        os.symlink(str(rig.tmp / "aim"), str(target))
    elif kind == "exists":
        target.write_text("kept before\n", encoding="utf-8")
    elif kind == "git-dir":
        (rig.tmp / "keep" / ".git").mkdir()
    elif kind == "git-file":
        (rig.tmp / "keep" / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    return target


NO_VERSION = "cannot tell asciinema's version"
COLLIDES = "collides with the page's own text"


@pytest.mark.parametrize("change, said, ran", [
    ({"rig": {"missing": ("asciinema", "agg")}, "args": []}, "asciinema is not on PATH", ""),
    ({"rig": {"missing": ("asciinema",)}}, "asciinema is not on PATH", ""),
    ({"rig": {"missing": ("agg",)}}, "agg is not on PATH", ""),
    ({"args": ["--throwaway-repo", REPO]}, "pass --with-model to opt in", ""),
    ({"args": ["--with-model"]}, "pass --throwaway-repo OWNER/NAME", ""),
    ({"args": ["--with-model", "--throwaway-repo", "acme/not-a-test"]}, "must contain 'e2e'", ""),
    ({"args": ["--with-model", "--throwaway-repo", "no-slash-e2e"]}, "is not OWNER/NAME", ""),
    ({"env": {"ANTHROPIC_API_KEY": None}}, "no model credential", ""),
    ({"env": {"GH_TOKEN": None}}, "GH_TOKEN is not set", ""),
    ({"out": "missing"}, "is not a directory", ""),
    ({"keep": "exists"}, "exists: the raw cast is only written to a new file", ""),
    ({"keep": "symlink"}, "is a symlink", ""),
    ({"keep": "dangling"}, "is a symlink", ""),
    ({"keep": "git-dir"}, "is inside a git work tree", ""),
    ({"keep": "git-file"}, "is inside a git work tree", ""),
    ({"keep": "no-dir"}, "its directory does not exist", ""),
    ({"repo_owner": "page"}, "the throwaway repo's owner " + COLLIDES, ""),
    ({"rig": {"missing": ("gh",)}}, "gh is not on PATH", ""),
    ({"rig": {"version": "asciinema"}}, NO_VERSION, "version"),
    ({"rig": {"version": "a recorder"}}, NO_VERSION, "version"),
    ({"rig": {"version": ""}}, NO_VERSION, "version"),
    ({"rig": {"version": "asciinema 3.0.0", "version_exit": 1}}, NO_VERSION, "version"),
    ({"rig": {"gh_exit": 1}}, "cannot read your GitHub login", "version gh"),
    ({"rig": {"login": "not a login!"}}, "cannot read your GitHub login", "version gh"),
    ({"rig": {"login": ""}}, "cannot read your GitHub login", "version gh"),
    ({"rig": {"login": "ada"}}, "your gh login " + COLLIDES, "version gh"),
    ({"rig": {"login": "ADA"}}, "your gh login " + COLLIDES, "version gh"),
])
def test_a_refusal_records_nothing(tmp_path, change, said, ran):
    """BR-4: exit 2, one line saying why, before ``rec`` runs, nothing written. Tools are
    checked first, then the opt-in, the repo and the credentials; then a --keep-raw target
    that exists, is a symlink or sits in a git work tree; an asciinema whose version cannot
    be read; and a login or owner that is a word on the page (``Ada`` is), never printed."""
    rig = Rig(tmp_path, **change.get("rig", {}))
    repo = REPO
    if change.get("repo_owner") == "page":
        # The owner the page's own step 1 names, read at run time.
        repo = qs.load()[0].text.split()[-1].split("/")[0] + "/adlc-e2e-check"
    args = change.get("args", ["--with-model", "--throwaway-repo", repo])
    if change.get("keep"):
        args = args + ["--keep-raw", str(keep_target(rig, change["keep"]))]
    out = str(rig.tmp / "missing") if change.get("out") else str(rig.out)
    done = rig.run(*(args + ["--out-dir", out]), **change.get("env", {}))
    assert done.returncode == 2 and done.stdout == "", rig.output
    lines = done.stderr.splitlines()
    assert len(lines) == 1 and lines[0].startswith("record-demo: refused, nothing recorded: ")
    assert said in lines[0], lines
    assert rig.recs() == []
    assert len(rig.log("asciinema")) == ran.count("version")
    assert len(rig.log("gh")) == ran.count("gh")
    login = change.get("rig", {}).get("login")
    if login == "ada":
        assert any(rd.owner_pattern(login).search(step.text) for step in qs.load())
    assert not login or login.lower() not in rig.output.lower(), "the login is printed"
    if change.get("keep") == "exists":
        kept = rig.tmp / "keep" / "sub" / "raw.cast"
        assert kept.read_text(encoding="utf-8") == "kept before\n"
    if change.get("keep") in ("symlink", "dangling"):
        assert os.listdir(str(rig.tmp / "keep" / "sub")) == ["raw.cast"]
        assert os.path.lexists(str(rig.tmp / "aim")) == (change["keep"] == "symlink")
    assert_nothing_written(rig)


def test_a_login_inside_a_longer_page_word_is_not_a_collision(tmp_path):
    """The login is matched as a whole word: one that is only part of a word the page and
    the recording hold is neither refused nor a ``forbidden`` hit."""
    steps = qs.load()
    word = max(re.findall(r"[a-z]+", steps[0].text), key=len)
    login = word[:-1]
    assert len(login) >= 4 and not any(rd.owner_pattern(login).search(s.text) for s in steps)
    extra = {(6, 2): "$ " + steps[0].text + "\r\n"}
    rig = Rig(tmp_path, login=login, cast=cast_text(*raw_recording(extra=extra)))
    done = rig.full()
    assert done.returncode == 0, rig.output
    assert word in joined(rc.load_cast(str(rig.out / "demo.cast"))[1])
    assert rd.owner_pattern is rc.word_pattern, "one matcher replaces and forbids"


def test_writes_the_cast_and_gif_only_after_the_checks_pass(tmp_path):
    """The happy path: recorded, post-processed, checked, rendered, written as a pair."""
    rig = Rig(tmp_path)
    done = rig.full()
    assert done.returncode == 0, rig.output
    cast, gif = str(rig.out / "demo.cast"), str(rig.out / "demo.gif")
    assert sorted(rig.written()) == [cast, gif]
    assert done.stdout.splitlines() == ["record-demo: wrote %s (%d bytes) and %s (4096 bytes): "
                                        "58.00s, 210 events" % (cast, os.path.getsize(cast), gif)]
    assert repo_recording() == rig.repo_before
    # asciinema recorded the driver in --demo mode, passing the options through.
    assert [c["argv"] for c in rig.log("asciinema")][0] == ["--version"]
    (call,) = rig.recs()
    assert call["argv"][:3] == ["rec", "--overwrite", "--command"]
    command = call["argv"][3]
    assert shlex.split(command.split(";")[0]) == [
        sys.executable, os.path.join(rd.HERE, "quickstart_e2e.py"), "--demo", "--with-model",
        "--throwaway-repo", REPO]
    assert command.endswith('; s=$?; echo "$s" > "$%s"; exit "$s"' % rd.STATUS_VAR)
    assert os.path.dirname(os.path.dirname(call["argv"][4])) == str(rig.tmpdir)
    assert {"ANTHROPIC_API_KEY", "GH_TOKEN", rd.STATUS_VAR} <= set(call["env"])
    assert [c["argv"] for c in rig.log("gh")] == [["api", "user", "-q", ".login"]]
    # agg rendered the processed cast, which is what was written.
    (render,) = rig.log("agg")
    assert os.path.basename(render["argv"][0]) == "demo.cast"
    with open(str(rig.state / "agg-input.cast"), encoding="utf-8") as handle:
        assert handle.read() == pathlib.Path(cast).read_text(encoding="utf-8")
    # The written pair passes every check, the login forbidden.
    assert rc.check(cast, gif, forbid=[LOGIN]) == []
    header, events = rc.load_cast(cast)
    raw_header, raw_events = raw_recording()
    assert header == {"version": 2, "width": 100, "height": 30, "timestamp": 1763856000,
                      "env": {"TERM": "xterm-256color"}, "duration": 58.0}
    assert joined(events) == rd.owner_pattern(LOGIN).sub(rd.PLACEHOLDER_OWNER, joined(raw_events))
    for path in rig.written():
        with open(path, "rb") as handle:
            holds_login = LOGIN.encode() in handle.read()
        assert not holds_login, path


@pytest.mark.parametrize("case", ["home-path", "credential", "denylist", "forbidden", "gif-size"])
def test_a_failing_check_writes_neither_file(tmp_path, case):
    secret = {"home-path": home_path("notes.txt"), "credential": "gh" + "p_" + "A1b2" * 9,
              "forbidden": LOGIN[:8] + "\x1b[1m" + LOGIN[8:] + "\x1b[0m"}.get(case, "")
    if case == "denylist":
        secret = rc.load_denylist().repos[0].name  # read at run time, never printed
    extra = {(6, 2): "see " + secret + "\r\n"} if secret else {}
    rig = Rig(tmp_path, cast=cast_text(*raw_recording(extra=extra)),
              gif_size=rc.MAX_BYTES + 1 if case == "gif-size" else 4096)
    done = rig.full()
    assert done.returncode == 1, rig.output
    assert "FAIL %s: " % case in done.stderr
    assert done.stderr.rstrip().endswith("the recording failed a check: nothing written")
    echoed = bool(secret) and secret.lower() in rig.output.lower()
    assert not echoed, "the failure echoes what it matched"
    assert all(line.startswith("record-demo: ") for line in done.stderr.splitlines())
    assert rig.written() == []
    assert repo_recording() == rig.repo_before
    assert len(rig.log("agg")) == (1 if case == "gif-size" else 0)


@pytest.mark.parametrize("asciinema_exit, status, ok", [
    (0, "0", True), (1, "1", False), (0, "2", False), (0, None, False), (0, "garbage", False),
    (2, "0", False),
])
def test_the_driver_status_decides(tmp_path, asciinema_exit, status, ok):
    """Exit 0 from both asciinema and the driver's status file, or nothing is written.
    A missing or garbled status is unknown, never a pass (LESSON-581)."""
    rig = Rig(tmp_path, status=status, asciinema_exit=asciinema_exit)
    done = rig.full()
    if ok:
        assert done.returncode == 0, rig.output
        assert len(rig.written()) == 2 and repo_recording() == rig.repo_before
    else:
        assert done.returncode == 1, rig.output
        assert "did not pass" in done.stderr and "nothing written" in done.stderr
        assert_nothing_written(rig)


def test_a_recording_that_is_not_a_v2_or_v3_cast_writes_nothing(tmp_path):
    cast = '{"version": 1, "width": 100, "height": 30}\n[0.5, "o", "x"]\n'
    rig = Rig(tmp_path, cast=cast)
    done = rig.full()
    assert done.returncode == 1, rig.output
    assert "cannot use the recording: line 1: the header's version is not 2 or 3" in done.stderr
    assert_nothing_written(rig)


@pytest.mark.parametrize("version, flag, v3", [
    ("asciinema 2.4.0", [], False),
    ("asciinema 3.0.0", ["--output-format", "asciicast-v2"], False),
    ("asciinema 3.1.2", ["--output-format", "asciicast-v2"], True),
])
def test_the_cast_format_follows_the_asciinema_version(tmp_path, version, flag, v3):
    """asciinema 3 writes asciicast v3 unless told otherwise, so 3 and later are asked for
    v2 and 2.x is not; a v3 cast written anyway comes out as the same v2 cast."""
    raw = raw_recording()
    rig = Rig(tmp_path, version=version, cast=v3_text(*raw) if v3 else None)
    done = rig.full()
    assert done.returncode == 0, rig.output
    (call,) = rig.recs()
    assert call["argv"][:-3] == ["rec", "--overwrite"] + flag
    assert rc.load_cast(str(rig.out / "demo.cast")) == rd.postprocess(*raw, owner=LOGIN)


def test_keep_raw_and_the_options_passed_to_the_driver(tmp_path):
    rig = Rig(tmp_path)
    kept, marketplace = rig.tmp / "raw-kept.cast", rig.tmp / "clone"
    marketplace.mkdir()
    done = rig.full("--keep-raw", str(kept), "--model", "fake-model", "--marketplace",
                    str(marketplace))
    assert done.returncode == 0, rig.output
    assert kept.read_text(encoding="utf-8") == rig.raw
    assert stat.S_IMODE(os.lstat(str(kept)).st_mode) == 0o600
    assert ("record-demo: the unprocessed cast is kept at %s: it holds your GitHub account name "
            "and absolute paths, so it must not be committed or shared" % kept
            ) in done.stderr.splitlines()
    command = rig.recs()[0]["argv"][3]
    assert shlex.split(command.split(";")[0])[2:] == [
        "--demo", "--with-model", "--throwaway-repo", REPO, "--marketplace", str(marketplace),
        "--model", "fake-model"]


def test_recorded_command_writes_the_driver_status(tmp_path, monkeypatch):
    """The wrapper asciinema runs writes the driver's exit status, and exits with it."""
    driver = tmp_path / "driver.py"
    driver.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    monkeypatch.setattr(rd, "DRIVER", str(driver))
    (tmp_path / "bin").mkdir()
    status = tmp_path / "status"
    done = subprocess.run(["/bin/sh", "-c", rd.recorded_command(["--demo"])], env={
        "PATH": fakes.offline_path(tmp_path / "bin", tmp_path / "mirror"),
        rd.STATUS_VAR: str(status)}, stdin=subprocess.DEVNULL, timeout=60)
    assert done.returncode == 3
    assert status.read_text(encoding="utf-8") == "3\n"
    assert rd.driver_status(str(status)) == 3
    assert rd.driver_status(str(tmp_path / "none")) is None


def test_postprocess_fits_a_400_second_cast_into_60_seconds():
    """AC: idle gaps capped, times scaled to 60 s or less and kept in order, the owner
    replaced, and the output text otherwise the same."""
    header, events = raw_recording()
    assert rc.duration(events) == 400.0
    new_header, new_events = rd.postprocess(header, events, owner=LOGIN)
    assert (header, events) == raw_recording()  # pure: the inputs are unchanged
    assert rc.duration(new_events) == new_header["duration"] == 58.0
    times = [time for time, _, _ in new_events]
    assert times == sorted(times) and len(new_events) == len(events)
    assert [code for _, code, _ in new_events] == [code for _, code, _ in events]
    # Capped at 2 s, then all scaled by 58/320: no gap is longer than a capped idle wait.
    gaps = [b - a for a, b in zip([0.0] + times, times)]
    assert max(gaps) <= 2.0 * 58.0 / 320.0 + 1e-6
    assert joined(new_events) == joined(events).replace(LOGIN, rd.PLACEHOLDER_OWNER)
    assert LOGIN not in joined(new_events) and LOGIN in joined(events)


def test_postprocess_caps_idle_gaps_and_leaves_a_short_cast_unscaled():
    events = [(0.5, "o", "a"), (30.5, "o", "b"), (30.7, "o", "c"), (35.7, "r", "80x24")]
    header, new_events = rd.postprocess({"version": 2, "width": 80, "height": 24}, events)
    assert [time for time, _, _ in new_events] == [0.5, 2.5, 2.7, 4.7]
    assert header == {"version": 2, "width": 80, "height": 24, "duration": 4.7}
    assert rd.postprocess(header, [])[0]["duration"] == 0.0


def test_the_owner_is_replaced_exactly_across_event_boundaries():
    pattern = rd.owner_pattern(LOGIN)
    datas = ["To fake-log", "in-123/repo and FAKE-LOGIN-123", "", " xfake-login-123 fake-login-1234"]
    out = rd.replace_joined(datas, pattern, "your-github-user")
    assert out == ["To your-github-user", "/repo and your-github-user", "",
                   " xfake-login-123 fake-login-1234"]
    assert "".join(out) == pattern.sub("your-github-user", "".join(datas))
    events = [(1.0, "o", "by fake-"), (1.5, "i", "fake-login-123"), (2.0, "o", "login-123\r\n")]
    _, new = rd.postprocess({"version": 2, "width": 80, "height": 24}, events, owner=LOGIN)
    assert [data for _, _, data in new] == ["by your-github-user", "your-github-user", "\r\n"]


@pytest.mark.parametrize("previous", [False, True])
def test_install_writes_both_or_neither(tmp_path, monkeypatch, previous):
    """When the second move fails, the first is undone: the old pair is restored, or the
    directory is left as it was, with no temp or backup file."""
    source, out = tmp_path / "work", tmp_path / "out"
    source.mkdir()
    out.mkdir()
    (source / "demo.cast").write_text("new cast", encoding="utf-8")
    (source / "demo.gif").write_bytes(b"new gif")
    if previous:
        (out / "demo.cast").write_text("old cast", encoding="utf-8")
        (out / "demo.gif").write_bytes(b"old gif")
    real = os.replace

    def failing(src, dst):
        if os.path.basename(str(dst)) == "demo.gif" and str(src).endswith(".tmp"):
            raise OSError(28, "No space left on device")
        return real(src, dst)

    monkeypatch.setattr(rd.os, "replace", failing)
    pairs = [(str(source / "demo.cast"), "demo.cast"), (str(source / "demo.gif"), "demo.gif")]
    with pytest.raises(OSError):
        rd.install(pairs, str(out))
    if previous:
        assert sorted(os.listdir(str(out))) == ["demo.cast", "demo.gif"]
        assert (out / "demo.cast").read_text(encoding="utf-8") == "old cast"
        assert (out / "demo.gif").read_bytes() == b"old gif"
    else:
        assert os.listdir(str(out)) == []
    monkeypatch.setattr(rd.os, "replace", real)
    assert rd.install(pairs, str(out)) == [str(out / "demo.cast"), str(out / "demo.gif")]
    assert sorted(os.listdir(str(out))) == ["demo.cast", "demo.gif"]
    assert (out / "demo.gif").read_bytes() == b"new gif"
