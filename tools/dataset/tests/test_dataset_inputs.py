"""The export's input recognizers: DenyList, classifier, frontmatter (REQ-671 TASK-151)."""
import json
import os
import subprocess

import pytest

import classify
import denylist
import frontmatter
from dataset_helpers import DATASET_DIR, TOOLKIT, needs_toolkit_git

DENYLIST_PATH = os.path.join(DATASET_DIR, "denylist.json")


def _tree_paths():
    out = subprocess.run(["git", "-C", TOOLKIT, "ls-tree", "-r", "-z", "--name-only",
                          "--full-tree", "HEAD", "--", ".adlc"],
                         capture_output=True, check=True).stdout
    return [p.decode("utf-8") for p in out.split(b"\0") if p]


def _show(path):
    return subprocess.run(["git", "-C", TOOLKIT, "show", "HEAD:" + path],
                          capture_output=True, check=True).stdout.decode("utf-8")


# --- classifier ----------------------------------------------------------------

@pytest.mark.parametrize("path, expected", [
    (".adlc/specs/REQ-012-x/requirement.md", ("requirement", "REQ-012", "")),
    (".adlc/specs/REQ-012-x/architecture.md", ("architecture", "REQ-012/architecture", "REQ-012")),
    (".adlc/specs/REQ-012-x/tasks/TASK-003-y.md", ("task", "REQ-012/TASK-003", "REQ-012")),
    (".adlc/knowledge/lessons/LESSON-716-z.md", ("lesson", "LESSON-716", "")),
    (".adlc/bugs/BUG-205-a.md", ("bug", "BUG-205", "")),
    (".adlc/knowledge/assumptions/ASSUME-003-b.md", ("assumption", "ASSUME-003", "")),
])
def test_kinds_map(path, expected):
    assert tuple(classify.classify(path)) == expected


@pytest.mark.parametrize("path", [
    ".adlc/context/architecture.md",
    ".adlc/context/conventions.md",
    ".adlc/research/notes.md",
    ".adlc/specs/REQ-1-x/verification.md",
    ".adlc/specs/REQ-1-x/adversary-report.md",
    ".adlc/specs/REQ-1-x/oq1-spike-result.md",
    ".adlc/specs/REQ-1-x/pipeline-state.json",
    ".adlc/.next-assume",
    ".adlc/config.yml",
])
def test_exclusions_carry_a_reason(path):
    result = classify.classify(path)
    assert isinstance(result, classify.Excluded) and result.reason


def test_context_architecture_is_never_an_architecture_record():
    assert isinstance(classify.classify(".adlc/context/architecture.md"), classify.Excluded)


@pytest.mark.parametrize("path", [
    ".adlc/notes.md",
    ".adlc/specs/REQ-1-x/draft.md",
    ".adlc/specs/REQ-1-x/tasks/notes.md",
    ".adlc/knowledge/lessons/README.md",
    ".adlc/bugs/bug-205.md",
    ".adlc/specs/REQ-1-x/requirement.md.bak",
])
def test_unknown_path_is_unmapped(path):
    assert classify.classify(path) is None


@needs_toolkit_git
def test_current_tree_fully_classified():
    paths = _tree_paths()
    assert len(paths) > 400, "non-vacuity: the tree under test is the real corpus"
    unmapped = [p for p in paths if classify.classify(p) is None]
    assert unmapped == []
    kinds = {r.kind for r in map(classify.classify, paths) if isinstance(r, classify.Artifact)}
    assert kinds == set(classify.KIND_ORDER)


# --- frontmatter ---------------------------------------------------------------

def _parse(text):
    sp, finding = frontmatter.split(text)
    assert finding is None
    return frontmatter.parse(sp)


def test_frontmatter_reads_the_corpus_shapes():
    fields, findings = _parse(
        "<!--\nnote\n-->\n---\nid: LESSON-1\ntitle: \"A \\\"quoted\\\" title\"\n"
        "tags: [a, \"b c\", 'd']\nempty:\nlane: full  # a comment\n# a comment line\n"
        "stack: []\n---\nbody\n")
    assert findings == []
    assert fields == {"id": "LESSON-1", "title": 'A "quoted" title', "tags": ["a", "b c", "d"],
                      "empty": "", "lane": "full", "stack": []}


@pytest.mark.parametrize("line", [
    'title: "never closed',
    "tags: [a, b",
    "tags: [a, [b]]",
    "just some words",
    "  - item",
    "key:value",
    "map: {a: 1}",
    'title: "closed" trailing',
])
def test_frontmatter_rejects_unparseable_lines(line):
    fields, findings = _parse("---\nid: X-1\n%s\n---\n" % line)
    assert len(findings) == 1
    assert findings[0].line == 3


def test_frontmatter_rejects_repeated_key():
    _, findings = _parse("---\nid: X-1\nid: X-2\n---\n")
    assert [f.reason for f in findings] == ["repeated key 'id'"]


def test_frontmatter_unterminated_is_a_finding():
    sp, finding = frontmatter.split("---\nid: X-1\nbody without a close\n")
    assert sp is None and finding is not None and finding.line == 1


def test_no_frontmatter_is_none_without_finding():
    assert frontmatter.split("# A heading\n\ntext\n") == (None, None)


@needs_toolkit_git
def test_current_corpus_frontmatter_parses_clean():
    checked = 0
    for path in _tree_paths():
        result = classify.classify(path)
        if not isinstance(result, classify.Artifact):
            continue
        sp, finding = frontmatter.split(_show(path))
        assert finding is None, path
        if sp is None:
            assert result.kind == "architecture", "%s has no frontmatter" % path
            continue
        _, findings = frontmatter.parse(sp)
        assert findings == [], (path, findings)
        checked += 1
    assert checked > 400, "non-vacuity"


# --- DenyList ------------------------------------------------------------------

def test_committed_denylist_loads():
    dl = denylist.load(DENYLIST_PATH)
    assert dl.organization and dl.public_repos and dl.repos and dl.people
    assert {r.match for r in dl.repos} == set(denylist.MATCH_MODES)


def _valid():
    with open(DENYLIST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _mutations():
    """``(mutation, the message its check raises)``: each mutation trips one named check."""
    def unknown_top(d):
        d["extra"] = 1

    def unknown_repo_key(d):
        d["repos"][0]["note"] = "x"

    def missing_key(d):
        del d["repos"][0]["match"]

    def bad_match(d):
        d["repos"][0]["match"] = "word"

    def empty_name(d):
        d["repos"][0]["name"] = ""

    def spaced_name(d):
        d["repos"][0]["name"] = "admin api"

    def dup_name(d):
        d["repos"][1]["name"] = d["repos"][0]["name"].upper()

    def dup_placeholder(d):
        d["repos"][1]["placeholder"] = d["repos"][0]["placeholder"]

    def placeholder_leaks(d):
        d["repos"][0]["placeholder"] = d["repos"][1]["name"] + "-x"

    def wrong_type(d):
        d["public_repos"] = "adlc-toolkit"

    def bad_email(d):
        d["email_allowlist"] = ["not-an-address"]

    def empty_public(d):
        d["public_repos"] = []

    def padded_placeholder(d):
        d["repos"][0]["placeholder"] = " consumer-repo-1"

    def alias_is_another_repo(d):
        d["repos"][0]["aliases"] = [d["repos"][1]["name"]]

    def alias_bad_chars(d):
        d["repos"][0]["aliases"] = ["Admin/API"]

    def org_repo_extra_key(d):
        d["organization_repo"] = {"placeholder": "consumer-repo-99", "note": "x"}

    def org_repo_shares_placeholder(d):
        d["organization_repo"] = {"placeholder": d["repos"][0]["placeholder"]}

    return [
        (unknown_top, r"the DenyList has unknown key\(s\) extra"),
        (unknown_repo_key, r"repos\[0\] has unknown key\(s\) note"),
        (missing_key, r"repos\[0\] is missing key\(s\) match"),
        (bad_match, r"repos\[0\]\.match must be one of"),
        (empty_name, r"repos\[0\]\.name must be a non-empty string"),
        (spaced_name, r"repos\[0\]\.name 'admin api' is not a plain name"),
        (dup_name, r"listed more than once"),
        (dup_placeholder, r"two repos share a placeholder"),
        (placeholder_leaks, r"placeholder .* contains the name"),
        (wrong_type, r"public_repos must be a list"),
        (bad_email, r"is not an address"),
        (empty_public, r"public_repos must name at least one"),
        (padded_placeholder, r"repos\[0\]\.placeholder has surrounding whitespace"),
        (alias_is_another_repo, r"listed more than once"),
        (alias_bad_chars, r"repos\[0\]\.aliases\[0\] 'Admin/API' is not a plain name"),
        (org_repo_extra_key, r"organization_repo has unknown key\(s\) note"),
        (org_repo_shares_placeholder, r"two repos share a placeholder"),
    ]


@pytest.mark.parametrize("mutate, message", _mutations(), ids=lambda v: getattr(v, "__name__", ""))
def test_denylist_recognizer_refuses_malformed(mutate, message):
    data = _valid()
    denylist.parse(json.dumps(data))  # benign: the unmutated file passes
    mutate(data)
    with pytest.raises(denylist.DenyListError, match=message):
        denylist.parse(json.dumps(data))


def test_denylist_accepts_null_organization_repo_and_a_phrase_alias():
    data = _valid()
    data["organization_repo"] = None
    data["repos"][0]["aliases"] = ["Admin Panel"]
    dl = denylist.parse(json.dumps(data))
    assert dl.organization_repo is None and dl.repos[0].aliases == ("Admin Panel",)


def test_denylist_refuses_repeated_json_key():
    text = json.dumps(_valid())
    text = text.replace('"organization":', '"organization": "x", "organization":', 1)
    with pytest.raises(denylist.DenyListError, match="repeated key"):
        denylist.parse(text)


def test_denylist_refuses_invalid_json():
    with pytest.raises(denylist.DenyListError):
        denylist.parse("{not json")
