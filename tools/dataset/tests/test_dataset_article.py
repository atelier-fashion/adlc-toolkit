"""The companion article and its number script (REQ-671 TASK-155, BR-11).

The sandbox cases build a small dataset with ``export.main`` in a throwaway git
repository, then compute and render against it. The published-revision case
runs at publish time only, against a clone named by ``ADLC_DATASET_PUBLISHED_DIR``.
"""
import builtins
import json
import os
import re
import subprocess

import pytest

import article_numbers
import denylist
import export
from dataset_helpers import TOOLKIT, DATASET_DIR

DRAFT = os.path.join(DATASET_DIR, "article", "draft.md")
TOKEN_RE = re.compile(r"\{\{([^{}]*)\}\}")

DATASET_URL = "https://huggingface.co/datasets/example-org/adlc-artifacts"
SPACE_URL = "https://huggingface.co/spaces/example-org/spec-intake"
PLUGIN_URL = "https://github.com/atelier-fashion/adlc-toolkit#install"

FIXTURE_DENYLIST = {
    "organization": "acme-org",
    "organization_repo": None,
    "public_repos": ["open-tool"],
    "repos": [{"name": "secret-api", "placeholder": "consumer-repo-1", "match": "token", "aliases": []}],
    "people": [{"name": "Dana", "placeholder": "the maintainer"}],
    "email_allowlist": ["noreply@anthropic.com"],
}


def _req(num, created, tags, body):
    return ("---\nid: REQ-%s\ntitle: \"Requirement %s\"\nstatus: complete\ncreated: %s\n"
            "updated: %s\ntags: [%s]\n---\n\n%s\n" % (num, num, created, created,
                                                    ", ".join(tags), body))


def _task(num, parent, body):
    return ("---\nid: TASK-%s\ntitle: \"A task\"\nstatus: complete\nparent: %s\n"
            "created: 2026-02-01\n---\n\n%s\n" % (num, parent, body))


def _lesson(num, created, body):
    return ("---\nid: LESSON-%s\ntitle: \"A lesson\"\ntags: [x, y]\ncreated: %s\n---\n\n"
            "%s\n" % (num, created, body))


def _tree(sandbox):
    """A minimal tree with links, tags and a few scrub hits."""
    files = {
        "VERSION": "2.7.1\n",
        ".adlc/specs/REQ-001-first/requirement.md": _req(
            "001", "2026-01-05", ["a", "b"], "Builds on LESSON-002. See TASK-001 and REQ-999."),
        ".adlc/specs/REQ-001-first/architecture.md": "# Design\n\nTASK-001 and TASK-002.\n",
        ".adlc/specs/REQ-001-first/tasks/TASK-001-a.md": _task("001", "REQ-001", "For REQ-001."),
        ".adlc/specs/REQ-001-first/tasks/TASK-002-b.md": _task("002", "REQ-001", "Then TASK-001."),
        ".adlc/specs/REQ-003-second/requirement.md": _req(
            "003", "2026-03-09", ["b", "c"], "Cites LESSON-002 and LESSON-004."),
        ".adlc/specs/REQ-003-second/tasks/TASK-001-c.md": _task("001", "REQ-003", "For REQ-003."),
        ".adlc/knowledge/lessons/LESSON-002-a.md": _lesson(
            "002", "2026-01-20", "From REQ-001 and BUG-005."),
        ".adlc/knowledge/lessons/LESSON-004-b.md": _lesson(
            "004", "2026-03-30", "From REQ-003. Key AKIAABCDEFGHIJKLMNOP at "
            "/Users/someone/GitHub/open-tool/x.py in secret-api, by Dana."),
        ".adlc/bugs/BUG-005-a.md": "---\nid: BUG-005\ntitle: \"A bug\"\nstatus: resolved\n---\n\n"
                                   "Broke REQ-001.\n",
        ".adlc/knowledge/assumptions/ASSUME-001-a.md": "---\nid: ASSUME-001\ntitle: \"Holds\"\n"
                                                      "---\n\nHolds.\n",
        ".adlc/context/architecture.md": "# context\n",
        denylist.REPO_PATH: json.dumps(FIXTURE_DENYLIST),
    }
    for rel, content in files.items():
        sandbox.write(rel, content)
    return sandbox.commit()


@pytest.fixture
def dataset(sandbox, tmp_path):
    """Export the sandbox tree; return the ``dataset/`` directory."""
    _tree(sandbox)
    out = tmp_path / "out"
    assert export.main(["--commit", "main", "--out", str(out), "--repo", sandbox.root]) \
        == export.EXIT_OK
    return str(out / "dataset")


def _draft():
    with open(DRAFT, encoding="utf-8") as fh:
        return fh.read()


def _main(capsys, *argv):
    rc = article_numbers.main(list(argv))
    out, err = capsys.readouterr()
    return rc, out, err


def _urls(**kwargs):
    return article_numbers.url_values(kwargs.get("dataset"), kwargs.get("space"),
                                      kwargs.get("plugin"))


def _assert_reproduces(rendered, values, enabled, url_tokens):
    """Read every token's value back out of ``rendered`` and compare it.

    The draft is rendered once more with a sentinel per token, which gives the
    exact text around each token. That text, regex-escaped, with a capture group
    where each sentinel was, must match the rendered article in full, and each
    group must be the computed value.
    """
    sentinel = lambda names: dict((n, "\x00%s\x00" % n) for n in names)  # noqa: E731
    skeleton = article_numbers.render(_draft(), sentinel(values), enabled,
                                      sentinel(url_tokens))
    parts = re.split(r"\x00([a-z_]+)\x00", skeleton)
    pattern = "".join(re.escape(p) if i % 2 == 0 else r"(\S+?)" for i, p in enumerate(parts))
    match = re.fullmatch(pattern, rendered, re.S)
    assert match, "the rendered article does not follow the draft"
    expected = dict(values)
    expected.update(url_tokens)
    names = parts[1::2]
    for name, got in zip(names, match.groups()):
        assert got == str(expected[name]), name
    return names


def _numerals(text):
    """Numerals left after removing what may carry one (BR-11)."""
    text = re.sub(r"^```.*?^```[ \t]*$", "", text, flags=re.S | re.M)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = TOKEN_RE.sub("", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r"\]\([^)\s]*\)", "]", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"(?<![A-Za-z0-9])(?:REQ|TASK|LESSON|BUG|ASSUME)-[0-9]+(?![0-9])", "", text)
    return re.findall(r"\S*[0-9]\S*", text)


# --- the draft -------------------------------------------------------------------------

def test_draft_has_no_literal_numbers():
    draft = _draft()
    assert draft.startswith("# ") and not draft.startswith("## ")
    assert len(set(TOKEN_RE.findall(draft))) >= 15, "non-vacuity: the draft uses tokens"
    assert _numerals(draft) == []
    # The stripper is not vacuous: a numeral in prose survives it, and each
    # allowed carrier is stripped.
    assert _numerals("It has 465 records.") == ["465"]
    assert _numerals("Version 5.4.0 shipped") == ["5.4.0"]
    assert _numerals("{{total_records}} `v2` REQ-669 [x](https://h/1) https://h/2\n"
                     "```\nx = 3\n```\n<!-- if:space -->") == []


def test_draft_names_no_private_repo_or_person():
    text = _draft().lower()
    # Spelled in two halves so the brand scan over tools/ does not match this line.
    assert "ki" + "mi" not in text
    dl = denylist.load(os.path.join(TOOLKIT, denylist.REPO_PATH))
    names = [n for r in dl.repos if r.match == "token" for n in (r.name,) + r.aliases] + [
        p.name for p in dl.people]
    for name in names:
        assert not re.search(r"(?<![a-z0-9_])%s(?![a-z0-9_])" % re.escape(name.lower()),
                             text), name
    orgs = set(n.rstrip(".") for n in re.findall(
        r"%s/([a-z0-9_.-]+)" % re.escape(dl.organization.lower()), text))
    assert orgs <= set(r.lower() for r in dl.public_repos)


# --- rendering against a local export ------------------------------------------------

def test_render_reproduces_numbers(dataset, capsys):
    values = article_numbers.compute(dataset)
    draft_tokens = set(TOKEN_RE.findall(_draft()))
    # Every number the draft uses is computed, and every computed number is used.
    assert draft_tokens - set(article_numbers.URL_TOKENS) == set(values)

    assert values["total_records"] == 10
    assert (values["count_requirement"], values["count_task"], values["count_lesson"]) == (2, 3, 2)
    assert values["tasks_per_req_mean"] == "1.5"
    assert (values["first_created"], values["last_created"]) == ("2026-01-05", "2026-03-30")
    assert values["toolkit_version"] == "2.7.1"
    assert values["reqs_citing_lesson"] == 2 and values["lessons_citing_bug"] == 1
    # Frontmatter citations (a lesson's ``req:``) count as well as body ones.
    assert (values["most_cited_id"], values["most_cited_count"]) == ("REQ-001", 4)
    assert values["refs_dangling"] == 1
    assert values["scrub_credential"] >= 1 and values["scrub_person"] >= 1
    assert values["scrub_total"] == sum(v for k, v in values.items()
                                        if k.startswith("scrub_") and k != "scrub_total")

    for argv, enabled, urls in (
            ((), {"dataset": False, "space": False, "plugin": False}, {}),
            (("--dataset-url", DATASET_URL, "--space-url", SPACE_URL, "--plugin-url", PLUGIN_URL),
             {"dataset": True, "space": True, "plugin": True},
             {"dataset_url": DATASET_URL, "dataset_id": "example-org/adlc-artifacts",
              "space_url": SPACE_URL, "plugin_url": PLUGIN_URL})):
        rc, rendered, err = _main(capsys, dataset, "--render", DRAFT, *argv)
        assert rc == article_numbers.EXIT_OK, err
        assert "{{" not in rendered and "}}" not in rendered and "<!--" not in rendered
        for name, value in values.items():
            assert str(value) in rendered, name
        names = _assert_reproduces(rendered, values, enabled, urls)
        assert set(names) == set(values) | set(urls)

    # Re-running the script against the same directory gives the same numbers.
    assert article_numbers.compute(dataset) == values
    rc, printed, _ = _main(capsys, dataset)
    assert rc == article_numbers.EXIT_OK
    assert printed == "".join("%s=%s\n" % (k, values[k]) for k in sorted(values))


def test_links_only_when_live(dataset, capsys):
    def render(*argv):
        rc, out, err = _main(capsys, dataset, "--render", DRAFT, *argv)
        assert rc == article_numbers.EXIT_OK, err
        return out

    space_text, plugin_text, load_text = ("spec intake demo", "claude plugin install",
                                          "load_dataset(")
    bare = render()
    for text in (SPACE_URL, PLUGIN_URL, DATASET_URL, space_text, plugin_text, load_text):
        assert text not in bare, text
    assert "https://github.com/atelier-fashion/adlc-toolkit" in bare  # benign: always there
    assert "\n\n\n" not in bare

    space = render("--space-url", SPACE_URL)
    assert SPACE_URL in space and space_text in space
    assert plugin_text not in space and PLUGIN_URL not in space

    plugin = render("--plugin-url", PLUGIN_URL)
    assert PLUGIN_URL in plugin and plugin_text in plugin
    assert space_text not in plugin and SPACE_URL not in plugin

    data = render("--dataset-url", DATASET_URL)
    assert DATASET_URL in data and 'load_dataset("example-org/adlc-artifacts"' in data
    assert space_text not in data and plugin_text not in data


def test_unknown_token_exits_2(dataset, tmp_path, capsys):
    draft = _draft()
    cases = {
        "unknown": (draft + "\nAnd {{no_such_number}} more.\n", "{{no_such_number}}"),
        "spaced": (draft + "\n{{ total_records }}\n", "{{ total_records }}"),
        "url outside its block": (draft + "\nSee {{space_url}}.\n", "{{space_url}}"),
        "unknown condition": (draft + "\n<!-- if:nope -->x\n<!-- endif -->\n", "if:nope"),
        "unclosed block": (draft + "\n<!-- if:space -->\nx\n", "unclosed"),
        "unterminated": (draft + "\n{{total_records\n", "unterminated"),
    }
    for label, (text, needle) in cases.items():
        path = tmp_path / ("draft-%s.md" % label.replace(" ", "-"))
        path.write_text(text, encoding="utf-8")
        rc, out, err = _main(capsys, dataset, "--render", str(path))
        assert rc == article_numbers.EXIT_ERROR, label
        assert needle in err, (label, err)
        assert out == "", label
    # An unknown token inside a block that is dropped still fails the render.
    path = tmp_path / "draft-dropped.md"
    path.write_text(draft + "\n<!-- if:space -->\n{{typo_url}}\n<!-- endif -->\n",
                    encoding="utf-8")
    rc, _, err = _main(capsys, dataset, "--render", str(path))
    assert rc == article_numbers.EXIT_ERROR and "{{typo_url}}" in err


def test_usage_errors_exit_2(dataset, capsys):
    for argv in ((dataset, "--space-url", SPACE_URL),
                 (dataset, "--render", DRAFT, "--dataset-url", "https://example.com/x"),
                 (dataset, "--render", DRAFT, "--space-url", "http://insecure.example/x"),
                 (dataset, "--render", os.path.join(dataset, "no-such-draft.md")),
                 (os.path.join(dataset, "nope"),),
                 ()):
        rc, out, _ = _main(capsys, *argv)
        assert rc == article_numbers.EXIT_ERROR, argv
        assert out == ""


# --- what the script reads ----------------------------------------------------------

def test_reads_only_train_and_revision(dataset, tmp_path, monkeypatch, capsys):
    baseline = article_numbers.compute(dataset)
    # Junk next to the two files changes nothing.
    with open(os.path.join(dataset, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("{{not json at all\n")
    with open(os.path.join(dataset, "junk.bin"), "wb") as fh:
        fh.write(b"\xff\xfe\x00")
    os.makedirs(os.path.join(dataset, ".git"))

    opened = []
    real_open = builtins.open

    def spy_open(file, *args, **kwargs):
        opened.append(os.path.realpath(file))
        return real_open(file, *args, **kwargs)

    def no_process(*args, **kwargs):
        raise AssertionError("compute started a process: %r" % (args,))

    with monkeypatch.context() as m:
        m.setattr(builtins, "open", spy_open)
        m.setattr(subprocess, "Popen", no_process)
        assert article_numbers.compute(dataset) == baseline
    assert sorted(set(opened)) == sorted(os.path.realpath(os.path.join(dataset, p))
                                         for p in ("revision.json", "data/train.jsonl"))
    with open(article_numbers.__file__, encoding="utf-8") as fh:
        source = fh.read()
    # Spelled in two halves so the hub-client scan does not match this test file.
    assert "huggingface" + "_hub" not in source and "subprocess" not in source

    for missing in ("revision.json", os.path.join("data", "train.jsonl")):
        copy = tmp_path / ("copy-" + os.path.basename(missing))
        os.makedirs(str(copy / "data"))
        for rel in ("revision.json", os.path.join("data", "train.jsonl")):
            if rel != missing:
                with open(os.path.join(dataset, rel), "rb") as src, \
                        open(str(copy / rel), "wb") as dst:
                    dst.write(src.read())
        rc, out, err = _main(capsys, str(copy))
        assert rc == article_numbers.EXIT_ERROR, missing
        assert "missing" in err and out == ""


def _rewrite(path, edit):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(edit(text))


def test_malformed_dataset_exits_2(dataset, capsys):
    train = os.path.join(dataset, "data", "train.jsonl")
    _rewrite(train, lambda t: t + "{not json\n")
    rc, _, err = _main(capsys, dataset)
    assert rc == article_numbers.EXIT_ERROR and "line 11" in err


def test_files_disagree_exits_1(dataset, capsys):
    revision = os.path.join(dataset, "revision.json")
    with open(revision, encoding="utf-8") as fh:
        original = fh.read()
    _rewrite(revision, lambda t: t.replace('"bug":1', '"bug":2'))
    rc, out, err = _main(capsys, dataset)
    assert rc == article_numbers.EXIT_MISMATCH and "bug" in err and out == ""

    with open(revision, "w", encoding="utf-8") as fh:
        fh.write(original)
    train = os.path.join(dataset, "data", "train.jsonl")
    _rewrite(train, lambda t: t.replace('{"id":"REQ-999","status":"dangling"}',
                                        '{"id":"REQ-999","status":"resolved"}'))
    rc, _, err = _main(capsys, dataset)
    assert rc == article_numbers.EXIT_MISMATCH and "REQ-999" in err


# --- at publish (AC-13) ------------------------------------------------------------

def test_published_revision_reproduces_article(capsys):
    # Gated like the publish step's at-publish cases: skip unless
    # ADLC_DATASET_PUBLISHED=1; once set, a missing directory fails.
    if os.environ.get("ADLC_DATASET_PUBLISHED") != "1":
        pytest.skip("runs at publish: set ADLC_DATASET_PUBLISHED=1 and "
                    "ADLC_DATASET_PUBLISHED_DIR to a clone of the published dataset revision")
    published = os.environ.get("ADLC_DATASET_PUBLISHED_DIR", "")
    assert published, "ADLC_DATASET_PUBLISHED=1 needs ADLC_DATASET_PUBLISHED_DIR (a git clone)"
    assert os.path.isdir(published), "ADLC_DATASET_PUBLISHED_DIR=%s is not a directory" % published
    values = article_numbers.compute(published)
    assert article_numbers.compute(published) == values
    assert set(TOKEN_RE.findall(_draft())) - set(article_numbers.URL_TOKENS) == set(values)
    argv = ("--dataset-url", DATASET_URL, "--space-url", SPACE_URL, "--plugin-url", PLUGIN_URL)
    for flags in ((), argv):
        rc, rendered, err = _main(capsys, published, "--render", DRAFT, *flags)
        assert rc == article_numbers.EXIT_OK, err
        assert "{{" not in rendered
        enabled, urls = _urls(dataset=DATASET_URL, space=SPACE_URL,
                              plugin=PLUGIN_URL) if flags else _urls()
        _assert_reproduces(rendered, values, enabled, urls)
