"""fence-run's ``--arg-file`` read (REQ-719 BR-15, BR-16, AC-12, ADR-4): the file is walked
from a handle on the working directory, following no symlink, and checked and read on the
descriptor it was opened as, so there is no window between a check and the open."""

import builtins
import io
import os
import subprocess
import sys
import threading
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import exec_adapter as ea  # noqa: E402
import fence_census as fc  # noqa: E402
import fence_run as fr  # noqa: E402
import recording_stubs as rs  # noqa: E402

#: What every outside file holds: no byte of it may reach the caller or the fence.
SECRET = "outside-secret-7f3a"
#: The fence the toolkit copy gains: it prints the value it was bound, after a marker.
PRINTER = "\n```sh\nprintf 'bound:%s' \"$NEW_BODY\"\n```\n"
TEXT = "a 'quoted'\nvalue $(x)\n"


@pytest.fixture(scope="module")
def printer(tmp_path_factory):
    """A toolkit copy with one more runner fence, which prints its ``NEW_BODY``: ``(root, id)``."""
    root = rs.toolkit_copy(str(tmp_path_factory.mktemp("arg-file") / "tk"))
    with open(os.path.join(root, "validate", "SKILL.md"), "a", encoding="utf-8") as fh:
        fh.write(PRINTER)
    rec = [r for r in fc.census(root, ea.load("claude", root))
           if r["id"].startswith("validate/SKILL.md#")][-1]
    assert rec["route"] == "runner" and rec["placeholders"] == ["NEW_BODY"], rec
    return root, rec["id"]


@pytest.fixture
def runner(printer, monkeypatch):
    """``printer``, with ``fc.census`` memoized: every ``fence-run`` call recomputes it."""
    real = fc.census
    memo = {}

    def census(root, adapter=None):
        key = (root, adapter.name if adapter is not None else None)
        if key not in memo:
            memo[key] = real(root, adapter)
        return memo[key]
    monkeypatch.setattr(fc, "census", census)
    return printer


def _run(runner, path, cwd):
    """``fence-run run <printer> --arg-file NEW_BODY=<path>`` from ``cwd``: ``(rc, stderr)``."""
    root, fid = runner
    err = io.StringIO()
    rc = fr.run(fid, ["--arg-file", "NEW_BODY=%s" % path], root, environ=dict(os.environ),
                cwd=str(cwd), err=err)
    return rc, err.getvalue()


def _assert_bad_value(runner, rc, err, out, fragment):
    """Exit 65, one ``fence_run_bad_value:`` line naming ``fragment``, and nothing bound."""
    lines = err.splitlines()
    assert rc == fr.BAD_VALUE == 65, (rc, err)
    assert len(lines) == 1 and lines[0].startswith("fence_run_bad_value: %s: " % runner[1]), err
    assert fragment in lines[0], (fragment, err)
    assert "bound:" not in out and SECRET not in out and SECRET not in err, (out, err)


def _write(path, data):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


@pytest.fixture
def tree(tmp_path):
    """A working copy ``wc`` holding every kind of path BR-16 refuses, beside ``outside``."""
    wc = tmp_path / "wc"
    outside = tmp_path / "outside"
    _write(outside / "secret.txt", SECRET)
    _write(wc / "ok.txt", TEXT)
    _write(wc / "sub" / "value.txt", "in sub\n")
    (wc / "dir").mkdir()
    (wc / "link-in").symlink_to("ok.txt")
    (wc / "link-in-abs").symlink_to(wc / "ok.txt")
    (wc / "link-out").symlink_to(outside / "secret.txt")
    (wc / "dlink-in").symlink_to("sub")
    (wc / "dlink-out").symlink_to(outside)
    _write(wc / "big", b"x" * (fr.MAX_ARG_FILE + 1))
    _write(wc / "latin", b"caf\xe9\n")
    return wc, outside


def _refused(wc, outside):
    """``(path, fragment of the reason)`` for every path BR-16 refuses."""
    return [
        ("link-in", "'link-in' is a symlink"),                 # last component, points inside
        ("link-in-abs", "'link-in-abs' is a symlink"),
        ("link-out", "'link-out' is a symlink"),
        ("dlink-in/value.txt", "'dlink-in' is a symlink"),     # directory component, inside
        ("dlink-out/secret.txt", "'dlink-out' is a symlink"),  # directory component, outside
        (str(wc / "dlink-out" / "secret.txt"), "'dlink-out' is a symlink"),
        ("../outside/secret.txt", "'..' segment"),
        ("sub/../ok.txt", "'..' segment"),
        (str(wc) + "/../outside/secret.txt", "'..' segment"),
        (str(outside / "secret.txt"), "is not under the working directory"),
        (str(wc) + "2/ok.txt", "is not under the working directory"),
        ("/etc/hosts", "is not under the working directory"),
        ("dir", "is not a regular file"),
        (".", "is not a regular file"),
        (str(wc), "is not a regular file"),
        ("big", "over the 1 MiB cap"),
        ("latin", "is not UTF-8 text"),
        ("missing.txt", "'missing.txt' is a symlink or cannot be opened"),
        ("", "names no path"),
        ("ok.txt\x00", "names no path"),
    ]


# ------------------------------------------------------------------------ BR-16, AC-12
def test_req719_refused_paths_bind_nothing(runner, tree, capfd):
    """Each path BR-16 refuses is a Refusal read directly, and through `fence-run run` exit 65
    with one `fence_run_bad_value:` line and the fence never run. A symlink is refused at any
    component, the one that points inside the working directory too."""
    wc, outside = tree
    for path, fragment in _refused(wc, outside):
        with pytest.raises(fr.Refusal) as caught:
            fr.read_arg_file(path, str(wc))
        assert fragment in caught.value.reason, (path, caught.value.reason)
        assert SECRET not in caught.value.reason
        rc, err = _run(runner, path, wc)
        _assert_bad_value(runner, rc, err, capfd.readouterr().out, fragment)
    # A device is refused on its descriptor, before a byte is read: /dev/zero never ends.
    for name in ("null", "zero"):
        with pytest.raises(fr.Refusal) as caught:
            fr.read_arg_file(name, "/dev")
        assert "is not a regular file" in caught.value.reason
        rc, err = _run(runner, name, "/dev")
        _assert_bad_value(runner, rc, err, capfd.readouterr().out, "is not a regular file")
    # The working copy is as it was: nothing was written or moved.
    assert (wc / "ok.txt").read_text() == TEXT and (wc / "link-in").is_symlink()


# ------------------------------------------------------------------------ AC-12
def _within(seconds, call, unblock):
    """``call()`` in a thread: ``({"value"|"exc": …}, seconds taken)``. One still running after
    ``seconds`` is freed with ``unblock()`` and the test fails."""
    box = {}

    def target():
        try:
            box["value"] = call()
        except Exception as exc:  # the Refusal is the result under test
            box["exc"] = exc
    thread = threading.Thread(target=target, daemon=True)
    start = time.monotonic()
    thread.start()
    thread.join(seconds)
    took = time.monotonic() - start
    if thread.is_alive():
        unblock()
        thread.join(5)
        pytest.fail("the --arg-file read still blocked after %.1f s" % seconds)
    return box, took


def test_req719_a_fifo_is_refused_without_blocking(runner, tmp_path, capfd):
    """A FIFO no one writes is refused, and the call returns within two seconds: the last
    component is opened with O_NONBLOCK and refused on its descriptor before any read."""
    wc = tmp_path / "wc"
    wc.mkdir()
    fifo = wc / "pipe"
    os.mkfifo(str(fifo))

    def unblock():
        try:
            os.close(os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass

    box, took = _within(2.0, lambda: fr.read_arg_file("pipe", str(wc)), unblock)
    assert isinstance(box.get("exc"), fr.Refusal), box
    assert "is not a regular file" in box["exc"].reason and took < 2.0
    box, took = _within(2.0, lambda: _run(runner, "pipe", wc), unblock)
    assert "value" in box and took < 2.0, box
    _assert_bad_value(runner, box["value"][0], box["value"][1], capfd.readouterr().out,
                      "is not a regular file")
    # The real command line too: a blocked open would hang here until the timeout kills it.
    root, fid = runner
    out = subprocess.run([os.path.join(root, "tools", "adlc", "fence-run"), "run", fid,
                          "--arg-file", "NEW_BODY=pipe"], cwd=str(wc), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, universal_newlines=True, timeout=60)
    _assert_bad_value(runner, out.returncode, out.stderr, out.stdout, "is not a regular file")


# ------------------------------------------------------------------------ BR-16, AC-12
@pytest.fixture
def spelled(tmp_path):
    """A working copy reached through a symlinked parent: ``(given, real)`` spellings."""
    real = tmp_path / "real" / "wc"
    _write(real / "value.txt", TEXT)
    _write(real / "sub" / "value.txt", "in sub\n")
    (tmp_path / "via").symlink_to(tmp_path / "real")
    given = str(tmp_path / "via" / "wc")
    assert os.path.realpath(given) != given
    return given, os.path.realpath(given)


def test_req719_a_plain_file_is_read_under_each_spelling(runner, spelled, capfd):
    """A plain file is read under a relative path, under an absolute path in the working
    directory's given spelling and under one in its real spelling (macOS's /var and
    /private/var), and through `fence-run run` the fence is bound its text."""
    given, real = spelled
    for path, text in (("value.txt", TEXT), ("./value.txt", TEXT), ("sub/value.txt", "in sub\n"),
                       ("sub//./value.txt", "in sub\n"),
                       (given + "/value.txt", TEXT), (given + "/sub/value.txt", "in sub\n"),
                       (real + "/value.txt", TEXT), (real + "/sub/value.txt", "in sub\n")):
        assert fr.read_arg_file(path, given) == text, path
    for path in ("value.txt", given + "/value.txt", real + "/value.txt"):
        rc, err = _run(runner, path, given)
        assert rc == 0, (path, err)
        assert capfd.readouterr().out == "bound:" + TEXT, path
    # The cap is inclusive: exactly 1 MiB is read whole.
    _write(os.path.join(real, "cap"), b"y" * fr.MAX_ARG_FILE)
    assert fr.read_arg_file("cap", given) == "y" * fr.MAX_ARG_FILE


# ------------------------------------------------------------------------ BR-15, AC-12
#: The component the swap replaces at each seam call: before ``a`` is opened, before ``b`` is
#: opened from ``a``, and before ``value.txt`` is opened from ``b``.
SWAPS = {1: ("a", ""), 2: ("a/b", ""), 3: ("a/b/value.txt", "value.txt")}


def _swap_layout(base):
    """``base/wc/a/b/value.txt`` inside, and an ``outside`` that each swapped symlink reaches
    the same relative name in, holding :data:`SECRET`."""
    wc, outside = base / "wc", base / "outside"
    _write(wc / "a" / "b" / "value.txt", "inside\n")
    _write(outside / "b" / "value.txt", SECRET)
    _write(outside / "value.txt", SECRET)
    return wc, outside


def _swapper(wc, outside, at, calls):
    """A seam that, on its ``at``-th call, renames a component away and puts a symlink to the
    outside in its place."""
    rel, target = SWAPS[at]

    def seam():
        calls.append(rel)
        if len(calls) == at:
            here = os.path.join(str(wc), rel)
            os.rename(here, here + "-away")
            os.symlink(os.path.join(str(outside), target), here)
            # The swap is a real attack: a read by path now reaches the outside file.
            with open(os.path.join(str(wc), "a", "b", "value.txt"), encoding="utf-8") as fh:
                assert fh.read() == SECRET
    return seam


@pytest.mark.parametrize("at", sorted(SWAPS))
def test_req719_a_swapped_directory_leaks_nothing(runner, tmp_path, monkeypatch, capfd, at):
    """With the seam between two component opens replaced by a swap of a directory (or of the
    file) for a symlink to an outside directory, the read is refused and no byte of the
    outside file is returned, directly or to the fence."""
    wc, outside = _swap_layout(tmp_path / "direct")
    calls = []
    monkeypatch.setattr(fr, "between_arg_file_opens", _swapper(wc, outside, at, calls))
    with pytest.raises(fr.Refusal) as caught:
        fr.read_arg_file("a/b/value.txt", str(wc))
    name = os.path.basename(SWAPS[at][0])
    assert "%r is a symlink" % name in caught.value.reason, caught.value.reason
    assert SECRET not in caught.value.reason and len(calls) == at
    # Through the runner, from an absolute path: exit 65, and the fence never sees the file.
    wc, outside = _swap_layout(tmp_path / "runner")
    calls = []
    monkeypatch.setattr(fr, "between_arg_file_opens", _swapper(wc, outside, at, calls))
    rc, err = _run(runner, str(wc / "a" / "b" / "value.txt"), wc)
    _assert_bad_value(runner, rc, err, capfd.readouterr().out, "%r is a symlink" % name)
    assert len(calls) == at


def test_req719_no_path_is_resolved_then_opened(spelled):
    """The read resolves only the working directory, opens no path string for the file, and
    opens each component from the handle on the one before it, following no symlink."""
    given, real = spelled
    resolved, opened, by_path = [], [], []
    real_realpath, real_open = os.path.realpath, os.open

    def realpath(path, *a, **kw):
        resolved.append(path)
        return real_realpath(path, *a, **kw)

    def os_open(path, flags, mode=0o777, *, dir_fd=None):
        opened.append((path, flags, dir_fd))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def no_open(*a, **kw):
        by_path.append(a[:1])
        raise AssertionError("open() on a path string")

    for path in ("sub/value.txt", given + "/sub/value.txt", real + "/sub/value.txt"):
        del resolved[:], opened[:]
        # Patched only around the call, and undone before any assertion runs.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(os.path, "realpath", realpath)
            mp.setattr(os, "open", os_open)
            mp.setattr(builtins, "open", no_open)
            got = fr.read_arg_file(path, given)
        assert got == "in sub\n", path
        assert set(resolved) <= {given}, (path, resolved)
        assert not by_path, by_path
        assert [o[0] for o in opened] == [given, "sub", "value.txt"], opened
        assert opened[0][2] is None and opened[0][1] & os.O_DIRECTORY
        for name, flags, dir_fd in opened[1:]:
            assert dir_fd is not None and "/" not in name and flags & os.O_NOFOLLOW, opened
        assert opened[1][1] & os.O_DIRECTORY
        assert opened[2][1] & os.O_NONBLOCK and not opened[2][1] & os.O_DIRECTORY
