"""REQ-691 TASK-241 — /bugfix's regression-test protocol, held structurally.

The protocol lives in ``bugfix/references/regression-test.md`` (ADR-691-G) and
``bugfix/SKILL.md`` sends the model there from five steps. A live ``/bugfix`` run
is what produces the test, the record and the gate (AC-1 to AC-4, AC-12); this
file pins the text that makes the model produce them: where each pointer sits,
the order the companion gives the steps in, the fields and verdicts it names,
and the mode read at the head of every section (ADR-691-H). The engine's rules
are tested in ``tools/adlc/tests/test_regression_check.py`` and the wrapper's in
``partials/tests/regression-check.test.sh``.

Both files are read by path from the repo root, as ``test_lessons_contract.py``
reads its skills. Markers and fences are found by whole lines outside fenced
blocks, never by a substring a prose mention could also carry (LESSON-404).

The Gate's fence is also run, whole, in sandbox git repos with a bare origin,
under /bin/sh, bash, zsh and dash (a shell that is not installed is skipped by
name, LESSON-618). The installed toolkit there is this checkout, behind partials
that say when they are sourced, and the forge is the stateful mock
(``ADLC_FORGE_MOCK_STORE``), so each case runs the real wrapper and engine and
asserts on the lines they print. Before the fence runs, every line is held to a
token allowlist, and the allowlist itself is tested both ways (LESSON-619).
"""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SKILL = "bugfix/SKILL.md"
COMPANION = "bugfix/references/regression-test.md"
SECTIONS = ("Mode", "Write and contrast", "Record", "PR body", "Gate")

SOURCE = ('if [ -f .adlc/partials/regression-check.sh ]; then . .adlc/partials/regression-check.sh; '
          'else . "$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"; fi')
MODE_CALL = 'adlc_regression_check mode; echo "regression_mode_rc=$?"'
UNIT_POINTER = "Read `bugfix/references/regression-test.md` and follow it before you continue."
SECTION_POINTER = "Read the `{}` section of `bugfix/references/regression-test.md` and follow it before you continue."
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")

# The Gate fence (BR-13, ADR-691-F, amended): four single-quoted placeholders.
# It runs only the installed toolkit's code and reads policy only from the
# integration branch as a full remote ref; the fix tree supplies data (LESSON-718).
GATE_PLACEHOLDERS = ("'<bug-id>'", "'<fix-branch>'", "'<integration-branch>'", "'<pr-number>'")
GATE_ITSELF = 'if [ "$rgt_rc" = 0 ] && [ "$rgt_ib" = "$rgt_fix" ]; then'
GATE_PATHS = ('rgt_home="$ADLC_TOOLKIT_ROOT/partials/adlc-home.sh"; '
              'rgt_forge="$ADLC_TOOLKIT_ROOT/partials/forge.sh"; '
              'rgt_part="$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"')
GATE_REFS = 'rgt_base="refs/remotes/origin/$rgt_ib"; rgt_head="refs/remotes/origin/$rgt_fix"'
GATE_INSTALLED = 'elif [ ! -f "$rgt_home" ] || [ ! -f "$rgt_forge" ] || [ ! -f "$rgt_part" ]; then'
#: The three partials, in this order: adlc-home.sh first, so forge.sh never looks
#: for one in the current directory.
GATE_SOURCES = ('. "$rgt_home"', '. "$rgt_forge"', '. "$rgt_part"')
GATE_PROVIDER = ('rgt_prov=$(command "$(_adlc_forge_python)" -E '
                 '"$ADLC_TOOLKIT_ROOT/tools/adlc/forge_config.py" resolve-provider .)')
GATE_PR_BASE = ('elif [ "$(ADLC_FORGE_PROVIDER_OVERRIDE="$rgt_prov" adlc_forge_pr_view "$rgt_pr" '
                "--fields baseRefName | sed -n 's/^baseRefName=//p')\" != \"$rgt_ib\" ]; then")
GATE_FETCH = ('elif ! git fetch -q --no-tags origin "+refs/heads/$rgt_ib:$rgt_base" '
              '"+refs/heads/$rgt_fix:$rgt_head"; then')
GATE_CONFIG_AT_BASE = ('elif git cat-file -e "$rgt_at.adlc/config.yml" 2>/dev/null || '
                       '{ git cat-file -e "$rgt_at.adlc" 2>/dev/null && '
                       '! git cat-file -e "$rgt_at.adlc/" 2>/dev/null; }; then')
GATE_MODE = 'rgt_mode=$(adlc_regression_check mode --base "$rgt_base"); rgt_rc=$?'
GATE_OFF_ARM = "'0:regression-test: off'*) ;;"
GATE_REQUIRED_ARM = "'0:regression-test: required'*)"
GATE_GUARDS = (
    'if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then',
    'elif [ "$(git rev-parse HEAD)" != "$(git rev-parse "$rgt_head")" ]; then',
)
GATE_CALL = 'adlc_regression_check check --require-recorded --base "$rgt_base" "$rgt_bug"; rgt_rc=$?'
GATE_NO_CONFIG = ("printf 'regression-test: off\\n.adlc/config.yml does not exist at %s, which "
                  "means off; set bugfix.regression_test: required in it to turn regression "
                  "tests on\\n' \"$rgt_base\"")
#: The shells a fence may run under; one that is not installed is skipped by name.
SHELLS = ("/bin/sh", "bash", "zsh", "dash")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as handle:
        return handle.read()


def _section(text, start, end):
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[a:b]


def _root_line():
    """The canonical root line, taken from conventions.md rather than copied here."""
    for line in _read(".adlc/context/conventions.md").splitlines():
        if line.startswith('ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"'):
            return line
    raise AssertionError("conventions.md carries no root line")


def _fenced_line_numbers(lines):
    """Indices of every line inside a fenced block, the fence lines included."""
    inside, marker, out = False, "", set()
    for i, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if not inside and m:
            inside, marker = True, m.group(1)
            out.add(i)
        elif inside:
            out.add(i)
            if line.strip().startswith(marker[0] * len(marker)) and line.strip().strip(marker[0]) == "":
                inside = False
    return out


def _companion_sections():
    """``## `` headings of the companion, outside fences, mapped to their text."""
    lines = _read(COMPANION).splitlines()
    fenced = _fenced_line_numbers(lines)
    heads = [(i, line[3:].strip()) for i, line in enumerate(lines)
             if i not in fenced and line.startswith("## ")]
    out = {}
    for n, (i, name) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        out[name] = "\n".join(lines[i:end])
    return out


def _sh_fences(text):
    """The bodies of the ```sh fences in ``text``, each a list of its lines."""
    fences, body = [], None
    for line in text.splitlines():
        if body is None:
            if re.match(r"^\s*```(sh|bash|shell)\b", line):
                body = []
        elif line.strip() == "```":
            fences.append(body)
            body = None
        else:
            body.append(line)
    return fences


def _step6(text):
    """``/bugfix`` Step 6 to the next ``## `` heading outside a fence, sliced as
    ``partials/tests/lesson-check.test.sh`` slices it."""
    out, started, inside = [], False, False
    for line in text.splitlines():
        if line.startswith("**Step 6 "):
            started = True
        if not started:
            continue
        if line.lstrip().startswith("```"):
            inside = not inside
        elif not inside and line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


# --- LESSON-619: the Gate fence is executed below, so it is an execution surface.
# Before any of it runs, every word of every line is held to a small allowlist:
# the commands and git subcommands the fence uses, the arguments it passes, and
# its own variables. Quoted spans are data, except that a `$( )` inside one is
# checked as a command line of its own, and a backtick anywhere fails. The root
# line, the three source lines and the provider line are taken whole, because
# conventions.md and the GATE_ constants pin them byte for byte. Anything else
# fails the test unexecuted.
_ALLOWED_COMMANDS = frozenset({"printf", "echo", "git", ":", "[", "adlc_regression_check", "case", "for",
                               "adlc_forge_pr_view", "sed"})
_KEYWORDS = frozenset({"if", "elif", "else", "then", "fi", "do", "done", "!", "{", "}"})
_GIT_SUBCOMMANDS = frozenset({"status", "fetch", "rev-parse", "cat-file"})
_ALLOWED_ARGS = frozenset({
    "in", "rgt_ref", "0", "-n", "-z", "-f", "-e", "!", "=", "!=", "]", "-q", "origin", "HEAD",
    "--show-prefix", "--porcelain", "--untracked-files=normal", "--no-tags", "--fields",
    "baseRefName", "mode", "check", "--require-recorded", "--base", "2>/dev/null",
})
_ASSIGN_RE = re.compile(r"^(rgt_(bug|fix|ib|pr|rc)=(Q|0|2|\$\?)|rgt_(home|forge|part|base|head|at)=D"
                        r"|rgt_mode=S|ADLC_FORGE_PROVIDER_OVERRIDE=D)$")
_PATTERN_RE = re.compile(r"^[A-Za-z0-9*?.\[\]!/_-]+$")
_QUOTED_RE = re.compile(r"^[QD]+$")
_REDIRECT_RE = re.compile(r"\d?>&\d")


def _close_paren(text, i):
    """Index of the ``)`` closing the ``$(`` whose ``(`` is at ``i``."""
    depth, j = 0, i
    while j < len(text):
        c = text[j]
        if c == "'":
            j = text.index("'", j + 1)
        elif c == '"':
            j += 1
            while text[j] != '"':
                j += 2 if text[j] == "\\" else 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError("unclosed $(")


def _shell_words(line):
    """``(words, subs)``: the line's words, a single-quoted span written ``Q`` and
    a double-quoted one ``D``, operators as words of their own; and the bodies of
    its ``$( )`` substitutions, quoted or not."""
    words, subs, cur, i = [], [], "", 0
    while i < len(line):
        c = line[i]
        if c == "`":
            raise ValueError("a backtick")
        if c == "'":
            i = line.index("'", i + 1) + 1
            cur += "Q"
        elif c == '"':
            j = i + 1
            while line[j] != '"':
                if line[j] == "`":
                    raise ValueError("a backtick")
                if line.startswith("$(", j):
                    k = _close_paren(line, j + 1)
                    subs.append(line[j + 2:k])
                    j = k + 1
                    continue
                j += 2 if line[j] == "\\" else 1
            cur += "D"
            i = j + 1
        elif line.startswith("$(", i):
            k = _close_paren(line, i + 1)
            subs.append(line[i + 2:k])
            cur += "S"
            i = k + 1
        elif _REDIRECT_RE.match(line, i):
            m = _REDIRECT_RE.match(line, i)
            cur += m.group(0)
            i = m.end()
        elif c in " \t":
            if cur:
                words.append(cur)
            cur, i = "", i + 1
        elif c in ";|&()":
            if cur:
                words.append(cur)
            op = line[i:i + 2] if line[i:i + 2] in (";;", "&&", "||") else c
            words.append(op)
            cur, i = "", i + len(op)
        elif c == "\\":
            cur, i = cur + line[i:i + 2], i + 2
        else:
            cur, i = cur + c, i + 1
    if cur:
        words.append(cur)
    return words, subs


def _line_offenders(line, pattern_mode):
    """``(pattern_mode, offenders)`` for one line; ``pattern_mode`` is True while a
    ``case`` is between ``in`` (or ``;;``) and an arm's ``)``."""
    try:
        words, subs = _shell_words(line)
    except (ValueError, IndexError) as exc:
        return pattern_mode, ["%s: %s" % (line, exc)]
    bad = []
    cmd_pos, cmd, want_git_sub = not pattern_mode, None, False
    for w in words:
        if pattern_mode:
            if w == "esac":
                pattern_mode, cmd_pos = False, False
            elif w == ")":
                pattern_mode, cmd_pos, cmd = False, True, None
            elif not (w == "|" or w == "Q" or _PATTERN_RE.match(w)):
                bad.append("%s: pattern %r" % (line, w))
            continue
        if w in (";", "&&", "||", "|", "("):
            cmd_pos, cmd = True, None
        elif w == ";;":
            pattern_mode, cmd_pos, cmd = True, False, None
        elif cmd_pos:
            if w in _KEYWORDS or _ASSIGN_RE.match(w):
                continue
            if w in _ALLOWED_COMMANDS:
                cmd_pos, cmd, want_git_sub = False, w, w == "git"
            else:
                bad.append("%s: command %r" % (line, w))
                cmd_pos = False
        elif want_git_sub:
            want_git_sub = False
            if w not in _GIT_SUBCOMMANDS:
                bad.append("%s: git subcommand %r" % (line, w))
        elif cmd == "case" and w == "in":
            pattern_mode = True
        elif not (w in _ALLOWED_ARGS or _QUOTED_RE.match(w)):
            bad.append("%s: argument %r" % (line, w))
    for sub in subs:
        bad.extend(_line_offenders(sub, False)[1])
    return pattern_mode, bad


def _fence_offenders(lines):
    """Every line of ``lines`` not on the allowlist, with the word that failed."""
    whole = {_root_line(), GATE_PROVIDER} | set(GATE_SOURCES)
    bad, pattern_mode = [], False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or line in whole:
            continue
        pattern_mode, found = _line_offenders(line, pattern_mode)
        bad.extend(found)
    return bad


def _gate_fence():
    """The Gate's fence, held to the allowlist before anything can run it."""
    fence = _sh_fences(_companion_sections()["Gate"])[0]
    offenders = _fence_offenders(fence)
    assert not offenders, offenders
    return fence


def _shell(name):
    found = shutil.which(name)
    if not found:
        pytest.skip("%s is not installed" % name)
    return found


def _sandbox_env(home):
    """No ToolkitRoot, no global or system git config, and a fixed identity."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }


def _git(env, cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True, capture_output=True, timeout=60)


def _commit(env, work, rel, text):
    path = work / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    _git(env, work, "add", "--", rel)
    _git(env, work, "commit", "-q", "-m", "add " + rel)


FIX = "fix/bug-123-thing"
REQUIRED = "bugfix:\n  regression_test: required\n"
OFF = "bugfix:\n  regression_test: off\n"
RECORDED = ('---\nid: BUG-123\nstatus: open\nregression_tests: ["tests/test_123.py"]\n---\n\n'
            "# BUG-123\n")
UNRECORDED = "---\nid: BUG-123\nstatus: open\n---\n\n# BUG-123\n"
#: Lines that only appear when code from the tree ran.
FORGED = 'echo "FORGED-RAN"\nadlc_regression_check() { echo "regression-check: pass"; return 0; }\n'
INSTALLED = ("INSTALLED-adlc-home-SOURCED", "INSTALLED-forge-SOURCED",
             "INSTALLED-regression-check-SOURCED")


class _Lab(object):
    """A fix checkout of a bare origin, on ``dev`` then ``fix/bug-123-thing``.

    HOME's symlink-route install is a directory whose three partials say when
    they are sourced and then source this checkout's real ones, and whose
    ``tools`` is this checkout's: the fence runs the real wrapper, engine and
    forge adapter. The forge is the stateful mock, holding PR 7 (``dev`` <-
    the fix branch). ``origin`` is a ``file://github.com/...`` URL, which git
    reads as a local path and the installed ``forge_config.py`` as GitHub.
    """

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        home = tmp_path / "home"
        skills = home / ".claude" / "skills"
        (skills / "partials").mkdir(parents=True)
        for name in ("adlc-home", "forge", "regression-check"):
            (skills / "partials" / (name + ".sh")).write_text(
                'echo "INSTALLED-%s-SOURCED"\n. "%s/partials/%s.sh"\n' % (name, ROOT, name))
        os.symlink(os.path.join(ROOT, "tools"), str(skills / "tools"))
        self.store = tmp_path / "forge-store"
        self.store.mkdir()
        self.env = _sandbox_env(home)
        self.env.update({"ADLC_FORGE_MOCK": "1", "ADLC_FORGE_MOCK_STORE": str(self.store)})
        self.origin = tmp_path / "origin.git"
        self.work = tmp_path / "work"
        _git(self.env, tmp_path, "init", "-q", "--bare", str(self.origin))
        _git(self.env, tmp_path, "init", "-q", "-b", "dev", str(self.work))
        self.git("remote", "add", "origin", "file://github.com" + str(self.origin))
        self.prs((7, "dev"))

    def git(self, *args):
        _git(self.env, self.work, *args)

    def prs(self, *pairs):
        """The forge's PRs: ``(number, base)``, each with the fix branch as head."""
        prs = [{"number": n, "url": "https://mock.forge/acme/widgets/pull/%d" % n, "state": "OPEN",
                "headRefName": FIX, "baseRefName": base} for n, base in pairs]
        (self.store / "prs.json").write_text(json.dumps({"next": 100, "prs": prs}))

    def write(self, rel, text):
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, files, msg="change"):
        for rel, text in files.items():
            self.write(rel, text)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)

    def base(self, files, ib="dev"):
        """Commit ``files`` on the integration branch, push it, and cut the fix branch."""
        self.commit(dict({"README.md": "fixture\n"}, **files), "base")
        self.git("push", "-q", "origin", ib)
        self.git("checkout", "-q", "-b", FIX)

    def fix(self, files, push=True):
        self.commit(files, "fix")
        if push:
            self.git("push", "-q", "-u", "origin", FIX)

    def run(self, shell, cwd=None, bug="BUG-123", fix=FIX, ib="dev", pr="7"):
        return _run_gate(shell, self.env, cwd or self.work, self.tmp,
                         bug=bug, fix=fix, ib=ib, pr=pr)

    def engine(self, *argv, cwd=None):
        """The installed engine run directly, for parity with the fence's own lines."""
        proc = subprocess.run(["python3", "-E", os.path.join(ROOT, "tools", "adlc", "regression_check.py")]
                              + list(argv), cwd=str(cwd or self.work), env=self.env,
                              capture_output=True, text=True, timeout=60)
        return proc.stdout


def _run_gate(shell, env, cwd, tmp_path, bug="BUG-123", fix=FIX, ib="dev", pr="7"):
    """Run the Gate fence under ``shell`` from ``cwd``, each placeholder replaced as
    conventions.md says: one single-quoted literal, each ``'`` written ``'\\''``.
    The script lives outside the work tree, so it never dirties it. Returns stdout."""
    body = "\n".join(_gate_fence())
    for placeholder, value in zip(GATE_PLACEHOLDERS, (bug, fix, ib, pr)):
        assert body.count(placeholder) == 1, placeholder
        body = body.replace(placeholder, "'" + value.replace("'", "'\\''") + "'")
    script = tmp_path / "gate.sh"
    script.write_text(body + "\n")
    result = subprocess.run([shell, str(script)], cwd=str(cwd), env=env,
                            capture_output=True, text=True, timeout=120)
    return result.stdout


def _rc(out):
    last = out.splitlines()[-1] if out else ""
    assert last.startswith("regression_gate_rc="), out
    return int(last.split("=", 1)[1])


def _never(out, *words):
    for word in words:
        assert word not in out, (word, out)


def test_mode_read_before_phase_1():
    """BR-1, BR-17, AC-3: the mode is read before Phase 1, an error stops there,
    and an unreadable setting is never off."""
    skill = _read(SKILL)
    prereq = _section(skill, "## Prerequisites", "### Phase 1: Report")
    assert UNIT_POINTER in prereq
    assert "its `Mode` section reads `bugfix.regression_test` now, before Phase 1" in prereq
    assert "a setting it cannot read stops `/bugfix` here" in prereq
    assert skill.index(UNIT_POINTER) < skill.index("### Phase 1: Report")
    context = _section(skill, "## Context", "## Input")
    assert "read .adlc/config.yml before Phase 1" in context
    assert "before Step 1" not in context

    sections = _companion_sections()
    assert list(sections) == list(SECTIONS)
    companion = _read(COMPANION)
    assert "Companion to `bugfix/SKILL.md`" in companion
    assert "| Prerequisites, before Phase 1 | Mode |" in companion
    mode = sections["Mode"]
    assert _sh_fences(mode)[0] == [_root_line(), SOURCE, MODE_CALL]
    fence_end = mode.index("```\n", mode.index("```sh") + 5)
    required = mode.index("- `regression-test: required` (rc 0)")
    off = mode.index("- `regression-test: off` (rc 0)")
    error = mode.index("- `regression-test: error` (rc 2)")
    assert fence_end < required < off < error
    stop = mode[error:]
    assert "stop `/bugfix` here, before Phase 1, and show the second line as printed" in stop
    assert "the allowed values `required` and `off`" in stop
    assert "An error is never `off`" in stop and "do not choose a mode yourself" in stop
    assert "Any other output, or none, is an error as well." in mode


def test_write_and_contrast_section():
    """BR-2, BR-4: Phase 3 sends the model to the test-first protocol before the
    fix, and the protocol says what the test exercises and how it cites the bug."""
    phase3 = _section(_read(SKILL), "### Phase 3: Fix", "### Phase 4: Verify")
    pointer = SECTION_POINTER.format("Write and contrast")
    assert pointer in phase3
    assert phase3.index(pointer) < phase3.index("3. Implement the fix")
    assert "5. Update related test files if the fix changes behavior" in phase3  # BR-8 unchanged

    wc = _companion_sections()["Write and contrast"]
    assert _sh_fences(wc)[0] == [_root_line(), SOURCE, MODE_CALL]
    step1 = _section(wc, "1. **Write the regression test before any of the fix.**", "\n2. **")
    assert "exercises the root cause in the bug report's Root Cause section" in step1
    assert "asserts the expected behavior (BR-2)" in step1
    assert "Updating an existing test counts when the updated case reproduces the bug" in step1
    assert "`BUG-nnn`" in step1
    for where in ("in the test name", "in the describe or suite title", "in a comment next to the case"):
        assert where in step1, where
    # The seam lands first, as its own behaviour-preserving change, and is not the fix.
    assert "land the seam first, on its own" in step1
    assert "behavior-preserving change" in step1 and "The seam is not the fix." in step1
    step2 = _section(wc, "2. **Run the test against the unfixed tree.", "\n3. **")
    assert "**It fails to load**" in step2 and "That is a weak contrast" in step2
    assert "the PR body flags it" in step2


def test_failing_run_recorded_before_fix():
    """BR-3, AC-4 (ADR-691-E): the test is written and its failing run kept before
    the fix is written; a test that passes without the fix is never recorded."""
    wc = _companion_sections()["Write and contrast"]
    anchors = [
        "1. **Write the regression test before any of the fix.**",
        "2. **Run the test against the unfixed tree. It must fail on an assertion.**",
        "keep the exact command and the first failing assertion line",
        "it is never recorded as the regression test (BR-3, AC-4)",
        "3. **Only then write the fix**",
        "4. **Run the regression test(s) again, with the fix in place. They must pass.**",
    ]
    at = [wc.index(a) for a in anchors]
    assert at == sorted(at), list(zip(anchors, at))
    # No step tells the model to write the fix before step 3 does.
    steps = wc[at[0]:]
    assert steps.lower().index("write the fix") == steps.index("3. **Only then write the fix**") + len("3. **Only then ")
    passes = _section(wc, "**It passes.**", "**It fails to load**")
    assert "Rewrite it against the root cause" in passes and "waive the bug instead" in passes


def test_record_section_names_fields():
    """BR-5, BR-7, AC-1: Phase 4 records the tests or a waiver, in the shapes the
    readers need, never both, spelled out in full for an older vendored template."""
    phase4 = _section(_read(SKILL), "### Phase 4: Verify", "### Phase 5:")
    pointer = SECTION_POINTER.format("Record")
    assert phase4.index("3. Update the bug report") < phase4.index(pointer) < phase4.index("4. Present an interim summary")
    assert "1. Run the test suite" in phase4  # BR-8: the suite still runs

    rec = _companion_sections()["Record"]
    assert _sh_fences(rec)[0] == [_root_line(), SOURCE, MODE_CALL]
    assert "LESSON-603" in rec and "whatever the template holds" in rec
    tests_line = re.search(r"`(regression_tests: \[[^`\n]*\])`", rec)
    assert tests_line, "no flow-list regression_tests example"
    value = json.loads(tests_line.group(1).split(": ", 1)[1])
    assert value and all(isinstance(v, str) for v in value)
    assert "Never write a block list" in rec
    assert "`<repo-id>:<path>`" in rec and "(BR-14)" in rec
    waiver_line = re.search(r'`(regression_waiver: "[^"`\n]+")`', rec)
    assert waiver_line, "no double-quoted regression_waiver example"
    assert "double-quoted, because a plain value is cut at the first ` #`" in rec
    body = _section(rec, "fill the body section `## Regression Test`", "**No test can reproduce the bug.**")
    for item in ("- Test path(s):", "- Command run:", "- Without the fix: fails — the first failing assertion line",
                 "- With the fix: passes"):
        assert item in body, item
    assert "never both (BR-7)" in rec
    assert "The regression check fails a bug that has both." in rec


def test_waiver_reaches_pr_body_and_summary():
    """BR-6: a waiver needs a reason, and the waiver and its reason reach the PR
    body and the Phase 6 summary."""
    sections = _companion_sections()
    rec = sections["Record"]
    assert "A waiver needs a reason" in rec
    assert "an empty or whitespace-only `regression_waiver` is no waiver at all (BR-6)" in rec
    assert "write `Waived: <the reason>` in `## Regression Test`" in rec

    pr = sections["PR body"]
    assert _sh_fences(pr)[0] == [_root_line(), SOURCE, MODE_CALL]
    assert "between `## Files Changed (this repo)` and `## Test Plan`" in pr
    assert "- `required`, waived: `Waived:` and the reason from `regression_waiver`, word for word (BR-6)." in pr
    assert "`Weak contrast: without the fix the test failed to load, not on an assertion.`" in pr

    skill = _read(SKILL)
    phase5 = _section(skill, "### Phase 5:", "### Phase 6:")
    pointer = SECTION_POINTER.format("PR body")
    assert phase5.index(pointer) < phase5.index("- **Body**:")
    files = phase5.index("     ## Files Changed (this repo)")
    slot = phase5.index("     ## Regression Test")
    plan = phase5.index("     ## Test Plan")
    assert files < slot < plan
    assert "the waiver and its reason" in phase5[slot:plan]

    step6 = _step6(skill)
    assert "### Regression test" in step6 and "Waived: <reason>" in step6
    assert step6.index("### Regression test") < step6.index("### Lessons captured")
    assert "NO_ENTRY: <reason>" in step6  # lesson-check.test.sh's Step 6 contract
    phase4 = _section(skill, "### Phase 4: Verify", "### Phase 5:")
    assert "- Regression test: the tests and their contrast, the waiver, or off for this project" in phase4


def test_off_mode_at_every_site():
    """BR-8, AC-2: every section reads the mode in its own first fence and says
    what off does there; the summary says off and names the key when it is absent."""
    root_line = _root_line()
    sections = _companion_sections()
    for name in SECTIONS:
        sec = sections[name]
        fences = _sh_fences(sec)
        assert fences, name
        first = fences[0]
        if name == "Gate":
            # The Gate sources nothing from the tree; it reads the mode at the base.
            stripped = [line.strip() for line in first]
            assert root_line in stripped and SOURCE not in stripped, name
            assert GATE_MODE in stripped and GATE_CALL in stripped, name
            off = "- `regression-test: off` (rc 0)"
        else:
            assert first[:2] == [root_line, SOURCE], name
            assert first[2] == MODE_CALL, name
            off = "- `regression-test: off`" if name != "PR body" else "- `off`: one line"
        # The mode read heads the section: nothing about off comes before it.
        assert sec.index("```sh") < sec.index(off), name

    mode = sections["Mode"]
    assert "write neither `regression_tests` nor `regression_waiver`" in mode
    assert "Phase 3 still updates related tests when the fix changes behavior" in mode
    assert "Phase 4 still runs the suite (BR-8)" in mode
    assert "When that line says the key is not set, or that there is no `.adlc/config.yml`" in mode
    assert "names the key that turns them on, `bugfix.regression_test: required`" in mode
    assert "- `regression-test: off`: skip this section." in sections["Write and contrast"]
    assert "- `regression-test: off`: write neither field" in sections["Record"]
    assert "- `off`: one line, `Regression tests: off for this project.`" in sections["PR body"]
    assert "there is nothing to gate. Continue to Step 1." in sections["Gate"]

    skill = _read(SKILL)
    assert "`off` skips them all" in _section(skill, "## Prerequisites", "### Phase 1: Report")
    for start, end, name in (("### Phase 3: Fix", "### Phase 4: Verify", "Write and contrast"),
                             ("### Phase 4: Verify", "### Phase 5:", "Record")):
        phase = _section(skill, start, end)
        pointer = phase.index(SECTION_POINTER.format(name))
        line_end = phase.index("\n", pointer)
        assert "skip it when the mode is `off`" in phase[pointer:line_end], name
    step6 = _step6(skill)
    assert "off for this project" in step6
    assert "when the key is not set" in step6
    assert "set bugfix.regression_test: required in .adlc/config.yml to turn them on" in step6


def test_gate_before_merge():
    """BR-13, AC-12 (ADR-691-F, amended): the gate runs before Phase 6 merges,
    validates its four values first, sources only the installed toolkit, checks the
    PR's base, reads the mode at the base before any guard, guards only a required
    project, and stops unmerged and unresolved on anything but a pass or off."""
    skill = _read(SKILL)
    phase6 = _section(skill, "### Phase 6:", "## Branch Naming")
    order = [
        "**Step 0 — Regression gate**",
        SECTION_POINTER.format("Gate"),
        "**Step 1 — Merge each PR.**",
        "adlc_forge_pr_merge <prUrl> --squash --delete-branch",
        "- Set status to `resolved`",
    ]
    at = [phase6.index(a) for a in order]
    assert at == sorted(at), list(zip(order, at))
    assert "in the fix worktree" in phase6[at[0]:at[2]]
    assert "stops `/bugfix` here, with nothing merged and the bug unresolved" in phase6[at[0]:at[2]]

    gate = _companion_sections()["Gate"]
    assert "| Phase 6 Step 0, before Step 1 merges | Gate |" in _read(COMPANION)
    assert "Run the fence from the project directory of the checkout that holds the fix branch" in gate
    fence = _gate_fence()
    stripped = [line.strip() for line in fence]
    text = "\n".join(fence)
    for placeholder in GATE_PLACEHOLDERS:
        assert text.count(placeholder) == 1, placeholder
    assert stripped[0] == ("rgt_bug='<bug-id>'; rgt_fix='<fix-branch>'; "
                           "rgt_ib='<integration-branch>'; rgt_pr='<pr-number>'")
    # Values first, then the installed partials, the PR's base, the fetch, the
    # mode at the base, and only in the required arm the guards and the check.
    order = ['case "$rgt_bug" in', 'case "$rgt_ref" in', 'case "$rgt_pr" in', GATE_ITSELF,
             _root_line(), GATE_PATHS, GATE_REFS, GATE_INSTALLED] + list(GATE_SOURCES) + [
             GATE_PROVIDER, GATE_PR_BASE, GATE_FETCH, GATE_CONFIG_AT_BASE, GATE_MODE,
             GATE_OFF_ARM, GATE_REQUIRED_ARM] + list(GATE_GUARDS) + [GATE_CALL, GATE_NO_CONFIG]
    at = [stripped.index(line) for line in order]
    assert at == sorted(at), list(zip(order, at))
    assert stripped[-1] == 'echo "regression_gate_rc=$rgt_rc"'
    for outcome in (
        "- `regression-test: off` (rc 0): regression tests are off for this project, so there is nothing to gate.",
        "- `regression-check: pass` (rc 0): continue to Step 1, the merge.",
        "- `regression-check: fail` (rc 1): stop before merging. Merge no PR and do not set the bug `resolved` (AC-12).",
        "Show the engine's `BUG-nnn:` lines as printed",
        "- `regression-test: error`, `regression-check: error`, or `regression_gate_rc=2` from a refusal or a guard: stop exactly as for `fail`.",
        "if Step 1 rebases and force-pushes the fix branch, run this fence again on the new head before merging",
    ):
        assert outcome in gate, outcome
    assert "turns a bug that recorded neither tests nor a waiver from legacy into failed (BR-13)" in gate
    for words in ("The Gate runs only the installed toolkit's code, and reads its policy only from the "
                  "integration branch, as a full remote ref.",
                  "The fix branch supplies data, the bug report and its tests, never code and never policy",
                  "resolved in the primary checkout before the fix branch existed",
                  "Never read it again from the fix checkout's `.adlc/config.yml`"):
        assert words in gate, words
    why = _section(gate, "**Why it is built this way.**", "The fence's first line")
    for reason in ("nothing under `.adlc/partials` is sourced at all",
                   "A symlinked `.adlc`, a file git ignores and a `skip-worktree` entry",
                   "a PR retargeted at another branch is refused",
                   "git resolves a short `origin/main` to a tag of that name",
                   "`off` has no guards** (BR-1)",
                   "the tree must be clean", "`HEAD` must equal `refs/remotes/origin/<fix-branch>`",
                   "cannot switch its own gate `off` by editing its config",
                   "requires every listed test to be committed in its repo's `HEAD`"):
        assert reason.lower() in why.lower(), reason
    limitation = gate[gate.index("**Known limitation, cross-repo.**"):]
    for words in ("its committed `repos.<id>.path`", "checked out in that clone, committed and pushed",
                  "`not cloned at`", "`does not exist`", "`not in HEAD`",
                  "never loop on the fence, and never merge"):
        assert words in limitation, words
    assert "absolute `repos.<id>.path`" not in gate

    rec = _companion_sections()["Record"]
    assert "Write the record in the bug report's copy on the fix branch, in the fix worktree" in rec
    assert "push it before Phase 6: the Gate's guards refuse" in rec


def test_gate_fence_runs_installed_code_against_full_refs():
    """LESSON-718, the re-verify findings: the fence sources nothing from the tree
    (no `.adlc/partials`, no `.adlc/tools`), only the three installed partials,
    each tested with `[ -f ]` first; names every ref in full under
    refs/remotes/origin/ and fetches no tags; checks the PR's base before reading
    anything; reads the mode before any guard; and guards only the required arm."""
    fence = _gate_fence()
    stripped = [line.strip() for line in fence]
    text = "\n".join(fence)
    assert ".adlc/partials" not in text and ".adlc/tools" not in text
    sourcing = [line for line in stripped
                if line.startswith(". ") or re.search(r"(?:;|&&|\|\||\bthen|\belse|\bdo)\s+\.\s", line)]
    assert sourcing == list(GATE_SOURCES), sourcing
    assert stripped.index(GATE_INSTALLED) < stripped.index(GATE_SOURCES[0])
    for var, name in (("rgt_home", "adlc-home"), ("rgt_forge", "forge"), ("rgt_part", "regression-check")):
        assert '%s="$ADLC_TOOLKIT_ROOT/partials/%s.sh"' % (var, name) in GATE_PATHS
        assert '[ ! -f "$%s" ]' % var in GATE_INSTALLED
    # The provider is resolved by the installed forge_config.py, so the adapter
    # never runs a forge_config.py from the tree.
    assert "ADLC_FORGE_PROVIDER_OVERRIDE=\"$rgt_prov\" adlc_forge_pr_view" in GATE_PR_BASE
    # Full refs only: every `origin/` is `refs/remotes/origin/`, and `--base` is always it.
    for match in re.finditer(r"origin/", text):
        assert text[:match.start()].endswith("refs/remotes/"), text[match.start() - 30:match.end() + 10]
    assert re.findall(r"--base (\"[^\"]*\")", text) == ['"$rgt_base"', '"$rgt_base"']
    assert text.count("--base") == 2
    assert GATE_REFS in stripped
    assert "--no-tags" in GATE_FETCH and text.count("git fetch") == 1
    # The PR's base before the fetch, the fetch before the mode, the mode before any guard.
    assert stripped.index(GATE_PR_BASE) < stripped.index(GATE_FETCH) < stripped.index(GATE_MODE)
    guards = [stripped.index(g) for g in GATE_GUARDS]
    assert stripped.index(GATE_MODE) < stripped.index(GATE_OFF_ARM) < stripped.index(GATE_REQUIRED_ARM) < min(guards)
    # The off arm is empty, and the no-config branch is the off lines alone.
    no_config = stripped.index(GATE_NO_CONFIG)
    assert stripped[no_config - 1] == "else" and stripped[no_config + 1] == "fi"
    assert text.count("git status") == 1 and text.count("git rev-parse HEAD") == 1
    # No checkout-root guard and no diff guard: code no longer comes from the tree.
    assert "git diff" not in text and "--show-prefix 2>&1" not in text


def test_gate_fence_allowlist_both_ways():
    """LESSON-619: the allowlist that gates execution passes the real fence and
    fails a fence carrying anything foreign, in the same run."""
    fence = _sh_fences(_companion_sections()["Gate"])[0]
    assert _fence_offenders(fence) == []
    end = len(fence) - 1
    for foreign in ('rm -rf "$HOME"', "printf x; curl https://example.com", 'elif [ -n "$(curl x)" ]; then',
                    "git -c core.pager=sh log", 'echo "`id`"', '"$rgt_bug" --version', 'eval "$rgt_bug"',
                    "rgt_rc=$(id)", "python3 -c pass", '. "$rgt_bug"', ". .adlc/partials/forge.sh",
                    "sed -i s/a/b/ x", "git diff --quiet", "git cat-file -p HEAD", "adlc_forge_pr_merge 7",
                    "{ id; }", 'rgt_mode=$(id)', 'ADLC_FORGE_PROVIDER_OVERRIDE=x id'):
        planted = fence[:end] + [foreign] + fence[end:]
        assert _fence_offenders(planted), foreign


@pytest.mark.parametrize("shell", SHELLS)
def test_gate_required_pass_and_fail(shell, tmp_path):
    """BR-13: in a required project the fence sources the installed partials, reads
    the mode at refs/remotes/origin/<integration-branch>, and the installed engine
    passes a recorded bug and fails one that recorded nothing."""
    sh = _shell(shell)
    lab = _Lab(tmp_path / "pass")
    lab.base({".adlc/config.yml": REQUIRED, ".adlc/bugs/.keep": ""})
    lab.fix({".adlc/bugs/BUG-123-thing.md": RECORDED, "tests/test_123.py": "# BUG-123\n"})
    out = lab.run(sh)
    for marker in INSTALLED:
        assert marker in out, (marker, out)
    assert ("regression-test: required\nbugfix.regression_test is required in .adlc/config.yml at "
            "refs/remotes/origin/dev\nregression-check: pass\npassed=1 waived=0 legacy=0 failed=0\n") in out, out
    assert _rc(out) == 0

    lab = _Lab(tmp_path / "fail")
    lab.base({".adlc/config.yml": REQUIRED})
    lab.fix({".adlc/bugs/BUG-123-thing.md": UNRECORDED})
    out = lab.run(sh)
    assert ("regression-check: fail\npassed=0 waived=0 legacy=0 failed=1\n"
            "BUG-123: neither regression_tests nor regression_waiver is recorded\n") in out, out
    assert _rc(out) == 1


@pytest.mark.parametrize("shell", SHELLS)
def test_gate_reads_the_branch_never_a_tag(shell, tmp_path):
    """A tag named origin/dev, or refs/remotes/origin/dev, at a commit whose config
    says off, never stands in for the integration branch: the fetch takes no tags,
    and every read names refs/remotes/origin/dev in full (git resolves a short
    origin/dev to the tag first)."""
    sh = _shell(shell)
    lab = _Lab(tmp_path)
    lab.commit({".adlc/config.yml": OFF}, "off, where the tags point")
    lab.git("tag", "origin/dev")
    lab.git("tag", "refs/remotes/origin/dev")
    lab.git("push", "-q", "origin", "refs/tags/origin/dev", "refs/tags/refs/remotes/origin/dev")
    lab.base({".adlc/config.yml": REQUIRED})
    lab.fix({".adlc/bugs/BUG-123-thing.md": UNRECORDED})
    lab.git("update-ref", "-d", "refs/remotes/origin/dev")
    out = lab.run(sh)
    assert "regression-test: required\nbugfix.regression_test is required in .adlc/config.yml at refs/remotes/origin/dev\n" in out, out
    assert "BUG-123: neither regression_tests nor regression_waiver is recorded" in out, out
    _never(out, "regression-test: off", "regression-check: off")
    assert _rc(out) == 1


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("plant", ["symlinked-adlc", "ignored-partial", "skip-worktree", "committed-partial"])
def test_gate_never_runs_code_from_the_tree(shell, plant, tmp_path):
    """The re-verify findings: a symlinked `.adlc` carrying forged partials, a forged
    partial git ignores, a vendored partial edited behind `skip-worktree`, and forged
    partials committed on the fix branch. None of them is ever sourced; the
    installed partials are, and the installed engine gives the verdict."""
    sh = _shell(shell)
    lab = _Lab(tmp_path)
    forged = dict((".adlc/partials/%s.sh" % name, FORGED) for name in ("regression-check", "forge", "adlc-home"))
    base = {".adlc/config.yml": REQUIRED}
    if plant == "skip-worktree":
        base[".adlc/partials/regression-check.sh"] = 'echo "VENDORED-RAN"\n'
    lab.base(base)
    expect = "BUG-123: neither regression_tests nor regression_waiver is recorded\n"
    if plant == "symlinked-adlc":
        lab.git("mv", ".adlc", "adlc-real")
        for rel, text in forged.items():
            lab.write("adlc-real/" + rel[len(".adlc/"):], text)
        os.symlink("adlc-real", str(lab.work / ".adlc"))
        lab.fix({"adlc-real/bugs/BUG-123-thing.md": UNRECORDED})
    elif plant == "ignored-partial":
        lab.fix({".gitignore": ".adlc/partials/\n", ".adlc/bugs/BUG-123-thing.md": RECORDED,
                 "tests/test_123.py": "# BUG-123\n"})
        for rel, text in forged.items():
            lab.write(rel, text)
        expect = "regression-check: pass\npassed=1 waived=0 legacy=0 failed=0\n"
    elif plant == "skip-worktree":
        lab.fix({".adlc/bugs/BUG-123-thing.md": UNRECORDED})
        lab.git("update-index", "--skip-worktree", ".adlc/partials/regression-check.sh")
        lab.write(".adlc/partials/regression-check.sh", FORGED)
    else:
        lab.fix(dict(forged, **{".adlc/bugs/BUG-123-thing.md": UNRECORDED}))
    out = lab.run(sh)
    _never(out, "FORGED-RAN", "VENDORED-RAN")
    for marker in INSTALLED:
        assert marker in out, (marker, out)
    assert "regression-test: required\n" in out and expect in out, out


@pytest.mark.parametrize("shell", SHELLS)
def test_gate_refuses_itself_and_a_retargeted_pr(shell, tmp_path):
    """The integration branch is never the fix branch (a branch that names itself
    `branches.integration` and turns its gate off), and the PR must target it: one
    retargeted at another branch, or one the forge does not know, is refused before
    anything is fetched or read. A PR that targets it reads the base's setting."""
    sh = _shell(shell)
    lab = _Lab(tmp_path)
    lab.base({".adlc/config.yml": REQUIRED})
    lab.fix({".adlc/config.yml": "branches:\n  integration: %s\n%s" % (FIX, OFF),
             ".adlc/bugs/BUG-123-thing.md": UNRECORDED})
    out = lab.run(sh, ib=FIX)
    assert "regression gate: the integration branch is the fix branch, fix/bug-123-thing" in out, out
    _never(out, "regression-test:", "regression-check:", *INSTALLED)
    assert _rc(out) == 2
    lab.prs((7, "release"), (8, "dev"))
    for pr in ("7", "99"):
        out = lab.run(sh, pr=pr)
        assert "regression gate: PR %s does not target dev, or the forge could not say" % pr in out, out
        _never(out, "regression-test:", "regression-check:")
        assert _rc(out) == 2
    out = lab.run(sh, pr="8")
    assert "regression-test: required\n" in out, out
    assert "BUG-123: neither regression_tests nor regression_waiver is recorded" in out, out
    assert _rc(out) == 1


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("base", ["set-off", "no-config", "no-adlc"])
def test_gate_off_has_no_guards(shell, base, tmp_path):
    """BR-1: a project that is off at the integration branch, set or with no
    config, gets no new stop: an untracked file, an unpushed commit and a vendored
    partial in the fix checkout change nothing, and the fence continues. With no
    config the fence answers without the engine, in the engine's own words."""
    sh = _shell(shell)
    lab = _Lab(tmp_path)
    lab.base({"set-off": {".adlc/config.yml": OFF}, "no-config": {".adlc/bugs/.keep": ""},
              "no-adlc": {}}[base])
    lab.fix({".adlc/partials/regression-check.sh": FORGED})
    lab.commit({"unpushed.txt": "never pushed\n"}, "unpushed")
    lab.write("untracked.txt", "not committed\n")
    out = lab.run(sh)
    _never(out, "FORGED-RAN", "uncommitted changes", "HEAD is not", "regression-check:")
    lines = out.splitlines()
    assert lines[-3] == "regression-test: off" and _rc(out) == 0, out
    assert "\n".join(lines[-3:-1]) + "\n" == lab.engine("mode", "--base", "refs/remotes/origin/dev"), out


@pytest.mark.parametrize("shell", SHELLS)
def test_gate_no_config_answer_never_hides_an_error(shell, tmp_path):
    """The fence answers `off` itself only where the engine would: a `.adlc` that is
    not a directory at the integration branch goes to the engine, whose error stops."""
    sh = _shell(shell)
    lab = _Lab(tmp_path)
    lab.write("adlc-real/notes.md", "x\n")
    os.symlink("adlc-real", str(lab.work / ".adlc"))
    lab.base({})
    lab.fix({"fix.txt": "the fix\n"})
    out = lab.run(sh)
    lines = out.splitlines()
    assert lines[-3:-1] == ["regression-test: error",
                            ".adlc is not a directory at refs/remotes/origin/dev; the check reads the "
                            "config only from a real .adlc/config.yml"], out
    assert _rc(out) == 2


@pytest.mark.parametrize("shell", SHELLS)
def test_gate_reads_a_subdirectory_projects_own_config(shell, tmp_path):
    """The fence runs from the project directory, which may be below the repo's
    root; the setting is the project's own, at its path in the integration branch,
    whatever the repo's root carries."""
    sh = _shell(shell)
    lab = _Lab(tmp_path / "required")
    lab.base({".adlc/config.yml": OFF, "sub/proj/.adlc/config.yml": REQUIRED})
    lab.fix({"sub/proj/.adlc/bugs/BUG-123-thing.md": UNRECORDED})
    out = lab.run(sh, cwd=lab.work / "sub" / "proj")
    assert ("regression-test: required\nbugfix.regression_test is required in .adlc/config.yml at "
            "refs/remotes/origin/dev\n") in out, out
    assert "BUG-123: neither regression_tests nor regression_waiver is recorded" in out, out
    assert _rc(out) == 1

    lab = _Lab(tmp_path / "off")
    lab.base({".adlc/config.yml": REQUIRED, "sub/proj/.adlc/bugs/.keep": ""})
    lab.fix({"sub/proj/.adlc/bugs/BUG-123-thing.md": UNRECORDED})
    lab.write("sub/proj/untracked.txt", "not committed\n")
    out = lab.run(sh, cwd=lab.work / "sub" / "proj")
    assert "regression-test: off\n.adlc/config.yml does not exist at refs/remotes/origin/dev," in out, out
    assert _rc(out) == 0


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("plant, reason", [
    ("untracked", "regression gate: the fix checkout has uncommitted changes"),
    ("unpushed", "regression gate: HEAD is not refs/remotes/origin/fix/bug-123-thing"),
    ("never-pushed", "regression gate: fetch of dev or fix/bug-123-thing from origin failed"),
])
def test_gate_required_guards(shell, plant, reason, tmp_path):
    """LESSON-718, required mode only: an uncommitted file, an unpushed record, or a
    fix branch that was never pushed stops the gate with one line, unchecked."""
    sh = _shell(shell)
    lab = _Lab(tmp_path)
    lab.base({".adlc/config.yml": REQUIRED})
    lab.fix({".adlc/bugs/BUG-123-thing.md": RECORDED, "tests/test_123.py": "# BUG-123\n"},
            push=plant != "never-pushed")
    if plant == "untracked":
        lab.write("notes.txt", "not committed\n")
    elif plant == "unpushed":
        lab.commit({"record.md": "a record that was never pushed\n"}, "unpushed")
    out = lab.run(sh)
    assert reason in out, out
    _never(out, "regression-check:")
    if plant != "never-pushed":
        assert "regression-test: required\n" in out, out
    assert _rc(out) == 2


@pytest.mark.parametrize("shell", SHELLS)
def test_gate_refuses_bad_ids_and_branch_names(shell, tmp_path):
    """The id, both branch names and the PR number are validated before anything
    else runs: a valid id reaches the check, anything else never does, and a
    substituted value can never inject a command."""
    sh = _shell(shell)
    lab = _Lab(tmp_path)
    lab.base({".adlc/config.yml": REQUIRED})
    lab.fix({".adlc/bugs/BUG-123-thing.md": RECORDED, "tests/test_123.py": "# BUG-123\n"})
    out = lab.run(sh)
    assert "regression-check: pass" in out and _rc(out) == 0, out
    for good in ("BUG-1234", "BUG-12345", "BUG-123456"):
        out = lab.run(sh, bug=good)
        assert "%s: no bug report in .adlc/bugs" % good in out, (good, out)
        assert _rc(out) == 1, (good, out)
    bad_ids = ("BUG-12", "BUG-1234567", "bug-123", "BUG-12a", " BUG-123", "BUG-123 ", "",
               "BUG-123\nBUG-456", "BUG-123'; echo INJECTED; '", "BUG-123; echo INJECTED")
    bad_refs = ("", "-x", "--upload-pack=echo INJECTED", "a..b", ".hidden", "a/.b", "/abs", "trail/",
                "a//b", "x.lock", "x.", "foo bar", "x$(echo INJECTED)", "x`echo INJECTED`",
                "x'; echo INJECTED; '", "x;echo INJECTED", "a\nb", "@{-1}", "x~1", "x^", "x:y")
    bad_prs = ("", "7a", "-7", "7 ", " 7", "#7", "7;echo INJECTED", "$(echo INJECTED)", "7\n8")
    cases = [(b, None, None, None, "is not a bug id") for b in bad_ids]
    cases += [(None, r, None, None, "is not a branch name") for r in bad_refs]
    cases += [(None, None, r, None, "is not a branch name") for r in bad_refs]
    cases += [(None, None, None, p, "is not a PR number") for p in bad_prs]
    for bug, fix, ib, pr, reason in cases:
        kw = dict((k, v) for k, v in (("bug", bug), ("fix", fix), ("ib", ib), ("pr", pr)) if v is not None)
        out = lab.run(sh, **kw)
        assert reason in out, (kw, out)
        assert "INJECTED" not in out.splitlines(), (kw, out)
        _never(out, "regression-test:", "regression-check:", *INSTALLED)
        assert _rc(out) == 2, (kw, out)


def test_contrast_sentence_outside_rules_block():
    """BR-16: the recorded pre-fix-fail / post-fix-pass run is named as the
    capture step's contrast and evidence, beside the reproduce-then-fix line and
    outside the capture-rules block, which stays equal to /wrapup's."""
    skill = _read(SKILL)
    lines = skill.splitlines()
    fenced = _fenced_line_numbers(lines)
    opens = [i for i, line in enumerate(lines) if i not in fenced and line.strip() == "<!-- lesson-capture-rules -->"]
    closes = [i for i, line in enumerate(lines) if i not in fenced and line.strip() == "<!-- /lesson-capture-rules -->"]
    assert len(opens) == 1 and len(closes) == 1 and opens[0] < closes[0], (opens, closes)
    block = range(opens[0], closes[0] + 1)
    anchor = [i for i, line in enumerate(lines)
              if line == "A reproduce-then-fix sequence is a contrast (rule 2); name it in `evidence`."]
    sentence = [i for i, line in enumerate(lines)
                if "pre-fix-fail / post-fix-pass run recorded in the bug report's `## Regression Test` section "
                   "is that contrast" in line]
    assert len(anchor) == 1 and len(sentence) == 1, (anchor, sentence)
    assert sentence[0] not in block and sentence[0] not in fenced
    assert closes[0] < anchor[0] and sentence[0] == anchor[0] + 1
    assert "cite it as the lesson's `evidence`" in lines[sentence[0]]
    assert "first failing assertion line" in lines[sentence[0]]
    write_point = [i for i, line in enumerate(lines) if i not in fenced and line.strip() == "<!-- lesson-write-point -->"]
    step4 = [i for i, line in enumerate(lines) if line.startswith("**Step 4 — Capture knowledge**")]
    assert len(write_point) == 1 and len(step4) == 1
    assert step4[0] < sentence[0] < write_point[0]

    wrapup = _read("wrapup/SKILL.md").splitlines()
    w_fenced = _fenced_line_numbers(wrapup)
    w_open = [i for i, line in enumerate(wrapup) if i not in w_fenced and line.strip() == "<!-- lesson-capture-rules -->"]
    w_close = [i for i, line in enumerate(wrapup) if i not in w_fenced and line.strip() == "<!-- /lesson-capture-rules -->"]
    assert len(w_open) == 1 and len(w_close) == 1
    assert lines[opens[0]:closes[0] + 1] == wrapup[w_open[0]:w_close[0] + 1]
