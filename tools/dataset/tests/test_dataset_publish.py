"""The maintainer publish step (REQ-671 TASK-154).

The Hub client is never imported for real: ``hub`` puts a recording stand-in
for ``huggingface_hub`` into ``sys.modules``, so the suite needs no network and
no install. A refused run must leave that stand-in untouched. The TTY test and
the typed confirmation go through ``publish._isatty`` and ``publish._ask``.

The two at-publish cases (AC-12, AC-14) skip unless ``ADLC_DATASET_PUBLISHED=1``
and ``ADLC_DATASET_PUBLISHED_DIR`` names a ``git clone`` of the published
revision. ``tools/dataset/README.md`` says when to run them.
"""
import ast
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import types

import pytest

import denylist
import export
import publish
from dataset_helpers import DATASET_DIR, TOOLKIT

CLIENT_RE = re.compile(r"huggingface[_-]hub", re.IGNORECASE)
REPO_ID = "some-owner/adlc-artifacts"
ACCOUNT = "some-maintainer"
#: The calls a run makes before the typed confirmation: one read, nothing sent.
ACCOUNT_READ = [("HfApi", (), {}), ("whoami", (), {})]
SECRET_TOKEN = "hf_" + "Q" * 34

FIXTURE_DENYLIST = {
    "organization": "acme-org",
    "organization_repo": None,
    "public_repos": ["open-tool"],
    "repos": [{"name": "secret-api", "placeholder": "consumer-repo-1", "match": "token", "aliases": []}],
    "people": [{"name": "Dana", "placeholder": "the maintainer"}],
    "email_allowlist": ["noreply@anthropic.com"],
}

REQ = """---
id: REQ-001
title: "First requirement"
status: approved
tags: [a, b]
---

## Description

Builds on LESSON-002.
"""
LESSON = """---
id: LESSON-002
title: "A lesson"
tags: [x]
---

## Lesson

Cites REQ-001.
"""


# --- fixtures and helpers -----------------------------------------------------------

class FakeHub(object):
    """A stand-in for the Hub client module: it records every call and sends nothing."""

    OID = "c0ffee" + "0" * 34

    def __init__(self):
        self.calls = []
        self.uploaded = None
        self.deleted = None
        self.tags = []
        self.remote_files = []
        self.fail = None
        self.exists = True
        self.account = {"name": ACCOUNT, "type": "user"}
        hub = self

        class HfApi(object):
            def __init__(self, *args, **kwargs):
                hub.calls.append(("HfApi", args, kwargs))

            def whoami(self, *args, **kwargs):
                hub.calls.append(("whoami", args, kwargs))
                if hub.fail == "whoami":
                    raise RuntimeError("Invalid user token.")
                return hub.account

            def create_repo(self, *args, **kwargs):
                hub.calls.append(("create_repo", args, kwargs))

            def repo_exists(self, *args, **kwargs):
                hub.calls.append(("repo_exists", args, kwargs))
                return hub.exists

            def list_repo_refs(self, *args, **kwargs):
                hub.calls.append(("list_repo_refs", args, kwargs))
                return types.SimpleNamespace(tags=[types.SimpleNamespace(name=t)
                                                   for t in hub.tags])

            def list_repo_files(self, *args, **kwargs):
                hub.calls.append(("list_repo_files", args, kwargs))
                return list(hub.remote_files)

            def create_commit(self, *args, **kwargs):
                hub.calls.append(("create_commit", args, kwargs))
                hub.uploaded = dict((op.path_in_repo, op.path_or_fileobj)
                                    for op in kwargs["operations"] if op.kind == "add")
                hub.deleted = sorted(op.path_in_repo for op in kwargs["operations"]
                                     if op.kind == "delete")
                if hub.fail == "create_commit":
                    raise RuntimeError("upload broke")
                return types.SimpleNamespace(oid=FakeHub.OID)

            def create_tag(self, *args, **kwargs):
                hub.calls.append(("create_tag", args, kwargs))
                if hub.fail == "create_tag":
                    raise RuntimeError("tag broke")

        def add(path_in_repo, path_or_fileobj):
            return types.SimpleNamespace(kind="add", path_in_repo=path_in_repo,
                                         path_or_fileobj=path_or_fileobj)

        def delete(path_in_repo):
            return types.SimpleNamespace(kind="delete", path_in_repo=path_in_repo)

        self.module = types.ModuleType("huggingface_hub")
        self.module.HfApi = HfApi
        self.module.CommitOperationAdd = add
        self.module.CommitOperationDelete = delete


@pytest.fixture
def hub(monkeypatch):
    fake = FakeHub()
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake.module)
    return fake


@pytest.fixture
def dl_path(sandbox):
    """The fixture DenyList, written into the sandbox so the next commit carries it."""
    return sandbox.write(denylist.REPO_PATH, json.dumps(FIXTURE_DENYLIST))


@pytest.fixture
def terminal(monkeypatch):
    """A maintainer at a terminal who types ``answer`` (set per test)."""
    state = {"answer": REPO_ID, "asked": [], "on_ask": None}

    def ask(prompt):
        state["asked"].append(prompt)
        if state["on_ask"]:
            state["on_ask"]()
        if isinstance(state["answer"], BaseException):
            raise state["answer"]
        return state["answer"]

    monkeypatch.setattr(publish, "_isatty", lambda: True)
    monkeypatch.setattr(publish, "_ask", ask)
    return state


def _files_under(root):
    found = []
    for dirpath, _, names in os.walk(str(root)):
        for name in names:
            found.append(os.path.relpath(os.path.join(dirpath, name), str(root)))
    return sorted(p.replace(os.sep, "/") for p in found)


def _export(sandbox, dl_path, tmp_path):
    """Export a small sandbox tree on main; return ``(out dir, dataset dir, sha)``."""
    sandbox.write("VERSION", "1.2.3\n")
    sandbox.write(".adlc/specs/REQ-001-first/requirement.md", REQ)
    sandbox.write(".adlc/knowledge/lessons/LESSON-002-a.md", LESSON)
    sha = sandbox.commit()
    out = tmp_path / "out"
    assert export.main(["--commit", "main", "--out", str(out), "--repo", sandbox.root]) \
        == export.EXIT_OK
    return out, out / "dataset", sha


@pytest.fixture
def exported(sandbox, dl_path, tmp_path):
    return _export(sandbox, dl_path, tmp_path)


def _publish(sandbox, dl_path, dataset, repo_id=REPO_ID):
    # ``--repo-id=`` keeps argparse from reading a leading ``-`` as an option.
    return publish.main(["--dataset", str(dataset), "--repo-id=" + repo_id,
                         "--repo", sandbox.root])


def _rewrite_records(dataset, change):
    path = dataset / "data" / "train.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    change(records)
    path.write_text("".join(export.dumps(r) + "\n" for r in records), encoding="utf-8")


# --- refusals (BR-6, BR-2, BR-1) ----------------------------------------------------

def test_refuses_without_tty(sandbox, dl_path, exported, hub, terminal, monkeypatch, capsys):
    _, dataset, _ = exported
    monkeypatch.setattr(publish, "_isatty", lambda: False)
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert "publishing needs a maintainer at a terminal" in capsys.readouterr().err
    assert hub.calls == [] and terminal["asked"] == []


def test_cli_refuses_from_a_pipe(tmp_path):
    proc = subprocess.run([sys.executable, os.path.join(DATASET_DIR, "publish.py"),
                           "--dataset", str(tmp_path / "missing"), "--repo-id", REPO_ID],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert proc.returncode == publish.EXIT_REFUSED, proc.stderr
    assert "publishing needs a maintainer at a terminal" in proc.stderr


def test_real_isatty_refuses_a_pipe(monkeypatch):
    with open(os.devnull) as devnull:
        monkeypatch.setattr(sys, "stdin", devnull)
        assert publish._isatty() is False
    monkeypatch.setattr(sys, "stdin", None)
    assert publish._isatty() is False


@pytest.mark.parametrize("answer", ["some-owner/other", "", "y", EOFError(), KeyboardInterrupt()])
def test_refuses_on_mismatched_confirmation(sandbox, dl_path, exported, hub, terminal, capsys,
                                            answer):
    _, dataset, _ = exported
    terminal["answer"] = answer
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert terminal["asked"] == ["Type the repo id to publish: "]
    assert "does not match %s" % REPO_ID in capsys.readouterr().err
    assert hub.calls == ACCOUNT_READ


def _plant_body_name(dataset):
    _rewrite_records(dataset, lambda rs: rs[0].update(body=rs[0]["body"] + "\nsee secret-api\n"))
    return "data/train.jsonl record 1 body line", "denylist"


def _plant_escaped_path(dataset):
    # The raw line holds no "/Users/"; only the decoded value does.
    path = dataset / "data" / "train.jsonl"
    raw = path.read_text(encoding="utf-8").replace('"body":"', '"body":"\\/Users\\/someone\\/x ',
                                                   1)
    assert "/Users/" not in raw
    path.write_text(raw, encoding="utf-8")
    return "data/train.jsonl record 1 body line 1", "home-path"


def _plant_tag_person(dataset):
    _rewrite_records(dataset, lambda rs: rs[1]["tags"].append("by Dana"))
    return "data/train.jsonl record 2 tags line 1", "denylist"


def _plant_card_email(dataset):
    with open(str(dataset / "README.md"), "a", encoding="utf-8") as fh:
        fh.write("\nContact jane.doe@example.com\n")
    return "README.md line", "email"


def _plant_revision_repo_name(dataset):
    # A well-formed rule name, so the schema passes it and the residue pass must not.
    path = dataset / "revision.json"
    path.write_text(path.read_text(encoding="utf-8").replace(
        '"scrub_replacements":{', '"scrub_replacements":{"secret-api":1,'), encoding="utf-8")
    return "revision.json line 1", "denylist"


@pytest.mark.parametrize("plant", [_plant_body_name, _plant_escaped_path, _plant_tag_person,
                                   _plant_card_email, _plant_revision_repo_name])
def test_refuses_dataset_with_residue(sandbox, dl_path, exported, hub, terminal, capsys, plant):
    _, dataset, _ = exported
    where, detector = plant(dataset)
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    err = capsys.readouterr().err
    assert "residue:" in err and where in err and detector in err, err
    assert "secret-api" not in err and "jane.doe" not in err and "Dana" not in err
    assert hub.calls == [] and terminal["asked"] == []


def _add_report(dataset):
    shutil.copytree(str(dataset.parent / "report"), str(dataset / "report"))
    return "unexpected report/"


def _add_stray_file(dataset):
    (dataset / ".DS_Store").write_bytes(b"\0")
    return "unexpected .DS_Store"


def _add_nested_file(dataset):
    (dataset / "data" / "extra.jsonl").write_text("{}\n", encoding="utf-8")
    return "unexpected data/extra.jsonl"


def _remove_revision(dataset):
    (dataset / "revision.json").unlink()
    return "missing revision.json"


def _symlink_card(dataset):
    target = dataset.parent / "card.md"
    shutil.move(str(dataset / "README.md"), str(target))
    os.symlink(str(target), str(dataset / "README.md"))
    return "unexpected README.md"


@pytest.mark.parametrize("change", [_add_report, _add_stray_file, _add_nested_file,
                                    _remove_revision, _symlink_card])
def test_refuses_dataset_dir_with_extra_or_missing_file(sandbox, dl_path, exported, hub,
                                                        terminal, capsys, change):
    _, dataset, _ = exported
    problem = change(dataset)
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    err = capsys.readouterr().err
    assert problem in err and "no report" in err, err
    assert hub.calls == [] and terminal["asked"] == []


def test_refuses_commit_not_on_main(sandbox, dl_path, exported, hub, terminal, capsys):
    _, dataset, sha = exported
    sandbox.git("checkout", "-q", "-b", "side")
    sandbox.write(".adlc/bugs/BUG-009-side.md", "---\nid: BUG-009\n---\n\nSide.\n")
    side = sandbox.commit("side")
    path = dataset / "revision.json"
    path.write_text(path.read_text(encoding="utf-8").replace(sha, side), encoding="utf-8")
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert "is not an ancestor of main or origin/main" in capsys.readouterr().err
    path.write_text(path.read_text(encoding="utf-8").replace(side, "f" * 40), encoding="utf-8")
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert "is not a commit in" in capsys.readouterr().err
    assert hub.calls == [] and terminal["asked"] == []


@pytest.mark.parametrize("repo_id", ["no-slash", "a/b/c", "-lead/x", "owner/", "/name",
                                     "owner/na me", "https://huggingface.co/datasets/a/b"])
def test_refuses_bad_repo_id(sandbox, dl_path, exported, hub, terminal, capsys, repo_id):
    _, dataset, _ = exported
    terminal["answer"] = repo_id
    assert _publish(sandbox, dl_path, dataset, repo_id=repo_id) == publish.EXIT_REFUSED
    assert "is not <owner>/<name>" in capsys.readouterr().err
    assert hub.calls == [] and terminal["asked"] == []


def test_refuses_records_that_disagree_with_revision(sandbox, dl_path, exported, hub, terminal,
                                                     capsys):
    _, dataset, _ = exported
    _rewrite_records(dataset, lambda rs: rs.pop())
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert "revision.json says" in capsys.readouterr().err
    assert hub.calls == []


def test_refuses_record_outside_the_schema(sandbox, dl_path, exported, hub, terminal, capsys):
    _, dataset, _ = exported
    _rewrite_records(dataset, lambda rs: rs[0].update(extra="x"))
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert "columns differ from the card's schema" in capsys.readouterr().err
    assert hub.calls == []


def test_refuses_when_dataset_changes_after_confirmation(sandbox, dl_path, exported, hub,
                                                         terminal, capsys):
    _, dataset, _ = exported

    def edit():
        with open(str(dataset / "data" / "train.jsonl"), "a", encoding="utf-8") as fh:
            fh.write("\n")

    terminal["on_ask"] = edit
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert "changed after it was checked" in capsys.readouterr().err
    assert hub.calls == ACCOUNT_READ


def test_missing_client_is_an_error_not_a_pass(sandbox, dl_path, exported, terminal, capsys,
                                               monkeypatch):
    _, dataset, _ = exported
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)  # import raises ImportError
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_ERROR
    assert "python3 -m pip install -r tools/dataset/requirements.txt" in capsys.readouterr().err
    assert terminal["asked"] == []


def test_summary_names_the_account_before_the_question(sandbox, dl_path, exported, hub, terminal,
                                                       capsys):
    _, dataset, _ = exported
    seen = []
    terminal["on_ask"] = lambda: seen.append(capsys.readouterr().out)
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_OK
    assert "publish: account  %s\n" % ACCOUNT in seen[0]


@pytest.mark.parametrize("fail, account, message", [
    ("whoami", None, "reading the Hub account failed (RuntimeError: Invalid user token.)"),
    (None, {"type": "user"}, "did not name the account"),
    (None, {"name": ""}, "did not name the account"),
    (None, ["not", "a", "dict"], "did not name the account"),
], ids=["no-login", "no-name", "empty-name", "not-a-dict"])
def test_unreadable_account_is_an_error_before_the_question(sandbox, dl_path, exported, hub,
                                                            terminal, capsys, fail, account,
                                                            message):
    _, dataset, _ = exported
    hub.fail = fail
    if account is not None:
        hub.account = account
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_ERROR
    assert message in capsys.readouterr().err
    assert terminal["asked"] == []
    assert hub.calls == ACCOUNT_READ


# --- the publish itself (BR-6, BR-7) ----------------------------------------------------

def test_publishes_on_confirmation_with_stub(sandbox, dl_path, exported, hub, terminal, capsys,
                                             monkeypatch):
    out, dataset, sha = exported
    monkeypatch.setenv("HF_TOKEN", SECRET_TOKEN)
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_OK
    tag = "v1.2.3-" + sha[:12]
    assert re.match(r"^v1\.2\.3-[0-9a-f]{12}$", tag)
    assert [c[0] for c in hub.calls] == ["HfApi", "whoami", "repo_exists", "list_repo_refs",
                                         "list_repo_files", "create_repo", "create_commit",
                                         "create_tag"]
    assert hub.calls[0][1:] == ((), {})
    assert hub.calls[1][1:] == ((), {})
    assert hub.calls[5][1:] == ((REPO_ID,), {"repo_type": "dataset", "exist_ok": True})
    commit = hub.calls[6]
    assert commit[1] == (REPO_ID,)
    assert (commit[2]["repo_type"], commit[2]["commit_message"]) == (
        "dataset", "Export %s (toolkit 1.2.3)" % sha[:12])
    assert hub.calls[7][1:] == ((REPO_ID,), {"tag": tag, "repo_type": "dataset",
                                             "revision": FakeHub.OID})
    # The committed bytes are the checked files, read before the confirmation.
    assert sorted(hub.uploaded) == sorted(publish.DATASET_FILES)
    for rel in publish.DATASET_FILES:
        assert hub.uploaded[rel] == (dataset / rel).read_bytes()
    assert hub.deleted == []
    assert terminal["asked"] == ["Type the repo id to publish: "]
    captured = capsys.readouterr()
    report = os.path.join(str(out), "report", "scrub-report.md")
    assert "Read %s before continuing." % report in captured.out
    assert "https://huggingface.co/datasets/%s" % REPO_ID in captured.out
    assert "publish: tag %s" % tag in captured.out
    assert "requirement 1, architecture 0, task 0, lesson 1, bug 0, assumption 0" in captured.out
    assert SECRET_TOKEN not in captured.out + captured.err


def test_typed_repo_id_tolerates_surrounding_whitespace(sandbox, dl_path, exported, hub,
                                                        terminal):
    _, dataset, _ = exported
    terminal["answer"] = "  %s \n" % REPO_ID
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_OK
    assert [c[0] for c in hub.calls][-1] == "create_tag"


def test_refuses_when_tag_exists(sandbox, dl_path, exported, hub, terminal, capsys):
    _, dataset, sha = exported
    hub.tags = ["v1.2.2-" + sha[:12], "v1.2.3-" + sha[:12]]
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert "tag v1.2.3-%s already exists" % sha[:12] in capsys.readouterr().err
    # Refused before anything is created on the Hub.
    assert [c[0] for c in hub.calls] == ["HfApi", "whoami", "repo_exists", "list_repo_refs"]
    assert hub.uploaded is None


def test_other_tags_do_not_block(sandbox, dl_path, exported, hub, terminal):
    _, dataset, sha = exported
    hub.tags = ["v1.2.2-" + sha[:12], "v1.2.3-" + "0" * 12]
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_OK
    assert [c[0] for c in hub.calls][-1] == "create_tag"


def test_stale_remote_files_deleted_in_the_same_commit(sandbox, dl_path, exported, hub,
                                                      terminal):
    _, dataset, _ = exported
    hub.remote_files = [".gitattributes", "README.md", "data/train.jsonl", "revision.json",
                        "report/x.md", "old.parquet"]
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_OK
    assert hub.deleted == ["old.parquet", "report/x.md"]
    assert sorted(hub.uploaded) == sorted(publish.DATASET_FILES)
    assert [c[0] for c in hub.calls].count("create_commit") == 1


@pytest.mark.parametrize("fail, message, calls", [
    ("create_commit", "uploading failed (RuntimeError: upload broke)",
     ["HfApi", "whoami", "repo_exists", "list_repo_refs", "list_repo_files", "create_repo",
      "create_commit"]),
    ("create_tag", "by hand failed (RuntimeError: tag broke)",
     ["HfApi", "whoami", "repo_exists", "list_repo_refs", "list_repo_files", "create_repo",
      "create_commit",
      "create_tag"]),
])
def test_client_failure_is_an_error(sandbox, dl_path, exported, hub, terminal, capsys, fail,
                                    message, calls):
    _, dataset, sha = exported
    hub.fail = fail
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_ERROR
    err = capsys.readouterr().err
    assert message in err, err
    if fail == "create_tag":
        assert "create tag v1.2.3-%s by hand" % sha[:12] in err
    assert [c[0] for c in hub.calls] == calls


def test_refuses_an_edited_card(sandbox, dl_path, exported, hub, terminal, capsys):
    _, dataset, sha = exported
    with open(str(dataset / "README.md"), "a", encoding="utf-8") as fh:
        fh.write("\nA harmless extra sentence.\n")
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    err = capsys.readouterr().err
    assert "README.md differ from a fresh export of %s" % sha in err, err
    assert hub.calls == [] and terminal["asked"] == []


def _rev(change):
    def edit(dataset):
        path = dataset / "revision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")
    return edit


def _bad_reference_status(dataset):
    _rewrite_records(dataset, lambda rs: rs[0].update(
        references=[{"id": "LESSON-002", "status": "maybe"}]))


@pytest.mark.parametrize("edit, message", [
    (_rev(lambda d: d.update(source_commit="abc1234")), "source_commit is not a full commit SHA"),
    (_rev(lambda d: d.update(source_commit=d["source_commit"].upper())),
     "source_commit is not a full commit SHA"),
    (_rev(lambda d: d.update(toolkit_version="1.0 ; rm")), "toolkit_version is not a version"),
    (_rev(lambda d: d.update(toolkit_version=1.0)), "toolkit_version is not a version"),
    (_rev(lambda d: d.update(extra=1)), "revision.json must hold exactly"),
    (_rev(lambda d: d.pop("scrub_replacements")), "revision.json must hold exactly"),
    (_rev(lambda d: d["records"].update(lesson=True)), "records must count each of"),
    (_rev(lambda d: d["records"].update(bug=-1)), "records must count each of"),
    (_rev(lambda d: d["records"].pop("bug")), "records must count each of"),
    (_rev(lambda d: d.update(scrub_replacements=[])), "scrub_replacements must map rules"),
    (_rev(lambda d: d["scrub_replacements"].update(email=False)),
     "scrub_replacements must map rules"),
    (_rev(lambda d: d["scrub_replacements"].update({"https://example.com/x": 1})),
     "scrub_replacements must map rules"),
    (_rev(lambda d: d["scrub_replacements"].update(total=1)), "scrub_replacements must map rules"),
    (_rev(lambda d: d.update(scrub_replacements={})), "scrub_replacements must map rules"),
    (_rev(lambda d: d.update(source_commit=d["source_commit"] + "\n")),
     "source_commit is not a full commit SHA"),
    (_rev(lambda d: d.update(toolkit_version="1.2.3\n")), "toolkit_version is not a version"),
    (_bad_reference_status, "references is not a list of {id, status} objects"),
], ids=["short-sha", "upper-sha", "shell-version", "float-version", "extra-key", "missing-key",
        "bool-count", "negative-count", "missing-kind", "list-replacements", "bool-replacement",
        "url-rule", "total-rule", "no-rules", "newline-sha", "newline-version",
        "bad-reference-status"])
def test_refuses_malformed_revision_or_record(sandbox, dl_path, exported, hub, terminal, capsys,
                                              edit, message):
    _, dataset, _ = exported
    edit(dataset)
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    err = capsys.readouterr().err
    assert message in err, err
    assert hub.calls == [] and terminal["asked"] == []


# --- dependency isolation (BR-10) --------------------------------------------------------

#: Where the client may be named outside Markdown docs.
CLIENT_ALLOWED = ("tools/dataset/publish.py", "tools/dataset/requirements.txt",
                  "tools/dataset/tests/test_dataset_publish.py")


def _client_surface():
    """Every file BR-10 keeps the client out of, root-relative."""
    paths = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(TOOLKIT, "tools")):
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and d not in ("__pycache__",
                                                                    "node_modules"))
        for name in filenames:
            if not name.endswith(".md"):
                paths.append(os.path.relpath(os.path.join(dirpath, name), TOOLKIT))
    for pattern in ("*/SKILL.md", "proceed/*.md", "agents/*.md", "partials/*", "scripts/*",
                    "hooks/*", "workflows/*.js", "install.sh"):
        paths.extend(os.path.relpath(p, TOOLKIT)
                     for p in glob.glob(os.path.join(TOOLKIT, pattern)) if os.path.isfile(p))
    return sorted(set(p.replace(os.sep, "/") for p in paths))


def test_hub_client_imported_only_by_publish():
    surface = _client_surface()
    for required in ("tools/adlc/checks.py", "tools/delegate/requirements.txt", "install.sh",
                     "tools/dataset/export.py", "spec/SKILL.md") + CLIENT_ALLOWED:
        assert required in surface, required  # the walk reached what BR-10 names
    assert len([p for p in surface if p.endswith("/SKILL.md")]) >= 10
    offenders = []
    for rel in surface:
        with open(os.path.join(TOOLKIT, rel), "rb") as fh:
            text = fh.read().decode("utf-8", "replace")
        if CLIENT_RE.search(text) and rel not in CLIENT_ALLOWED:
            offenders.append(rel)
    assert offenders == []

    with open(os.path.join(DATASET_DIR, "publish.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node
    imports = [n for n in ast.walk(tree)
               if (isinstance(n, ast.Import) and any(CLIENT_RE.match(a.name) for a in n.names))
               or (isinstance(n, ast.ImportFrom) and CLIENT_RE.match(n.module or ""))]
    assert len(imports) == 1
    node = imports[0]
    while not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
        node = node.parent
    assert isinstance(node, ast.FunctionDef) and node.name == "_hub_api"

    with open(os.path.join(DATASET_DIR, "requirements.txt"), encoding="utf-8") as fh:
        pins = [line.strip() for line in fh
                if line.strip() and not line.lstrip().startswith("#")]
    assert pins == ["huggingface_hub==0.26.2"]


def test_importing_publish_does_not_import_client(tmp_path):
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "huggingface_hub.py").write_text("raise RuntimeError('client imported')\n")
    code = "\n".join([
        "import sys",
        "sys.path[:0] = [%r, %r]" % (str(fake), DATASET_DIR),
        "import publish",
        "assert 'huggingface_hub' not in sys.modules",
        "try:",
        "    publish._hub_api()",
        "except RuntimeError as exc:",
        "    print('inside the function:', exc)",
    ])
    proc = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "inside the function: client imported"


# --- docs (BR-12) -----------------------------------------------------------------------

def _fenced_lines(text):
    lines, inside = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
        elif inside:
            lines.append(line.strip())
    return lines


def test_readme_documents_one_reexport_command():
    with open(os.path.join(DATASET_DIR, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    fenced = _fenced_lines(readme)
    exports = [line for line in fenced
               if line.startswith("python3 tools/dataset/export.py --commit")]
    assert exports == ["python3 tools/dataset/export.py --commit origin/main "
                       "--out ~/adlc-dataset/<version>"]
    publishes = [line for line in fenced if line.startswith("python3 tools/dataset/publish.py")]
    assert len(publishes) == 1 and "--dataset" in publishes[0] and "--repo-id" in publishes[0]
    assert fenced.index(exports[0]) < fenced.index(publishes[0])
    assert "not automatic" in readme and "scrub-report.md" in readme
    with open(os.path.join(TOOLKIT, "RELEASING.md"), encoding="utf-8") as fh:
        releasing = fh.read()
    assert "tools/dataset/README.md" in releasing
    assert not any("tools/dataset/export.py" in line for line in _fenced_lines(releasing))


# --- at publish, after merge (AC-12, AC-14) ---------------------------------------------

def _published_dir():
    """The clone of the published revision, or skip; a bad setting fails."""
    if os.environ.get("ADLC_DATASET_PUBLISHED") != "1":
        pytest.skip("at-publish check: set ADLC_DATASET_PUBLISHED=1 and "
                    "ADLC_DATASET_PUBLISHED_DIR (tools/dataset/README.md)")
    root = os.environ.get("ADLC_DATASET_PUBLISHED_DIR", "")
    assert root, "ADLC_DATASET_PUBLISHED=1 needs ADLC_DATASET_PUBLISHED_DIR (a git clone)"
    assert os.path.isdir(os.path.join(root, ".git")), \
        "ADLC_DATASET_PUBLISHED_DIR=%s is not a git clone" % root
    data = os.path.join(root, "data", "train.jsonl")
    with open(data, "rb") as fh:
        head = fh.read(64)
    assert not head.startswith(b"version https://git-lfs"), \
        "%s is a Git LFS pointer; install git-lfs and run git lfs pull" % data
    return root


def test_published_revision_loads():
    root = _published_dir()
    try:
        import datasets
    except ImportError:
        pytest.fail("ADLC_DATASET_PUBLISHED=1 needs the datasets library in this venv")
    ds = datasets.load_dataset("json", data_files=os.path.join(root, "data", "train.jsonl"),
                               split="train")
    assert tuple(sorted(ds.column_names)) == tuple(sorted(export.COLUMNS))
    with open(os.path.join(root, "revision.json"), encoding="utf-8") as fh:
        revision = json.load(fh)
    assert len(ds) == sum(revision["records"].values()) > 0


def test_readme_records_urls_after_publish():
    root = _published_dir()
    remote = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"],
                            capture_output=True, text=True)
    assert remote.returncode == 0, remote.stderr
    url = re.sub(r"(\.git)?/*$", "", remote.stdout.strip())
    assert url.startswith("https://huggingface.co/datasets/"), url
    with open(os.path.join(TOOLKIT, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    assert url in readme, "the root README does not record the dataset URL %s" % url
    assert re.search(r"https://huggingface\.co/blog/[A-Za-z0-9_./-]+", readme), \
        "the root README does not record the article URL"


def test_weakened_working_tree_denylist_does_not_pass_residue(sandbox, dl_path, exported, hub,
                                                              terminal, capsys):
    """Publish reads the DenyList committed at source_commit, not the working tree."""
    _, dataset, _ = exported
    _rewrite_records(dataset, lambda records: records[0].update(body="see secret-api"))
    sandbox.write(denylist.REPO_PATH, json.dumps(dict(FIXTURE_DENYLIST, repos=[])))
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_REFUSED
    assert "residue:" in capsys.readouterr().err
    assert hub.calls == []


def test_unreadable_dataset_file_is_an_error_not_a_refusal(sandbox, dl_path, exported, hub,
                                                           terminal, monkeypatch):
    _, dataset, _ = exported

    def broken(_):
        raise OSError("disk went away")
    monkeypatch.setattr(publish, "read_dataset", broken)
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_ERROR
    assert hub.calls == []


def test_new_repo_skips_tag_and_file_listing(sandbox, dl_path, exported, hub, terminal):
    _, dataset, _ = exported
    hub.exists = False
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_OK
    assert [c[0] for c in hub.calls] == ["HfApi", "whoami", "repo_exists", "create_repo", "create_commit",
                                         "create_tag"]


def test_missing_commit_id_is_not_tagged(sandbox, dl_path, exported, hub, terminal, capsys,
                                         monkeypatch):
    _, dataset, _ = exported
    monkeypatch.setattr(FakeHub, "OID", None)
    assert _publish(sandbox, dl_path, dataset) == publish.EXIT_ERROR
    assert "create_tag" not in [c[0] for c in hub.calls]
    assert "no commit id" in capsys.readouterr().err
