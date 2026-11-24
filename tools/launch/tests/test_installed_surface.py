"""The installed-surface guard and the launch README (REQ-672 TASK-284: BR-6, BR-8, AC-8, AC-10).

BR-6: adoption is measured only from statistics the platforms already give the owner.
Nothing an installed copy of the toolkit runs reads them or reaches ``tools/launch``.

AC-8: among the launch tools, only ``adoption_snapshot.py`` reads adoption statistics,
and only with read requests. The e2e driver and the recording script reach GitHub and
Claude only when the maintainer runs them with ``--with-model``. Every ``gh`` call a
launch tool may make is listed here, per module, and any other fails: every ``.py`` and
``.sh`` file under ``tools/launch`` but its tests is read, gh is recognised in any case,
through a variable bound to it and behind ``env`` or ``command``, and each module allowed
``gh api`` is held to reads.

The last section holds REQ-672's task files to tests that exist: each ``path::name`` in a
``## Verification`` table names a file that defines that test.

The scans walk the real tree from this file's own location and say how much they read,
so a walk that found nothing cannot pass (LESSON-019). Each test runs the same scanning
function over a small copy or a synthetic source, once clean and once with a violation,
so the guard is shown to fire and to stay quiet.
"""
import ast
import collections
import importlib.util
import os
import re

import pytest

HERE = os.path.dirname(os.path.realpath(__file__))
LAUNCH = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(LAUNCH))
README = os.path.join(LAUNCH, "README.md")
SNAPSHOT = "adoption_snapshot.py"

# --- BR-6: the installed surface --------------------------------------------------------

#: Directories an installed copy holds and may run or read, walked whole, beside every
#: top-level directory that holds a SKILL.md (its companions and proceed's phase files
#: included). ``tools/dataset`` is a maintainer tool, scanned to show that its Hub client
#: (REQ-671) is not a statistics read. ``examples/`` holds the quickstart's
#: ``new-project.sh``, which runs ``gh repo create`` and must stay quiet.
#:
#: Not scanned: ``docs/`` (the quickstart, the launch checklist and the drafted posts),
#: the root ``README.md``, ``RELEASING.md`` and ``CHANGELOG.md``, and ``.adlc/``. They are
#: documentation that names these tools on purpose, and an installed copy runs nothing
#: in them.
SURFACE_DIRS = ("agents", "partials", "hooks", "scripts", "workflows", "templates",
                "presets", "harness", "examples", "space", ".claude-plugin", ".cursor-plugin",
                ".github", "tools/adlc", "tools/delegate", "tools/lint-skills", "tools/dataset")
#: Single files, each scanned when present.
SURFACE_FILES = ("install.sh", ".claude/settings.json")
#: Applied to directories found below a scanned directory, never to the scan's root or
#: to a family's own directory: this repo is often checked out under a name such a list
#: could hold (LESSON-019).
SKIP_DIRS = ("__pycache__", ".git", ".pytest_cache", "node_modules")

#: The statistics reads BR-6 keeps off the installed surface: the snapshot, its file and
#: its diagnostics; GitHub's traffic endpoints and the repo's statistics fields; the Hub's
#: statistics endpoints; and the Hub client's two info reads. ``tools/dataset/publish.py``
#: uses other Hub client calls (``whoami``, ``repo_exists``, ``create_commit`` and the
#: like), none of which reads a statistic, and it stays quiet.
STATISTICS_PATTERNS = ("adoption_snapshot", "adoption-snapshot", "traffic/", "/stargazers",
                       "stargazers_count", "subscribers_count", "huggingface.co/api/datasets",
                       "huggingface.co/api/spaces", "dataset_info(", "space_info(")
#: The launch tools' directory, as a path and as a sibling's relative path, found line
#: by line.
LAUNCH_PATTERNS = (
    ("tools/launch", re.compile(r"tools/launch")),
    ("../launch/", re.compile(r"\.\./launch/")),
)
#: A separator a concatenation puts between two segments: ``os.sep``, ``os.path.sep``, or
#: a quoted ``/`` or ``\\``.
_SEP = r"""(?:os\.(?:path\.)?sep|["'](?:/|\\\\)["'])"""
#: The same directory put together from its segments, found in a file's whole text, so a
#: join split across lines is found too: by a join or a ``/`` (``os.path.join("tools",
#: "launch")``, ``ROOT / "tools" / "launch"``), and by concatenation (``"tools" + os.sep +
#: "launch"``, ``"tools/" + "launch"``). Each is reported on the line where it starts.
JOINED_PATTERNS = (
    ("'tools', 'launch'", re.compile(r"""["']tools["']\s*[,/]\s*["']launch["']""")),
    ("'tools' + 'launch'", re.compile(
        r"""["']tools(?:/|\\\\)?["']\s*\+\s*(?:%s\s*\+\s*)?["'](?:/|\\\\)?launch""" % _SEP)),
)
#: The order findings on one line are reported in.
PATTERN_ORDER = (STATISTICS_PATTERNS + tuple(name for name, _ in LAUNCH_PATTERNS)
                 + tuple(name for name, _ in JOINED_PATTERNS))
#: The lint mirrors two parsers here and names their files: ``quickstart_steps.py``'s
#: marker pattern (ADR-2) and ``launch_checklist.py``'s table parser. On a line of these
#: files, those exact paths, whole or as segments, are the only mentions of the launch
#: tools allowed. Any other mention is a finding, and so is any mention in another file
#: under ``tools/lint-skills``.
LINT_NAMING_FILES = ("tools/lint-skills/check.py", "tools/lint-skills/README.md")
LINT_TESTS = "tools/lint-skills/tests/"
LINT_MIRRORED = ("quickstart_steps", "launch_checklist")
LINT_ALLOWED = re.compile(
    r"""tools/launch/(?:%(names)s)\.py(?![\w/-])"""
    r"""|["']tools["']\s*[,/]\s*["']launch["']\s*[,/]\s*["'](?:%(names)s)\.py["']"""
    % {"names": "|".join(LINT_MIRRORED)})
#: The tree this guard landed on held well over this many surface files.
SCANNED_FLOOR = 300
#: Every family that must have been read for a green to mean anything.
REQUIRED_FAMILIES = ("skills", "agents", "partials", "hooks", "scripts", "workflows",
                     "templates", "install.sh", "examples", "space", ".claude-plugin",
                     ".cursor-plugin", ".github", "tools/adlc", "tools/delegate",
                     "tools/lint-skills", "tools/dataset")


def _walk(root, top):
    """Every file under ``root/top``, relative to ``root``, skipping SKIP_DIRS below it."""
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            if os.path.isfile(path):
                yield os.path.relpath(path, root).replace(os.sep, "/")


def surface_files(root):
    """``(family, relative path)`` for every file of the installed surface under ``root``."""
    found = collections.OrderedDict()
    for name in sorted(os.listdir(root)):
        if os.path.isfile(os.path.join(root, name, "SKILL.md")):
            for rel in _walk(root, name):
                found.setdefault(rel, "skills")
    for family in SURFACE_DIRS:
        if os.path.isdir(os.path.join(root, family)):
            for rel in _walk(root, family):
                found.setdefault(rel, family)
    for name in SURFACE_FILES:
        if os.path.isfile(os.path.join(root, name)):
            found.setdefault(name, name)
    return [(family, rel) for rel, family in found.items()]


def read_text(path):
    """The file's text, or None for a binary file (one holding a NUL byte)."""
    with open(path, "rb") as handle:
        data = handle.read()
    if b"\0" in data:
        return None
    return data.decode("utf-8", "replace")


def lint_may_name_the_parser(rel):
    """True for the lint files that may name the parsers in LINT_MIRRORED."""
    return rel in LINT_NAMING_FILES or rel.startswith(LINT_TESTS)


def line_findings(rel, line):
    """The patterns one line of the surface file at ``rel`` names."""
    found = [pattern for pattern in STATISTICS_PATTERNS if pattern in line]
    probe = LINT_ALLOWED.sub("", line) if lint_may_name_the_parser(rel) else line
    found += [name for name, regex in LAUNCH_PATTERNS if regex.search(probe)]
    return found


def file_findings(rel, text):
    """``(line, pattern)`` for each pattern the surface file at ``rel`` names, in line
    order: the line patterns per line, and JOINED_PATTERNS over the whole text. An allowed
    mention in a lint file is blanked first, keeping its line breaks, so the line numbers
    of what follows it stay true."""
    found = set()
    for number, line in enumerate(text.splitlines(), 1):
        found.update((number, pattern) for pattern in line_findings(rel, line))
    probe = text
    if lint_may_name_the_parser(rel):
        probe = LINT_ALLOWED.sub(lambda match: "\n" * match.group(0).count("\n"), text)
    for name, regex in JOINED_PATTERNS:
        for match in regex.finditer(probe):
            found.add((probe.count("\n", 0, match.start()) + 1, name))
    return sorted(found, key=lambda hit: (hit[0], PATTERN_ORDER.index(hit[1])))


def scan(root):
    """``(findings, counts)``: one ``path:line: names <pattern>`` per hit, files read per family."""
    findings, counts = [], collections.Counter()
    for family, rel in surface_files(root):
        text = read_text(os.path.join(root, rel))
        if text is None:
            continue
        counts[family] += 1
        for number, pattern in file_findings(rel, text):
            findings.append("%s:%d: names %s" % (rel, number, pattern))
    return findings, counts


def _put(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _append(path, text):
    """Append ``text`` as the last line of ``path``; return that line's number."""
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text + "\n")
    with open(path, encoding="utf-8") as handle:
        return len(handle.read().splitlines())


def test_no_installed_surface_reads_adoption_statistics(tmp_path, capsys):
    assert os.path.isfile(os.path.join(ROOT, ".claude-plugin", "plugin.json")), ROOT
    findings, counts = scan(ROOT)
    total = sum(counts.values())
    with capsys.disabled():
        print("\ninstalled-surface: scanned %d file(s) (%s)" % (
            total, ", ".join("%s %d" % (family, counts[family]) for family in sorted(counts))))
    assert findings == [], "\n".join(findings)
    assert total > SCANNED_FLOOR, counts
    for family in REQUIRED_FAMILIES:
        assert counts[family] > 0, family
    # The scope is the statistics reads, not the Hub: the dataset's publish step uses the
    # Hub client and names the Hub (REQ-671), was read, and is quiet. (The client's module
    # name is not spelled here: tools/dataset's own guard confines it to that step.)
    scanned = {rel for _, rel in surface_files(ROOT)}
    for rel in ("tools/dataset/publish.py", "spec/SKILL.md", "examples/quickstart/new-project.sh",
                "tools/lint-skills/check.py"):
        assert rel in scanned, rel
    publish = read_text(os.path.join(ROOT, "tools", "dataset", "publish.py"))
    assert "HfApi" in publish and "https://huggingface.co/" in publish
    assert "gh repo create" in read_text(os.path.join(ROOT, "examples", "quickstart",
                                                      "new-project.sh"))

    # A root under a directory SKIP_DIRS names is still walked (LESSON-019).
    copy = str(tmp_path / "__pycache__" / "toolkit")
    skill = _put(copy, "spec/SKILL.md", read_text(os.path.join(ROOT, "spec", "SKILL.md")))
    assert scan(copy) == ([], {"skills": 1})
    last = _append(skill, "Then run `python3 tools/launch/adoption_snapshot.py` weekly.")
    assert scan(copy)[0] == ["spec/SKILL.md:%d: names adoption_snapshot" % last,
                             "spec/SKILL.md:%d: names tools/launch" % last]


def test_the_lint_may_name_only_the_parsers_it_mirrors(tmp_path):
    """Under tools/lint-skills, the only allowed mentions are the paths of the two parsers
    the lint mirrors, in check.py, the lint's README or its tests."""
    # A copy of the real check.py: a line that runs another launch tool is a finding.
    real = str(tmp_path / "real")
    check = _put(real, "tools/lint-skills/check.py",
                 read_text(os.path.join(ROOT, "tools", "lint-skills", "check.py")))
    before = scan(real)[0]
    last = _append(check, 'subprocess.run(["python3", "tools/launch/adoption_snapshot.py"])')
    assert sorted(set(scan(real)[0]) - set(before)) == [
        "tools/lint-skills/check.py:%d: names adoption_snapshot" % last,
        "tools/lint-skills/check.py:%d: names tools/launch" % last]

    lint = str(tmp_path / "lint")
    allowed = ('ANCHOR = "tools/launch/quickstart_steps.py"\n'
               "#: a mirror of tools/launch/launch_checklist.py's ``parse``.\n")
    _put(lint, "tools/lint-skills/check.py", allowed)
    _put(lint, "tools/lint-skills/README.md", "a mirror of `tools/launch/quickstart_steps.py`'s\n")
    _put(lint, "tools/lint-skills/tests/test_mirror.py",
         'PATH = ROOT / "tools" / "launch" / "quickstart_steps.py"\n'
         'OTHER = os.path.join(ROOT, "tools", "launch", "launch_checklist.py")\n'
         'SPLIT = os.path.join(ROOT, "tools",\n'
         '                     "launch", "launch_checklist.py")\n')
    assert scan(lint) == ([], {"tools/lint-skills": 3})

    _put(lint, "tools/lint-skills/check.py", allowed + "# the lint does not import tools/launch\n"
         "RECORD = 'tools/launch/record_demo.py'\n")
    _put(lint, "tools/lint-skills/tests/test_mirror.py",
         'BAD = ROOT / "tools" / "launch" / "adoption_snapshot.py"\n'
         'DIR = os.path.join(ROOT, "tools", "launch")\n'
         'SPLIT = os.path.join(ROOT, "tools",\n'
         '                     "launch")\n'
         'GLUED = "tools" + os.sep + "launch"\n')
    _put(lint, "tools/lint-skills/mirror.py", 'PARSER = "tools/launch/quickstart_steps.py"\n')
    assert sorted(scan(lint)[0]) == [
        "tools/lint-skills/check.py:3: names tools/launch",
        "tools/lint-skills/check.py:4: names tools/launch",
        "tools/lint-skills/mirror.py:1: names tools/launch",
        "tools/lint-skills/tests/test_mirror.py:1: names 'tools', 'launch'",
        "tools/lint-skills/tests/test_mirror.py:1: names adoption_snapshot",
        "tools/lint-skills/tests/test_mirror.py:2: names 'tools', 'launch'",
        "tools/lint-skills/tests/test_mirror.py:3: names 'tools', 'launch'",
        "tools/lint-skills/tests/test_mirror.py:5: names 'tools' + 'launch'"]


def test_the_guard_reads_the_whole_installed_copy_and_every_spelling(tmp_path):
    """examples/, the manifests, .github/, space/ and the settings file are scanned, and a
    path, a statistics field or a Hub info read spelled another way is still found."""
    copy = str(tmp_path / "copy")
    script = _put(copy, "examples/quickstart/new-project.sh",
                  read_text(os.path.join(ROOT, "examples", "quickstart", "new-project.sh")))
    for rel in (".claude-plugin/plugin.json", ".cursor-plugin/plugin.json",
                ".claude/settings.json"):
        _put(copy, rel, read_text(os.path.join(ROOT, *rel.split("/"))))
    _put(copy, ".github/plugin/plugin.json", "{}\n")
    _put(copy, "space/app.js", "export const x = 1;\n")
    findings, counts = scan(copy)
    assert findings == []
    assert counts == {"examples": 1, ".claude-plugin": 1, ".cursor-plugin": 1, ".github": 1,
                      "space": 1, ".claude/settings.json": 1}
    # The script's own gh calls are quiet; a statistics read planted in it is not.
    last = _append(script, "gh api repos/x/y/traffic/views")
    assert scan(copy)[0] == ["examples/quickstart/new-project.sh:%d: names traffic/" % last]

    other = str(tmp_path / "other")
    _put(other, "partials/a.py", 'P = os.path.join(ROOT, "tools", "launch", "snap.py")\n')
    _put(other, "tools/adlc/b.py", 'sys.path.insert(0, os.path.join(HERE, "../launch/"))\n')
    _put(other, "hooks/c.sh", "gh api repos/o/n/stargazers --paginate\n")
    _put(other, "space/d.js", "const n = repo.subscribers_count;\n")
    _put(other, "tools/dataset/e.py", "info = api.dataset_info(repo_id)\n")
    _put(other, ".github/f.yml", "run: python3 -c 'api.space_info(x)'\n")
    _put(other, ".claude/settings.json", '{"allow": ["Bash(python3 tools/launch/x.py)"]}\n')
    # Segments joined across a line break, or concatenated, name the directory too; the
    # hit is on the line where the join starts.
    _put(other, "scripts/g.py", 'import os\nP = os.path.join(ROOT, "tools",\n'
                                '                 "launch", "x.py")\n')
    _put(other, "hooks/h.py", 'P = ROOT + os.sep + "tools" + os.sep + "launch"\n')
    _put(other, "agents/i.py", "P = 'tools/' + 'launch'\nQ = ('tools' +\n     '/launch')\n")
    assert sorted(scan(other)[0]) == [
        ".claude/settings.json:1: names tools/launch",
        ".github/f.yml:1: names space_info(",
        "agents/i.py:1: names 'tools' + 'launch'",
        "agents/i.py:2: names 'tools' + 'launch'",
        "hooks/c.sh:1: names /stargazers",
        "hooks/h.py:1: names 'tools' + 'launch'",
        "partials/a.py:1: names 'tools', 'launch'",
        "scripts/g.py:2: names 'tools', 'launch'",
        "space/d.js:1: names subscribers_count",
        "tools/adlc/b.py:1: names ../launch/",
        "tools/dataset/e.py:1: names dataset_info("]
    # Benign: the two words apart, or another directory joined, are not the path.
    quiet = str(tmp_path / "quiet")
    _put(quiet, "scripts/j.py", 'A = os.path.join(ROOT, "tools", "lint-skills")\n'
                                'B = "tools" + os.sep + "dataset"\nC = ["launch", "tools"]\n')
    assert scan(quiet) == ([], {"scripts": 1})


# --- AC-8: only the snapshot reads statistics; every gh call is listed -------------------

#: Modules that open a network connection. An import of one, or of anything under it,
#: counts, by ``import``, ``from ... import``, ``__import__`` or ``import_module``.
NETWORK_MODULES = ("urllib", "http.client", "socket", "ssl", "ftplib", "smtplib",
                   "requests", "urllib3", "httpx", "aiohttp")
#: The statistics endpoints and fields a launch tool could name; the Hub's API root
#: covers both of its statistics reads.
LAUNCH_STATISTICS = ("traffic/", "/stargazers", "stargazers_count", "subscribers_count",
                     "huggingface.co/api/")
#: ``gh api`` flags that turn a read into a write.
GH_WRITE_FLAGS = ("--method", "-X", "-f", "-F", "--field", "--raw-field", "--input")
HTTP_WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
_METHOD_RE = re.compile(r"""\bmethod\s*=\s*["'](?!GET["'])""")

#: Every ``gh`` call each launch module may make or spell, as its leading words, keyed by
#: the module's path under ``tools/launch``. An entry allows any call that begins with it;
#: a module not named here may make none. Each entry must match a call the module holds,
#: so the list is what the code does. Every module with an ``api`` entry is also held by
#: write_requests() to calls that carry no write flag.
GH_ALLOWED = {
    # Every read is `gh api <path>`.
    SNAPSHOT: {("api",)},
    # The signed-in login, read once and forbidden in the recording.
    "record_demo.py": {("api", "user")},
    # pr-merged: the throwaway repo's merged pull requests.
    "quickstart_check.py": {("pr", "list")},
    # The sandbox's git credential helper.
    "quickstart_e2e.py": {("auth", "git-credential")},
}
#: Text that spells a gh call without making one, allowed only as this exact string in
#: this module. The refusal that says no throwaway repo was given advises creating one by
#: hand, which the driver never does: any other text that spells `gh repo create` there,
#: and any argv that runs it, is a call no entry allows.
GH_ADVICE = {
    "quickstart_e2e.py": (
        "no throwaway GitHub repo: create an empty one yourself (gh repo create "
        "OWNER/adlc-e2e-YYYYMMDD --private) and pass --throwaway-repo OWNER/NAME",),
}
#: gh's commands. In a string literal, ``gh`` followed by one of these is a call; ``gh``
#: followed by any other word ("gh is not on PATH") is prose.
GH_COMMANDS = frozenset((
    "agent-task", "alias", "api", "attestation", "auth", "browse", "cache", "codespace",
    "completion", "config", "copilot", "extension", "gist", "gpg-key", "help", "issue",
    "label", "org", "pr", "preview", "project", "release", "repo", "ruleset", "run",
    "search", "secret", "ssh-key", "status", "variable", "workflow"))
#: ``gh <command> [<subcommand>]`` in text; the executable's name in any case.
_GH_TEXT_RE = re.compile(
    r"(?<![\w./-])(?i:gh)[ \t]+([a-z][a-z0-9-]*)(?:[ \t]+([a-z][a-z0-9-]*)(?![\w./-]))?")
#: A name that holds the gh executable by its own name, in any case.
_GH_NAME_RE = re.compile(r"^(?:gh|gh_\w+|\w+_gh)$", re.I)
#: The lookups whose result is the executable's path: ``shutil.which`` and the launch
#: modules' own ``_which`` wrappers around it.
_WHICH_CALLS = ("which", "_which")
#: Programs that run the command after them: ``env [-i] [NAME=value ...] gh …`` and
#: ``command gh …``. ``command -v gh`` only looks gh up.
_WRAPPERS = ("env", "command")
_LOOKUP_FLAGS = ("-v", "-V")
#: The ``re`` functions whose first argument is a pattern.
_RE_CALLS = ("compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn",
             "split")
_FETCHER_RE = re.compile(r"(?<![\w-])(?:curl|wget)(?![\w-])")


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _text(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def network_imports(source):
    """The NETWORK_MODULES entries ``source`` imports."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            modules = [base] + ["%s.%s" % (base, alias.name) for alias in node.names]
        elif (isinstance(node, ast.Call) and _call_name(node) in ("__import__", "import_module")
              and node.args and _text(node.args[0])):
            modules = [_text(node.args[0])]
        else:
            continue
        for module in modules:
            for name in NETWORK_MODULES:
                if module == name or module.startswith(name + "."):
                    found.add(name)
    return found


def statistics_hits(text):
    """The LAUNCH_STATISTICS entries ``text`` names."""
    return [pattern for pattern in LAUNCH_STATISTICS if pattern in text]


def write_requests(source):
    """``(problems, seen)``: every place ``source`` could write to a platform, and how
    many ``gh api`` argv lists and ``Request`` calls the analysis read."""
    problems, seen = [], collections.Counter()
    for node in ast.walk(ast.parse(source)):
        value = _text(node)
        if value is not None:
            long_flag = value.startswith("--") and value.split("=", 1)[0] in GH_WRITE_FLAGS
            short_flag = value[:2] in GH_WRITE_FLAGS and not value.startswith("--")
            if long_flag or short_flag:
                problems.append("line %d: gh write flag %r" % (node.lineno, value))
            if value in HTTP_WRITE_METHODS:
                problems.append("line %d: HTTP method %r" % (node.lineno, value))
        if isinstance(node, (ast.List, ast.Tuple)) and "api" in [_text(e) for e in node.elts]:
            seen["gh api argv"] += 1
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        if name == "Request":
            seen["Request"] += 1
            if len(node.args) > 1 or "data" in keywords:
                problems.append("line %d: Request with a body" % node.lineno)
            if "method" in keywords and _text(keywords["method"]) != "GET":
                problems.append("line %d: Request whose method is not GET" % node.lineno)
        if name == "urlopen" and (len(node.args) > 1 or "data" in keywords):
            problems.append("line %d: urlopen with a body" % node.lineno)
        if name in ("request", "putrequest") and node.args and _text(node.args[0]) != "GET":
            problems.append("line %d: %s that is not a GET" % (node.lineno, name))
    for number, line in enumerate(source.splitlines(), 1):
        for flag in GH_WRITE_FLAGS:
            if '"%s"' % flag in line or "'%s'" % flag in line:
                problems.append("line %d: quoted gh write flag %s" % (number, flag))
        if _METHOD_RE.search(line):
            problems.append("line %d: a method other than GET" % number)
    return problems, seen


def _program(value):
    """The program a string names: its last path part, lower-cased, without ``.exe``."""
    base = re.split(r"[/\\]", value)[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def _key(node):
    """The string key of a subscript (``tools["gh"]``), or None."""
    key = node.slice
    if isinstance(key, getattr(ast, "Index", ())):  # Python 3.8's wrapper
        key = key.value
    return _text(key)


def _binding(node):
    """What an assignment target binds, as ``(kind, name)``, or None."""
    if isinstance(node, ast.Name):
        return ("name", node.id)
    if isinstance(node, ast.Attribute):
        return ("attr", node.attr)
    if isinstance(node, ast.Subscript) and _key(node) is not None:
        return ("key", _key(node))
    return None


def gh_bindings(tree):
    """Every target ``tree`` assigns a lookup of the gh executable to (``exe =
    shutil.which("gh")``, ``tools["exe"] = _which("gh", path)``, ``(exe := which("gh"))``),
    as ``_binding`` gives it: a name holding gh under any name is gh too."""
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            targets = [node.target]
        else:
            continue
        value = node.value
        if isinstance(value, ast.Call) and _call_name(value) in _WHICH_CALLS and value.args \
                and _text(value.args[0]) is not None and _program(_text(value.args[0])) == "gh":
            bound.update(_binding(target) for target in targets)
    bound.discard(None)
    return bound


def _is_gh(node, bound=frozenset()):
    """True when ``node`` is the gh executable: the literal in any case (or a path ending in
    it), a name, an attribute or a key named for it, or one of ``bound`` (gh_bindings)."""
    value = _text(node)
    if value is not None:
        return _program(value) == "gh"
    if isinstance(node, ast.Name):
        return bool(_GH_NAME_RE.match(node.id)) or ("name", node.id) in bound
    if isinstance(node, ast.Attribute):
        return bool(_GH_NAME_RE.match(node.attr)) or ("attr", node.attr) in bound
    if isinstance(node, ast.Subscript):
        key = _key(node)
        return key is not None and (_program(key) == "gh" or ("key", key) in bound)
    return False


def _gh_at(elements, bound):
    """Where gh sits in an argv list, or None: its first item, or the first item after an
    ``env`` or ``command`` wrapper and the wrapper's flags and ``NAME=value`` settings."""
    if not elements:
        return None
    if _is_gh(elements[0], bound):
        return 0
    first = _text(elements[0])
    if first is None or _program(first) not in _WRAPPERS:
        return None
    wrapper = _program(first)
    for index, element in enumerate(elements[1:], 1):
        if _is_gh(element, bound):
            return index
        value = _text(element)
        if value is None or (wrapper == "command" and value in _LOOKUP_FLAGS):
            return None
        if not (value.startswith("-") or (wrapper == "env" and "=" in value)):
            return None
    return None


def _not_commands(tree):
    """The ids of the string nodes in ``tree`` that are never run: docstrings, and the
    pattern of a ``re`` call, which is text to match (such as gh's own error message)."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.body and isinstance(node.body[0], ast.Expr) \
                and _text(node.body[0].value) is not None:
            found.add(id(node.body[0].value))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "re" \
                and node.func.attr in _RE_CALLS and node.args:
            found.update(id(part) for part in ast.walk(node.args[0]))
    return found


def gh_calls(source, advice=()):
    """``(calls, fetchers)``: the leading words of every ``gh`` call ``source`` makes or
    spells, and every string literal that names ``curl`` or ``wget``.

    A call is an argv list or tuple with gh first, or after an ``env`` or ``command``
    wrapper (_gh_at; its words: the string literals after gh, up to two, stopping at a flag
    or anything else), or ``gh <command>`` inside a string literal other than a docstring,
    a ``re`` pattern or a string of ``advice`` (up to two words). gh is recognised in any
    case and through a name bound to ``which("gh")`` (gh_bindings)."""
    tree = ast.parse(source)
    not_commands = _not_commands(tree)
    bound = gh_bindings(tree)
    calls, fetchers = set(), []
    for node in ast.walk(tree):
        at = _gh_at(node.elts, bound) if isinstance(node, (ast.List, ast.Tuple)) else None
        if at is not None:
            words = []
            for element in node.elts[at + 1:at + 3]:
                value = _text(element)
                if value is None or value.startswith("-"):
                    break
                words.append(value)
            calls.add(tuple(words))
        value = _text(node)
        if value is None:
            continue
        if _FETCHER_RE.search(value):
            fetchers.append("line %d: %s" % (node.lineno, _FETCHER_RE.search(value).group(0)))
        if id(node) in not_commands or value in advice:
            continue
        for match in _GH_TEXT_RE.finditer(value):
            if match.group(1) in GH_COMMANDS:
                calls.add(tuple(word for word in match.groups() if word))
    return calls, fetchers


#: A shell variable set to the gh executable: ``GH=$(command -v gh)``, ``GH=`which gh```
#: or ``GH=gh``, the name of gh in any case.
_SH_GH_BINDING_RE = re.compile(
    r"""(?:^|[\s;&|(])([A-Za-z_]\w*)=["']?(?:\$\((?:command[ \t]+-v|which)[ \t]+(?i:gh)\)"""
    r"""|`(?:command[ \t]+-v|which)[ \t]+(?i:gh)`|(?i:gh)(?![\w./-]))""", re.M)
#: A shell comment: ``#`` at the start of a line or after a blank.
_SH_COMMENT_RE = re.compile(r"(?:^|[ \t])#.*$")


def shell_gh_calls(text):
    """``(calls, fetchers)`` of a shell script: every ``gh <command> [<subcommand>]`` it
    runs outside a comment, gh by name in any case, quoted or not, or through a variable
    set to it (``"$GH" repo create``), and every line that names ``curl`` or ``wget``."""
    names = sorted({match.group(1) for match in _SH_GH_BINDING_RE.finditer(text)})
    program = "|".join([r"(?i:gh)"] + [r"\$\{?%s\}?" % re.escape(name) for name in names])
    call_re = re.compile(r"""(?<![\w./$-])["']?(?:%s)["']?[ \t]+([a-z][a-z0-9-]*)"""
                         r"""(?:[ \t]+([a-z][a-z0-9-]*)(?![\w./-]))?""" % program)
    calls, fetchers = set(), []
    for number, line in enumerate(text.splitlines(), 1):
        fetchers += ["line %d: %s" % (number, match.group(0))
                     for match in _FETCHER_RE.finditer(line)]
        for match in call_re.finditer(_SH_COMMENT_RE.sub("", line)):
            if match.group(1) in GH_COMMANDS:
                calls.add(tuple(word for word in match.groups() if word))
    return calls, fetchers


def analyse(rel, text):
    """``(network imports, statistics hits, gh calls, fetchers)`` of the launch module at
    ``rel``: a Python module read through its syntax tree, a shell script line by line."""
    if rel.endswith(".sh"):
        calls, fetchers = shell_gh_calls(text)
        return set(), statistics_hits(text), calls, fetchers
    calls, fetchers = gh_calls(text, GH_ADVICE.get(rel, ()))
    return network_imports(text), statistics_hits(text), calls, fetchers


def unlisted(module, calls):
    """The ``calls`` no GH_ALLOWED entry of ``module`` allows."""
    allowed = GH_ALLOWED.get(module, set())
    return sorted(call for call in calls
                  if not any(call[:len(entry)] == entry for entry in allowed))


def api_modules():
    """The modules with an ``api`` entry: write_requests() holds each to reads."""
    return sorted(module for module, entries in GH_ALLOWED.items()
                  if any(entry[:1] == ("api",) for entry in entries))


#: The launch tools' own tests, which the module analysis does not read: they hold the
#: fakes and the violations this file plants.
LAUNCH_TESTS = "tests"
LAUNCH_SUFFIXES = (".py", ".sh")


def launch_modules(root=LAUNCH):
    """``(path under root, absolute path)`` of every ``.py`` and ``.sh`` file under ``root``,
    at any depth, outside its ``tests`` directory and SKIP_DIRS."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS
                             and not (dirpath == root and name == LAUNCH_TESTS))
        for filename in filenames:
            if filename.endswith(LAUNCH_SUFFIXES):
                path = os.path.join(dirpath, filename)
                found.append((os.path.relpath(path, root).replace(os.sep, "/"), path))
    return sorted(found)


def test_only_the_snapshot_reads_statistics_and_every_platform_call_is_allowlisted():
    modules = launch_modules()
    names = [rel for rel, _ in modules]
    assert SNAPSHOT in names and set(GH_ALLOWED) <= set(names) and len(names) >= 5, names
    assert set(GH_ADVICE) <= set(names), names

    # (i) Only the snapshot imports a network module or names a statistics endpoint.
    network, statistics, found, sources = {}, {}, {}, {}
    for name, path in modules:
        sources[name] = read_text(path)
        network[name], statistics[name], calls, fetchers = analyse(name, sources[name])
        assert fetchers == [], (name, fetchers)
        assert unlisted(name, calls) == [], (name, unlisted(name, calls))
        found[name] = calls
    assert [name for name in names if network[name]] == [SNAPSHOT], network
    assert [name for name in names if statistics[name]] == [SNAPSHOT], statistics
    assert statistics[SNAPSHOT], "the snapshot names no statistics endpoint"

    # Every module with a `gh api` entry only reads: no write flag, no write method.
    readers = api_modules()
    assert readers == sorted([SNAPSHOT, "record_demo.py"]), readers
    for name in readers:
        problems, seen = write_requests(sources[name])
        assert problems == [], (name, problems)
        assert seen["gh api argv"] >= 1, (name, seen)
    assert write_requests(sources[SNAPSHOT])[1]["Request"] >= 1

    # (ii) Every gh call is allowlisted (above), and every entry is a call the module holds;
    # every advice string is a string the module holds, exactly.
    for name, entries in sorted(GH_ALLOWED.items()):
        for entry in sorted(entries):
            assert any(call[:len(entry)] == entry for call in found[name]), (name, entry)
    for name, texts in sorted(GH_ADVICE.items()):
        held = {_text(node) for node in ast.walk(ast.parse(sources[name]))}
        for text in texts:
            assert text in held, (name, text)

    # (iii) The same analyses fire on a violation, and stay quiet on what is allowed.
    clean = ('import json, subprocess, urllib.request\n'
             'subprocess.run(["gh", "api", "repos/o/n"])\n'
             'urllib.request.urlopen(urllib.request.Request("https://h.invalid/a", method="GET"))\n')
    assert write_requests(clean) == ([], {"gh api argv": 1, "Request": 1})
    assert network_imports(clean) == {"urllib"} and statistics_hits(clean) == []
    write = ('import subprocess, urllib.request\n'
             'subprocess.run(["gh", "api", "-X", "POST", "repos/o/n/issues", "-f", "title=t"])\n'
             'urllib.request.urlopen(urllib.request.Request("https://h.invalid/a", '
             'data=b"{}", method="POST"))\n')
    problems, _ = write_requests(write)
    for needle in ("gh write flag '-X'", "gh write flag '-f'", "HTTP method 'POST'",
                   "Request with a body", "Request whose method is not GET",
                   "a method other than GET"):
        assert any(needle in problem for problem in problems), (needle, problems)
    assert network_imports("import socket\nfrom http import client\n") == {"socket", "http.client"}
    assert network_imports("import json\nfrom http import HTTPStatus\n") == set()
    assert statistics_hits('URL = "repos/o/n/traffic/clones"') == ["traffic/"]
    assert statistics_hits('N = repo["subscribers_count"]') == ["subscribers_count"]

    # A new gh call planted in a real module is unlisted; the module as it is was not.
    check = read_text(os.path.join(LAUNCH, "quickstart_check.py"))
    planted = check + '\nsubprocess.run(["gh", "repo", "delete", repo, "--yes"])\n'
    assert unlisted("quickstart_check.py", gh_calls(planted)[0]) == [("repo", "delete")]
    login = 'subprocess.run([tools["gh"], "api", "-X", "PATCH", "user"])\n'
    assert unlisted("record_demo.py", gh_calls(login)[0]) == [("api",)]
    assert unlisted("recording_check.py", gh_calls('run([gh_bin, "pr", "view"])')[0]) == \
        [("pr", "view")]
    assert gh_calls("CMD = \"sh -c 'gh release create v1'\"\n")[0] == {("release", "create")}
    assert gh_calls('run(["curl", "-s", url])\n')[1] == ["line 1: curl"]
    assert gh_calls('URL = "wget https://h.invalid/a"\n')[1] == ["line 1: wget"]
    # A docstring, a pattern matched against gh's output, and prose that names gh but no
    # gh command are not calls; the same text run as a command is.
    assert gh_calls('"""Then gh pr merge it."""\nWHY = "gh is not on PATH"\n'
                    'RULE = re.compile(r"gh auth login|denied", re.I)\n') == (set(), [])
    assert gh_calls('subprocess.run("gh auth login", shell=True)\n')[0] == {("auth", "login")}


def test_gh_is_found_in_any_case_and_through_indirection():
    """The gh executable spelled in another case or as a path, held by a variable bound to
    ``which("gh")``, or run through ``env`` or ``command``, is still gh; a lookup of
    another program, ``command -v gh`` and prose are not calls."""
    for source, call in (
            ('run(["GH", "pr", "view"])', ("pr", "view")),
            ('run(["/usr/local/bin/Gh", "pr", "view"])', ("pr", "view")),
            ('run(["C:\\\\tools\\\\gh.exe", "pr", "view"])', ("pr", "view")),
            ('run([GH_BIN, "pr", "view"])', ("pr", "view")),
            ('exe = shutil.which("gh")\nrun([exe, "repo", "delete", repo])', ("repo", "delete")),
            ('found = which("GH")\nrun([found, "repo", "delete"])', ("repo", "delete")),
            ('self.tool = _which("gh", path)\nrun([self.tool, "repo", "delete"])',
             ("repo", "delete")),
            ('tools["exe"] = shutil.which("gh")\nrun([tools["exe"], "repo", "delete"])',
             ("repo", "delete")),
            ('exe: str = shutil.which("gh")\nrun((exe, "repo", "delete"))', ("repo", "delete")),
            ('if (exe := shutil.which("gh")):\n    run([exe, "repo", "delete"])',
             ("repo", "delete")),
            ('run(["env", "GH_TOKEN=t", "gh", "repo", "delete"])', ("repo", "delete")),
            ('run(["/usr/bin/env", "-i", "PATH=/bin", "GH", "repo", "delete"])',
             ("repo", "delete")),
            ('exe = shutil.which("gh")\nrun(["env", exe, "repo", "delete"])', ("repo", "delete")),
            ('run(["command", "gh", "api", "-X", "POST", "repos/o/n/issues"])', ("api",)),
            ('CMD = "env GH_PAGER=cat GH repo delete x"', ("repo", "delete"))):
        assert gh_calls(source)[0] == {call}, source
        assert unlisted("record_demo.py", gh_calls(source)[0]) == [call], source
    for source in ('exe = shutil.which("git")\nrun([exe, "repo", "create"])',
                   'run(["command", "-v", "gh"])',
                   'run(["env", "GIT_DIR=x", "git", "push"])',
                   'run(["ghost", "repo", "create"])',
                   'WHY = "GH is not on PATH"'):
        assert gh_calls(source) == (set(), []), source
    assert gh_bindings(ast.parse('a = shutil.which("gh")\nb = shutil.which("git")\n'
                                 'c.d = _which("GH", p)\n')) == {("name", "a"), ("attr", "d")}


def test_every_module_with_a_gh_api_entry_only_reads():
    """Each module the allowlist lets run ``gh api``, record_demo.py's ``gh api user``
    included, is held to reads: a write flag or a write method planted in it fails."""
    for name in api_modules():
        source = read_text(os.path.join(LAUNCH, name))
        assert write_requests(source)[0] == [], name
        for flag in GH_WRITE_FLAGS:
            planted = source + '\nsubprocess.run([gh, "api", "user", "%s", "x"])\n' % flag
            problems, _ = write_requests(planted)
            assert "line %d: gh write flag %r" % (len(planted.splitlines()), flag) \
                in problems, (name, flag, problems)
        planted = source + '\nsubprocess.run([gh, "api", "--method=PATCH", "user"])\n'
        problems, _ = write_requests(planted)
        assert any("--method=PATCH" in problem for problem in problems), (name, problems)
        assert any("HTTP method 'PATCH'" in problem
                   for problem in write_requests(source + '\nMETHOD = "PATCH"\n')[0]), name
    # record_demo.py's own read, a `-q` filter on `gh api user`, is not a write.
    assert write_requests('run([tools["gh"], "api", "user", "-q", ".login"])\n') == (
        [], {"gh api argv": 1})


def test_advice_text_is_allowed_only_as_the_exact_message():
    """The e2e driver may spell `gh repo create` only in its exact refusal message: a real
    argv that runs it, the message changed, or the message in another module is a call no
    entry allows."""
    name = "quickstart_e2e.py"
    (advice,) = GH_ADVICE[name]
    assert ("repo", "create") not in {entry for entries in GH_ALLOWED.values()
                                      for entry in entries}
    source = read_text(os.path.join(LAUNCH, name))
    assert unlisted(name, analyse(name, source)[2]) == []
    planted = source + '\nsubprocess.run(["gh", "repo", "create", repo, "--private"])\n'
    assert unlisted(name, analyse(name, planted)[2]) == [("repo", "create")]
    message = "WHY = %r\n" % advice
    assert analyse(name, message)[2] == set()
    assert unlisted(name, analyse(name, "WHY = %r\n" % (advice + " now"))[2]) == \
        [("repo", "create")]
    assert unlisted(name, analyse(name, "WHY = %r\n" % advice.replace("gh ", "gh  "))[2]) == \
        [("repo", "create")]
    assert unlisted("quickstart_check.py", analyse("quickstart_check.py", message)[2]) == \
        [("repo", "create")]


def test_the_module_analysis_walks_tools_launch_and_reads_shell_scripts(tmp_path):
    """Every ``.py`` and ``.sh`` file under tools/launch is analysed, at any depth, but not
    its tests; a shell script's gh calls, direct or through a variable, its fetchers and its
    statistics reads are found, and its comments are not calls."""
    root = str(tmp_path / "launch")
    _put(root, "a.py", "X = 1\n")
    _put(root, "sub/b.py", 'run(["gh", "release", "create", "v1"])\n')
    _put(root, "sub/deeper/c.sh", "true\n")
    _put(root, "run.sh", "true\n")
    _put(root, "notes.md", "gh repo delete\n")
    _put(root, "tests/test_a.py", 'run(["gh", "repo", "delete"])\n')
    _put(root, "__pycache__/a.py", "X = 1\n")
    assert [rel for rel, _ in launch_modules(root)] == [
        "a.py", "run.sh", "sub/b.py", "sub/deeper/c.sh"]
    assert unlisted("sub/b.py", analyse("sub/b.py", read_text(
        os.path.join(root, "sub", "b.py")))[2]) == [("release", "create")]

    script = ("#!/bin/sh\n"
              "# gh repo delete is never run here\n"
              "GH=$(command -v gh)\n"
              "gh api repos/o/n/traffic/views\n"
              '"$GH" repo delete "$1" --yes  # gh pr merge in a comment\n'
              "${GH} pr merge 1\n"
              "'gh' release create v1\n"
              "curl -s https://h.invalid/a\n")
    network, statistics, calls, fetchers = analyse("run.sh", script)
    assert network == set() and statistics == ["traffic/"]
    assert unlisted("run.sh", calls) == [("api",), ("pr", "merge"), ("release", "create"),
                                         ("repo", "delete")]
    assert fetchers == ["line 8: curl"]
    quiet = '#!/bin/sh\n# gh repo delete\necho "gh is not on PATH" >&2\n$PAGER repo view\n'
    assert analyse("run.sh", quiet) == (set(), [], set(), [])


# --- BR-8, AC-10: the README ---------------------------------------------------------------

#: A crontab schedule line: five time fields, then a command.
_CRON_RE = re.compile(r"^(?:[0-9*/,-]+\s+){5}\S")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _fenced_lines(text):
    """Every line inside a fenced block of ``text``, stripped."""
    lines, fence = [], None
    for line in text.splitlines():
        match = _FENCE_RE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
            continue
        if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                and not line.strip()[len(match.group(1)):].strip():
            fence = None
            continue
        lines.append(line.strip())
    return lines


def _load_snapshot():
    """``adoption_snapshot.py`` imported by path, under a name no other test uses."""
    spec = importlib.util.spec_from_file_location("_installed_surface_snapshot",
                                                  os.path.join(LAUNCH, SNAPSHOT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section(text, heading):
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end < 0 else text[start:end]


def test_readme_gives_the_weekly_rule_the_reason_and_a_schedule():
    with open(README, encoding="utf-8") as handle:
        text = handle.read()
    weekly = _section(text, "## Run it at least weekly")
    assert "at least weekly" in weekly and "14 days" in weekly
    cron = [line for line in _fenced_lines(weekly) if _CRON_RE.match(line)]
    assert len(cron) == 1, cron
    minute, hour, day, month, weekday = cron[0].split()[:5]
    assert minute.isdigit() and hour.isdigit() and (day, month) == ("*", "*"), cron
    assert re.match(r"^[0-7]$", weekday), cron  # one day of the week: weekly
    assert "cd /path/to/adlc-toolkit && python3 tools/launch/adoption_snapshot.py" in cron[0]
    assert "launchd" in weekly and "StartCalendarInterval" in weekly
    # A fence that is not a schedule is not counted as one.
    assert _fenced_lines("```text\nhello\n```\n0 9 * * 1 outside\n") == ["hello"]
    assert not _CRON_RE.match("python3 tools/launch/adoption_snapshot.py")

    snap = _load_snapshot()
    for cls in snap.CLASSES:
        assert "| `%s` |" % cls in text, cls
    for source, fields in snap.SOURCE_FIELDS:
        assert "| `%s` |" % source in text, source
        for field in fields:
            assert "`%s`" % field in text, field
    assert "`hf_space_runs` has no source" in text and "`no-source`" in text
    for name in (snap.ENV_FILE, snap.ENV_HF_DATASET, snap.ENV_HF_SPACE):
        assert "`%s`" % name in text, name
    assert "`<ADLC_HOME>/%s`" % "/".join(snap.DEFAULT_FILE) in text
    assert "No row is committed to this repo" in text

    for rel, _ in launch_modules():
        assert "| `%s` |" % rel in text, rel
    word = _section(text, "## What needs the maintainer's word")
    for needle in ("quickstart_e2e.py --with-model", "record_demo.py --with-model",
                   "adoption_snapshot.py", "real GitHub and Hugging Face APIs"):
        assert needle in word, needle


# --- The REQ's task files: every verification row names a test that exists ------------------

#: REQ-672's spec directory. An installed copy holds no ``.adlc/specs``, so the check skips.
SPEC_DIR = os.path.join(ROOT, ".adlc", "specs", "REQ-672-newcomer-path-and-launch")
#: A backticked ``path::name`` in a table row.
_ROW_ARTIFACT_RE = re.compile(r"`(?P<path>[^`\s:]+)::(?P<name>[A-Za-z_]\w*)`")


def verification_rows(text):
    """``(line, path, name)`` for each backticked ``path::name`` in the table rows of the
    text's ``## Verification`` section."""
    rows, inside = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            inside = line.strip() == "## Verification"
        elif inside and line.lstrip().startswith("|"):
            rows += [(number, m.group("path"), m.group("name"))
                     for m in _ROW_ARTIFACT_RE.finditer(line)]
    return rows


def missing_tests(root, task, text):
    """One ``<task>:<line>: <path>::<name> ...`` per row whose file is missing under
    ``root`` or holds no ``def <name>(``."""
    problems = []
    for number, rel, name in verification_rows(text):
        path = os.path.join(root, *rel.split("/"))
        source = read_text(path) if os.path.isfile(path) else None
        if source is None:
            problems.append("%s:%d: %s::%s names no file" % (task, number, rel, name))
        elif not re.search(r"^[ \t]*(?:async[ \t]+)?def[ \t]+%s[ \t]*\(" % re.escape(name),
                           source, re.M):
            problems.append("%s:%d: %s::%s names no test in that file" % (task, number, rel, name))
    return problems


def test_every_verification_row_names_a_test_that_exists(tmp_path):
    """Each task file's ``## Verification`` table names its tests as ``path::name``; each
    must be a file that exists and defines that test, so a renamed or folded test cannot
    leave a row pointing at nothing."""
    if not os.path.isdir(SPEC_DIR):
        pytest.skip("%s is absent: an installed copy has no .adlc/specs"
                    % os.path.relpath(SPEC_DIR, ROOT))
    tasks = task_files(SPEC_DIR)
    assert tasks, "no TASK-*.md under %s" % SPEC_DIR
    problems, read = [], 0
    for path in tasks:
        text = read_text(path)
        rows = verification_rows(text)
        assert rows, "%s has no path::name row in its Verification table" % path
        read += len(rows)
        problems += missing_tests(ROOT, os.path.basename(path), text)
    assert problems == [], "\n".join(problems)
    assert read >= len(tasks)

    # A broken copy: a row naming a renamed test, and one naming a missing file, are each
    # reported on their own line; a row naming a real test, and prose outside the table
    # or under another heading, are not read as rows.
    _put(str(tmp_path), "tests/test_x.py", "def test_real():\n    pass\n# def test_gone():\n")
    task = ("## Acceptance Criteria\n\n| AC-1 | test-case | `tests/test_x.py::test_other` | no |\n\n"
            "## Verification\n\n| rule | kind | artifact | benign_path |\n|---|---|---|---|\n"
            "| BR-1 | test-case | `tests/test_x.py::test_real` | no |\n"
            "| BR-2 | test-case | `tests/test_x.py::test_gone` | no |\n"
            "| AC-2 | test-case | `tests/test_y.py::test_real` | yes |\n\n"
            "Prose naming `tests/test_x.py::test_prose` is not a row.\n\n## Technical Notes\n\n"
            "| x | `tests/test_x.py::test_notes` |\n")
    assert [row[2] for row in verification_rows(task)] == ["test_real", "test_gone", "test_real"]
    assert missing_tests(str(tmp_path), "TASK-1.md", task) == [
        "TASK-1.md:10: tests/test_x.py::test_gone names no test in that file",
        "TASK-1.md:11: tests/test_y.py::test_real names no file"]


def task_files(spec_dir):
    """The ``TASK-*.md`` files of ``spec_dir``'s ``tasks`` directory, sorted, or none."""
    folder = os.path.join(spec_dir, "tasks")
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, name) for name in os.listdir(folder)
                  if name.startswith("TASK-") and name.endswith(".md"))
