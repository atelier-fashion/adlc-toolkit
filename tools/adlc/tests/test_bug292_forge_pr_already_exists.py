"""BUG-292: a forge's refusal of a second open PR for one head and base has an error class of
its own, `pr-already-exists`.

Before it, `_adlc_forge_classify` gave both forges' words the fall-through class, `network`,
the one that reads as transient and invites a retry (LESSON-581). The refusal is neither: the
PR it names is the caller's own, and the create is refused every time.

Every case is offline: the classifier is run on strings, the mock forge on a throwaway store.
`gh`'s sentence is the format string the gh 2.103.3 binary holds. GitHub's server-side sentence
is as third-party code that catches it quotes it. Azure DevOps's TF401179 is matched by its
code; the prose after it is unconfirmed. None was read off a live forge, and no duplicate PR
was opened to find out.
"""

import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import fence_run as fr  # noqa: E402
import forge_mock  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
CLASS = "pr-already-exists"
FORGE_SH = os.path.join(TOOLKIT, "partials", "forge.sh")
FORGE_MD = os.path.join(TOOLKIT, "partials", "forge.md")
#: `gh pr create`'s own pre-check: two lines, the second the PR's URL.
GH_SAID = ('a pull request for branch "feat/x" into branch "main" already exists:\n'
           "https://github.com/acme/widgets/pull/101")
#: GitHub's refusal of the create itself, as gh frames a GraphQL error.
GITHUB_SAID = ("pull request create failed: GraphQL: A pull request already exists for "
               "acme:feat/x. (createPullRequest)")
ADO_SAID = "TF401179: An active pull request for the source and target branch already exists."
MAKE = ["pr_create", "--draft", "--base", "main", "--head", "feat/x", "--title", "t", "--body",
        "b"]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _classify(raw):
    """The class `partials/forge.sh` gives a backend's stderr."""
    script = '. "$1/partials/forge.sh"; _adlc_forge_classify "$2"'
    return subprocess.run(["sh", "-c", script, "sh", TOOLKIT, raw], stdout=subprocess.PIPE,
                          universal_newlines=True, check=True).stdout.strip()


def _env(tmp_path, **extra):
    """A throwaway HOME, and no scenario or store inherited from the caller's shell."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "ADLC_TOOLKIT_ROOT": TOOLKIT,
           "ADLC_FORGE_MOCK": "1"}
    env.update(extra)
    return env


def _mock(tmp_path, store, *args, **extra):
    env = _env(tmp_path, ADLC_FORGE_MOCK_STORE=str(store), **extra)
    return subprocess.run([sys.executable, os.path.join(TOOLKIT, "tools", "adlc", "forge_mock.py")]
                          + list(args), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)


def _adapter(tmp_path, call, **extra):
    """One adapter call as a fence makes it: `forge.sh` sourced, then the op, in one `sh`."""
    script = '. "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; %s' % call
    return subprocess.run(["sh", "-c", script], env=_env(tmp_path, **extra),
                          cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)


def _store(tmp_path, name="store"):
    store = tmp_path / name
    store.mkdir()
    (store / "config.json").write_text(json.dumps({"remote": "", "owner": "acme",
                                                   "name": "widgets"}))
    return store


def _enumeration(text):
    """The classes an `error_class=<a|b|…>` enumeration names, comment marks and line breaks
    aside."""
    found = re.search(r"error_class=<([^>]*)>", text)
    assert found, "no error_class=<…> enumeration"
    return set(re.sub(r"[#\s]", "", found.group(1)).split("|"))


def test_bug292_every_statement_of_the_class_set_is_the_same_set():
    """The set is written down in five places, and LESSON-581's second half is that they drift:
    what the classifier can print, the enumeration in `forge.sh`'s header, the one in
    `forge.md`, the scenario names the shell fixture honours, and the mock's `ERROR_CLASSES`.
    All five are one set, and the new class is in it."""
    sh = _read(FORGE_SH)
    body = sh[sh.index("\n_adlc_forge_classify() {"):]
    emitted = set(re.findall(r'echo "([a-z-]+)"', body[:body.index("\n}\n")]))
    (arm,) = re.findall(r'^ +((?:[a-z-]+\|)+[a-z-]+)\)\n +_adlc_forge_err "\$adlc_mk_scn"', sh,
                        re.M)
    stated = {"forge.sh's header": _enumeration(sh), "forge.md": _enumeration(_read(FORGE_MD)),
              "the shell fixture's scenarios": set(arm.split("|")),
              "forge_mock.ERROR_CLASSES": set(forge_mock.ERROR_CLASSES)}
    assert CLASS in emitted, sorted(emitted)
    for where, classes in stated.items():
        assert classes == emitted, (where, sorted(classes ^ emitted))
    assert len(forge_mock.ERROR_CLASSES) == len(set(forge_mock.ERROR_CLASSES))


@pytest.mark.parametrize("said", [
    GH_SAID,
    GITHUB_SAID,
    ADO_SAID,
    "ERROR: " + ADO_SAID,
    # The refusal quotes the project's own names, so its arm is tried before every other.
    GH_SAID.replace("feat/x", "feat/REQ-12-branch-protection-policy"),
    GH_SAID.replace("feat/x", "fix/credentials-not-found"),
    GH_SAID.replace("acme/widgets", "acme/policy-engine"),
    GITHUB_SAID.replace("feat/x", "fix/authentication-unsupported"),
])
def test_bug292_each_forges_refusal_has_the_class(said):
    assert _classify(said) == CLASS, said


@pytest.mark.parametrize("said, klass", [
    ("fatal: a branch named 'feat/x' already exists", "local-git"),
    ('no pull requests found for branch "feat/x"', "pr-not-found"),
    ("ERROR: TF401174: The pull request does not exist", "pr-not-found"),
    ("error connecting to api.github.com: dial tcp: i/o timeout", "network"),
])
def test_bug292_the_class_takes_nothing_from_another(said, klass):
    """Other things that already exist, and a PR that does not, keep their classes."""
    assert _classify(said) == klass, said


def test_bug292_the_mock_refuses_under_the_class_the_adapter_gives_its_words(tmp_path):
    """BUG-291's rule for the mock holds: its refusal carries the class `_adlc_forge_classify`
    gives the forge's own words. That class is now `pr-already-exists`, under both providers,
    from `forge_mock.py` itself and through `adlc_forge_pr_create`. No second PR is opened."""
    for provider, raw in (("github", ['a pull request for branch "feat/x" into branch "main" '
                                      "already exists:",
                                      "https://mock.forge/acme/widgets/pull/101"]),
                          ("azure-devops", [ADO_SAID])):
        store = _store(tmp_path, provider)
        assert _mock(tmp_path, store, *MAKE, ADLC_FORGE_MOCK_PROVIDER=provider).returncode == 0
        block = ["error_class=%s" % CLASS] + ["raw=%s" % line for line in raw]
        again = _mock(tmp_path, store, *MAKE, ADLC_FORGE_MOCK_PROVIDER=provider)
        assert again.returncode == 1 and again.stdout.splitlines() == block, again
        assert _classify("\n".join(raw)) == CLASS
        through = _adapter(
            tmp_path, "adlc_forge_pr_create --draft --base main --head feat/x --title t --body b",
            ADLC_FORGE_MOCK_STORE=str(store), ADLC_FORGE_MOCK_PROVIDER=provider)
        assert through.returncode == 1 and through.stdout.splitlines() == block, through
        assert len(json.loads((store / "prs.json").read_text())["prs"]) == 1


def test_bug292_the_class_is_a_mock_scenario(tmp_path):
    """Every class the classifier prints is a scenario (forge.md, "Mock backend"). An unknown
    scenario name comes back as `network`, the mislabel BUG-201 found for `local-git`."""
    store = _store(tmp_path)
    for provider in ("github", "azure-devops"):
        out = _mock(tmp_path, store, "pr_view", "101", "--fields", "state",
                    ADLC_FORGE_MOCK_PROVIDER=provider, ADLC_FORGE_MOCK_SCENARIO=CLASS)
        assert out.returncode == 1 and out.stdout.splitlines()[0] == "error_class=%s" % CLASS
        # With no store the shell fixture answers, from its own list of scenario names.
        out = _adapter(tmp_path, "adlc_forge_pr_create --base main --head feat/x --title t "
                                 "--body b",
                       ADLC_FORGE_MOCK_PROVIDER=provider, ADLC_FORGE_MOCK_SCENARIO=CLASS)
        assert out.returncode == 1, out
        assert out.stdout.splitlines() == [
            "error_class=%s" % CLASS,
            "raw=mock backend (%s): simulated %s for pr_create" % (provider, CLASS)], out


def test_bug292_the_runners_pr_read_takes_the_class_for_no_other():
    """`fence_run.pr_verdict` is the one program that reads a class by name. It reads a
    `pr_view`, which no forge answers with this class, and if one did the read would be
    unverified (75), as for every class but `pr-not-found`: never a bad value (65) to correct.
    This held before the class existed; it pins that the new name is one the runner's pattern
    for a class admits, so the line it prints names the class."""
    for klass in forge_mock.ERROR_CLASSES:
        assert fr._ERROR_CLASS_RE.match(klass), klass
    verdict = fr.pr_verdict("101", "feat/x", (1, "error_class=%s\nraw=x\n" % CLASS, ""))
    assert verdict == (fr.UNVERIFIED, "error_class=%s" % CLASS)


def test_bug292_the_text_a_session_reads_names_the_class():
    """The sentence beside Step 0's draft-PR fence says what the refusal prints, so a session
    that reads `error_class=pr-already-exists` has been told it is the REQ's own PR and not a
    failed setup. A project's vendored `forge.sh` can be older than the class, so the sentence
    names what that one prints too. The contract and the operator reference name the class."""
    setup = " ".join(_read(os.path.join(TOOLKIT, "proceed", "phase-0-setup.md")).split())
    item = setup[setup.index("8a. **Open a draft PR early"):]
    item = item[:item.index("In subagent mode")]
    assert "`error_class=%s`" % CLASS in item
    assert "`error_class=network` from a vendored `forge.sh` older than that class" in item
    assert "not a failed setup" in item and "never open one under another title" in item
    contract = " ".join(_read(FORGE_MD).split())
    assert "**`%s` is the caller's own PR" % CLASS in contract
    readme = " ".join(_read(os.path.join(TOOLKIT, "tools", "adlc", "README.md")).split())
    assert "as `error_class=%s` with the forge's own words" % CLASS in readme
    assert "as `error_class=network` with the forge's own words" not in readme
