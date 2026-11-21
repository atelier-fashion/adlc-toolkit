"""The fence census: every fence an exec run can meet has a route (REQ-682 BR-1, BR-8, AC-2),
one census per exec-capable adapter (REQ-662 BR-3, ADR-8, ADR-9)."""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import exec_adapter as ea  # noqa: E402
import exec_matcher as em  # noqa: E402
import exec_prompt as ep  # noqa: E402
import fence_census as fc  # noqa: E402
import recording_stubs as rs  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
FIXTURE = os.path.join(HERE, "fixtures", "exec-fence", "extra-fences.md")
#: A Codex-shaped adapter with ``matcher: none``: a harness whose matching nothing models.
MATCHER_NONE = os.path.join(HERE, "fixtures", "harness", "fake-exec-file.yml")
ROUTES = ("direct", "runner", "engine", "excised")
PUSH_KEY = "proceed/phase-0-setup.md#6"


@pytest.fixture(scope="module")
def claude():
    return ea.load("claude", TOOLKIT)


@pytest.fixture(scope="module")
def records(claude):
    return fc.census(TOOLKIT, claude)


def with_matcher_none(root):
    """``root`` with the matcher-none fixture adapter shipped beside the real ones; returns
    ``(root, {name: adapter})`` for every exec-capable adapter under it."""
    shutil.copy(MATCHER_NONE, os.path.join(root, "harness"))
    return root, {a.name: a for a in fc.exec_adapters(root)}


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    """A toolkit copy with two exec-capable adapters: ``claude`` and ``fake-exec-file``."""
    return with_matcher_none(rs.toolkit_copy(str(tmp_path_factory.mktemp("two") / "tk")))


@pytest.fixture(scope="module")
def prompts():
    pipe = ep.pipeline_prompt(TOOLKIT, TOOLKIT, "REQ-901", "feat/REQ-901-thing", "/abs/repo",
                              "/abs/repo/.worktrees/REQ-901").decode("utf-8")
    close = ep.closeout_prompt(TOOLKIT, "REQ-901", "chore/REQ-901-close-out", "/abs/co",
                               "EVIDENCE").decode("utf-8")
    return pipe, close


def test_every_fence_has_a_route(records):
    assert records, "the census is empty"
    for rec in records:
        assert rec["route"] in ROUTES, (rec["id"], rec["route"], rec.get("reason"))
        assert fc._ID_OK.match(rec["id"]), rec["id"]


def test_real_tree_has_no_unrouted_fence(records):
    """Benign path: the unmodified tree reports no unrouted fence, on any adapter."""
    assert fc.unrouted(records) == []
    for adapter in fc.exec_adapters(TOOLKIT):
        assert fc.unrouted(fc.census(TOOLKIT, adapter)) == [], adapter.name


def test_census_covers_invoked_skills_and_agents(records, prompts):
    """The set covers the delivered prompts and every file they send the model to, in both
    directions; and every fence of the delivered views is a record, counted, not hand-kept."""
    assert fc.coverage_problems(TOOLKIT, list(prompts)) == []
    ids = {r["id"] for r in records}
    counted = 0
    for rel in fc.EXEC_FILES:
        for fence in fc.fences(fc.view(TOOLKIT, rel), rel):
            assert fence.id in ids, fence.id
            counted += 1
    assert counted == len(records)
    pipeline_fences = sum(len(fc.fences(fc.view(TOOLKIT, rel), rel)) for rel in fc.PIPELINE_FILES)
    assert pipeline_fences == len([r for r in records if r["id"].split("#")[0]
                                   in fc.PIPELINE_FILES])


def test_invoked_name_missing_from_the_set_fails(monkeypatch, prompts):
    smaller = tuple(rel for rel in fc.EXEC_FILES if rel != "validate/SKILL.md")
    monkeypatch.setattr(fc, "EXEC_FILES", smaller)
    problems = fc.coverage_problems(TOOLKIT, list(prompts))
    assert any("validate/SKILL.md is named" in p for p in problems), problems


def test_listed_file_no_longer_named_is_reported(monkeypatch, prompts):
    monkeypatch.setattr(fc, "EXEC_FILES", fc.EXEC_FILES + ("agents/adversary.md",))
    problems = fc.coverage_problems(TOOLKIT, list(prompts))
    assert any("agents/adversary.md is in EXEC_FILES but no delivered text" in p
               for p in problems), problems


def test_direct_fences_admitted_statement_by_statement(records, claude):
    """AC-2's positive half: a `direct` fence's statements are admitted over the rendered
    ExecPolicy, as written or as the exec notes tell the model to run it (LESSON-779)."""
    policy = fc.exec_policy(TOOLKIT, claude)
    direct = [r for r in records if r["route"] == "direct"]
    assert direct
    for rec in direct:
        rel, ordinal = rec["id"].split(":")[0].split("#")
        fence = fc.fences(fc.view(TOOLKIT, rel), rel)[int(ordinal) - 1]
        assert em.admits(policy, fence.code) or fc._direct_with_samples(fence.code, policy), \
            rec["id"]


def test_phase0_git_c_fences_are_engine_and_br24_fences_excised(records):
    by_key = {r["id"].split(":")[0]: r for r in records}
    for n in (1, 3, 4):
        assert by_key["proceed/phase-0-setup.md#%d" % n]["route"] == "engine"
    tokens = [t for t in ep.EMPTY_ALLOWLIST + ep.CLOSEOUT_EMPTY if t]
    for rel in fc.EXEC_FILES:
        for fence in fc.fences(fc.view(TOOLKIT, rel), rel):
            if any(t in fence.code for t in tokens):
                assert by_key[fence.key]["route"] == "excised", fence.id


def test_golden_matches_fresh_census(records):
    """Every exec-capable adapter's committed golden is its fresh census (REQ-662 ADR-8)."""
    for adapter in fc.exec_adapters(TOOLKIT):
        rel = fc.golden_path(adapter.name)
        with open(os.path.join(TOOLKIT, rel), encoding="utf-8") as fh:
            golden = fh.read()
        assert golden == fc.dumps(fc.golden_doc(fc.census(TOOLKIT, adapter))), \
            "%s is stale: run fence_census.py --write" % rel
        assert not rel.startswith("harness/%s/rendered/" % adapter.name)
    with open(os.path.join(TOOLKIT, fc.golden_path("claude")), encoding="utf-8") as fh:
        assert fh.read() == fc.dumps(fc.golden_doc(records))
    assert fc.stale_goldens(TOOLKIT) == []
    assert fc.main(["--check"]) == 0


def test_census_has_no_harness_default(two):
    """With no adapter the census is the merge over every exec-capable adapter: a fence is
    `runner` there when any adapter routes it `runner`, never one harness's routes."""
    root, adapters = two
    per = [fc.census(root, a) for _name, a in sorted(adapters.items())]
    merged = {r["id"]: r for r in fc.census(root)}
    assert set(merged) == {r["id"] for r in per[0]}
    for records in per:
        for rec in records:
            if rec["route"] == "runner":
                assert merged[rec["id"]]["route"] == "runner", rec["id"]
    assert merged[next(i for i in merged if i.startswith(PUSH_KEY + ":"))]["route"] == "runner"


def test_matcher_none_routes_nothing_direct(two):
    """BR-3: on a `matcher: none` adapter no fence is `direct` and none is unrouted; the
    Step 0 branch push takes the runner route, as the branch-push kind (ADR-9)."""
    root, adapters = two
    records = fc.census(root, adapters["fake-exec-file"])
    assert [r["id"] for r in records if r["route"] == "direct"] == []
    assert fc.unrouted(records) == []
    push = next(r for r in records if r["id"].startswith(PUSH_KEY + ":"))
    assert push["route"] == "runner", push
    assert push["push"] == fc.BRANCH_PUSH and push["reach"] == ["git push"]
    assert push["placeholders"] == ["branch", "worktree"]
    assert [r["id"] for r in records if r.get("push")] == [push["id"]]


def test_claude_routes_are_the_golden_beside_a_matcher_none_adapter(two):
    """On `claude` every route is what the committed golden says, even with a second adapter
    widening the union deny tier: the push fence stays `direct` (ADR-9)."""
    root, adapters = two
    records = fc.census(root, adapters["claude"])
    with open(os.path.join(TOOLKIT, fc.golden_path("claude")), encoding="utf-8") as fh:
        assert fh.read() == fc.dumps(fc.golden_doc(records))
    push = next(r for r in records if r["id"].startswith(PUSH_KEY + ":"))
    assert push["route"] == "direct" and "push" not in push


def test_check_fails_when_any_adapter_golden_is_stale(tmp_path):
    """`fence_census --check` holds every adapter's golden fresh: a missing golden, a stale
    one and one naming no exec-capable adapter each fail it; --write makes it pass."""
    root, adapters = with_matcher_none(rs.toolkit_copy(str(tmp_path / "tk")))
    script = os.path.join(root, "tools", "adlc", "fence_census.py")

    def check():
        return subprocess.run([sys.executable, "-I", script, "--check"], cwd=root,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
    fake = fc.golden_path("fake-exec-file")
    assert fc.stale_goldens(root) == ["%s is missing" % fake]
    out = check()
    assert out.returncode == 1 and "%s is missing" % fake in out.stderr, out.stderr
    assert sorted(fc.write_goldens(root)) == sorted(fc.golden_path(n) for n in adapters)
    assert fc.stale_goldens(root) == [] and check().returncode == 0
    with open(os.path.join(root, fc.golden_path("claude")), encoding="utf-8") as fh:
        claude_after = fh.read()
    with open(os.path.join(TOOLKIT, fc.golden_path("claude")), encoding="utf-8") as fh:
        assert fh.read() == claude_after
    with open(os.path.join(root, fake), "a", encoding="utf-8") as fh:
        fh.write(" ")
    assert fc.stale_goldens(root) == ["%s is stale" % fake]
    out = check()
    assert out.returncode == 1 and "%s is stale" % fake in out.stderr, out.stderr
    fc.write_goldens(root)
    # copilot's stage has not run (REQ-662 Amendments), so it is not exec-capable.
    orphan = os.path.join(root, "harness", "copilot", fc.GOLDEN_NAME)
    os.makedirs(os.path.dirname(orphan), exist_ok=True)
    shutil.copy(os.path.join(root, fake), orphan)
    assert fc.stale_goldens(root) == ["%s names no exec-capable adapter" %
                                      fc.golden_path("copilot")]
    assert check().returncode == 1


def test_an_adapter_that_will_not_load_refuses_the_census(tmp_path):
    """Fail closed: an adapter whose deny tier cannot be read refuses every census, since the
    union the reach audit reads would be incomplete."""
    root = rs.toolkit_copy(str(tmp_path / "tk"))
    with open(os.path.join(root, "harness", "fake-exec-file.yml"), "w") as fh:
        fh.write("name: fake-exec-file\nunknown_key: 1\n")
    with pytest.raises(fc.CensusError, match="fake-exec-file.yml does not load"):
        fc.exec_adapters(root)
    with pytest.raises(fc.CensusError):
        fc.census(root)


@pytest.mark.parametrize("value,ok", [
    ("feat/REQ-901-thing", True), ("fix/BUG-12.x_y", True), ("chore/REQ-901-close-out", True),
    ("main", False), ("+feat/x", False), ("feat/x:main", False), ("--force", False),
    ("", False), ("feat/-x", False), ("feat/.x", False), ("feat/", False),
    ("refs/heads/feat/x", False), ("feat/x y", False), ("feat/x\n", False),
    ("HEAD:feat/x", False), ("feat/../main", False),
])
def test_branch_placeholder_pattern(value, ok):
    """ADR-9: the branch value cannot spell the integration branch, a refspec, a `+` prefix or
    an option; both placeholder spellings share the one pattern."""
    for key in ("branch", "branch-name"):
        assert (fc.PLACEHOLDERS[key].check(value) is None) is ok, (key, value)


@pytest.fixture
def copy(tmp_path):
    return rs.toolkit_copy(str(tmp_path / "tk"))


def _append_fixture(root):
    path = os.path.join(root, "proceed", "phase-4-implementation.md")
    with open(FIXTURE, encoding="utf-8") as fh:
        extra = fh.read()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n" + extra)


def test_unrouted_fixture_fence_is_named(copy):
    """BR-8: a fence a skill gains with no route is named, with the statement no allow
    admits; a placeholder outside a value position and an unknown name are unrouted too."""
    _append_fixture(copy)
    bad = {r["id"].split(":")[0]: r for r in fc.unrouted(fc.census(copy, ea.load("claude", copy)))}
    base = len(fc.fences(fc.view(TOOLKIT, "proceed/phase-4-implementation.md")))
    keys = ["proceed/phase-4-implementation.md#%d" % (base + k) for k in (1, 2, 3)]
    assert sorted(bad) == sorted(keys), sorted(bad)
    first = bad[keys[0]]
    assert first["refused"][0].startswith("scp "), first
    assert "neither the function index nor EXTERNAL" in first["reason"]
    assert "could become code" in bad[keys[1]]["reason"]
    assert "not in the closed table" in bad[keys[2]]["reason"]


@pytest.mark.parametrize("code,expected", [
    ('adlc_x "<state>"', 'adlc_x "${ADLC_ARG_state}"'),
    ("adlc_x '<state>'", 'adlc_x "${ADLC_ARG_state}"'),
    ("adlc_x <mode> --y", 'adlc_x ${ADLC_ARG_mode:+"${ADLC_ARG_mode}"} --y'),
    ('adlc_x --base "origin/<integrationBranch>"', 'adlc_x --base "origin/${ADLC_ARG_integrationBranch}"'),
    ("adlc_x origin/<integrationBranch>", 'adlc_x origin/"${ADLC_ARG_integrationBranch}"'),
    ('adlc_x --component "<component>"', 'adlc_x --component "${ADLC_ARG_component_0}" '
                                         '--component "${ADLC_ARG_component_1}"'),
    ('adlc_x "$prNumber" "$NEW_BODY"', 'adlc_x "${ADLC_ARG_prNumber}" "${ADLC_ARG_NEW_BODY}"'),
])
def test_transform_binds_values_as_data(code, expected):
    values = {"state": ["s"], "mode": [""], "integrationBranch": ["main"],
              "component": ["a", "b"], "prNumber": ["7"], "NEW_BODY": ["b"]}
    assert fc.transform(code, values, root="/abs/tk") == expected


@pytest.mark.parametrize("code", [
    "awk '{print \"<state>\"}' f",
    "sh -c \"echo <state>\"",
    "eval \"x <state>\"",
    "cat <<'EOF'\nsee <state> here\nEOF",
    "adlc_x '<state> and more'",
])
def test_placeholder_in_a_code_position_is_unroutable(code):
    with pytest.raises(fc.Unroutable):
        fc.plan(code)


def test_canonical_lines_are_rewritten_to_the_toolkit():
    code = fc.ROOT_LINE + "\n" + \
        'if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . ' \
        '"$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi\nadlc_forge_pr_view 1'
    out = fc.transform(code, {}, root="/abs/tk")
    assert out.split("\n") == ['ADLC_TOOLKIT_ROOT="/abs/tk"; export ADLC_TOOLKIT_ROOT',
                               '. "/abs/tk/partials/forge.sh"', "adlc_forge_pr_view 1"]
    with pytest.raises(fc.Unroutable, match="canonical spelling"):
        fc.plan(". .adlc/partials/forge.sh\nadlc_forge_pr_view 1")


def test_golden_is_valid_json_with_every_record():
    with open(os.path.join(TOOLKIT, fc.golden_path("claude")), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert {r["route"] for r in doc["fences"]} <= set(ROUTES)
    assert any(r["route"] == "runner" and r.get("reach") for r in doc["fences"])


def test_root_line_is_the_lint_s_canonical_line():
    """The census recognizes the root line by its canonical bytes, held equal to the ones
    `toolkit-root-line` pins, so a respelled root line is never silently rewritten."""
    sys.path.insert(0, os.path.join(TOOLKIT, "tools", "lint-skills"))
    import check
    assert fc.ROOT_LINE == check.TOOLKIT_ROOT_LINE


def test_a_variable_the_fence_assigns_is_left_alone():
    """Only a variable the fence never assigns is bound: proceed's own `$flag`, set by
    `skill-flag.sh create` two lines up, is the fence's, never an empty ADLC_ARG_flag."""
    code = 'flag=$(x create)\nmark "$flag" a\nedit "$prNumber"'
    out = fc.transform(code, {"prNumber": ["7"]}, root="/abs/tk")
    assert 'mark "$flag" a' in out
    assert 'edit "${ADLC_ARG_prNumber}"' in out
    rec = next(r for r in fc.census(TOOLKIT, ea.load("claude", TOOLKIT))
               if r["id"].startswith("proceed/SKILL.md#1:"))
    assert rec["route"] == "runner" and "flag" not in rec["placeholders"]


# --------------------------------------------------------------------------- REQ-719 BR-13
UNMARKED_FIXTURE = os.path.join(HERE, "fixtures", "exec-fence", "unmarked-pr-arg.md")


def test_req719_every_pr_number_placeholder_carries_the_mark():
    """BR-13: the tie is keyed on the placeholder. Every entry of the closed tables whose
    pattern is a PR number's carries the PR mark, and no other entry does."""
    tables = (fc.PLACEHOLDERS, fc.LITERAL_PLACEHOLDERS, fc.VAR_PLACEHOLDERS)
    pr_pattern = fc.Placeholder("x", "x", fc.PR_NUMBER).pattern.pattern
    marked = []
    for table in tables:
        for key, ph in table.items():
            assert ph.pr is (ph.pattern.pattern == pr_pattern), (key, ph.pattern.pattern)
            if ph.pr:
                marked.append((key, ph.arg))
    assert sorted(marked) == [("prNumber", "pr"), ("prNumber", "prNumber")]


def test_req719_every_operation_but_create_and_list_takes_a_pr():
    """BR-13's six operations take a PR, and so does one the adapter gains later: the rule
    names the two that take none, so a new operation starts checked (LESSON-781)."""
    for op in ("view", "edit", "ready", "comment", "checks", "merge", "close"):
        assert fc.is_pr_operation("adlc_forge_pr_" + op), op
    for name in ("adlc_forge_pr_create", "adlc_forge_pr_list", "adlc_forge_commit_prs",
                 "adlc_forge_branch_protection", "gh"):
        assert not fc.is_pr_operation(name), name


#: ``(case, body, operation, what the reason names)``: a call whose argv is not a closed shape.
#: Every shape the reviews found routing (F1 a to g, F11, the re-verification probes in
#: scratchpad/rv719c and the security re-audit's in scratchpad/rv3) is here, refused.
REFUSED = [
    # The PR argument is not one of its spellings.
    ("an unmarked placeholder", 'adlc_forge_pr_edit "<n>" --title "<short title>"',
     "adlc_forge_pr_edit", '"<n>"'),
    ("an unmarked free variable", 'adlc_forge_pr_ready "$LESSON_NUM"',
     "adlc_forge_pr_ready", '"$LESSON_NUM"'),
    ("a literal placeholder", 'adlc_forge_pr_view "REQ-xxx" --fields state',
     "adlc_forge_pr_view", '"REQ-xxx"'),
    ("inside a substitution", 'x=$(adlc_forge_pr_view "<n>" --json body -q .body)',
     "adlc_forge_pr_view", '"<n>"'),
    ("text beside the placeholder", 'adlc_forge_pr_view "#<prNumber>" --fields state',
     "adlc_forge_pr_view", '"#<prNumber>"'),
    ("a bare literal", "adlc_forge_pr_view 1 --fields state", "adlc_forge_pr_view", "1"),
    ("a default in the expansion", 'adlc_forge_pr_view "${prNumber:-<id>}" --fields state',
     "adlc_forge_pr_view", "${prNumber:-<id>}"),
    ("an assigning expansion", 'adlc_forge_pr_view "${prNumber:=<id>}" --fields state',
     "adlc_forge_pr_view", "${prNumber:=<id>}"),
    ("F1 d: set --", 'set -- <id>\nadlc_forge_pr_edit "$1" --title x',
     "adlc_forge_pr_edit", '"$1"'),
    ("F1 e: a function's argument", 'f() { adlc_forge_pr_view "$1" --fields state; }; f <id>',
     "defines the function f", None),
    ("a status", "f() { return '<id>'; }\nf; n=$?\nadlc_forge_pr_view \"$n\" --fields state",
     "defines the function f", None),
    ("a status, directly", "test '<id>' = 5; adlc_forge_pr_view \"$?\" --fields state",
     "adlc_forge_pr_view", '"$?"'),
    ("an indirect expansion", "v=ADLC_ARG\\_title\nadlc_forge_pr_view \"${!v}\" --fields state",
     "ADLC_ARG", None),
    # A variable the fence writes from anything but one forge call standing alone.
    ("F1 a: a substitution", 'n=$(printf %s "<id>")\nadlc_forge_pr_view "$n" --fields state',
     "adlc_forge_pr_view", '"$n"'),
    ("an assigned placeholder", 'n="<n>"\nadlc_forge_pr_view "$n" --json body',
     "adlc_forge_pr_view", '"$n"'),
    ("an assigned marked placeholder", 'n="<prNumber>"\nadlc_forge_pr_view "$n" --fields state',
     "adlc_forge_pr_view", '"$n"'),
    ("through another variable", 'n="<n>"; m="pr-$n"\nadlc_forge_pr_comment "$m" --body x',
     "adlc_forge_pr_comment", '"$m"'),
    ("arithmetic", 'n=$((<n> + 1))\nadlc_forge_pr_checks "$n"', "adlc_forge_pr_checks", '"$n"'),
    ("a for list", 'for n in "<n>" 7; do adlc_forge_pr_ready "$n"; done',
     "adlc_forge_pr_ready", '"$n"'),
    ("a for list of one", 'for p in <id>; do adlc_forge_pr_edit "$p" --title x; done',
     "adlc_forge_pr_edit", '"$p"'),
    ("read from a here-document",
     "while read -r n; do adlc_forge_pr_edit \"$n\" --title x; done <<'EOF'\n<n>\nEOF",
     "adlc_forge_pr_edit", '"$n"'),
    ("F1 b: read in a brace group",
     'printf "%s\\n" "<id>" | { read n; adlc_forge_pr_view "$n" --fields state; }',
     "adlc_forge_pr_view", '"$n"'),
    ("F1 b: read in a while loop",
     'printf "<id>" | while read -r p; do adlc_forge_pr_edit "$p" --title x; done',
     "adlc_forge_pr_edit", '"$p"'),
    ("F1 c: a here-string", 'read n <<< "<id>"\nadlc_forge_pr_view "$n" --fields state',
     "adlc_forge_pr_view", '"$n"'),
    ("read with IFS", "IFS=x read n <<EOF\n<id>\nEOF\nadlc_forge_pr_view \"$n\" --fields state",
     "adlc_forge_pr_view", '"$n"'),
    ("a function's output", "f() { printf '%s' '<id>'; }\nn=$(f)\nadlc_forge_pr_view \"$n\"",
     "defines the function f", None),
    ("a function piped into read",
     "f() { printf '%s\\n' '<id>'; }\nf | { read n; adlc_forge_pr_view \"$n\"; }",
     "defines the function f", None),
    ("a function's global", "f() { n='<id>'; }\nf\nadlc_forge_pr_view \"$n\" --fields state",
     "defines the function f", None),
    ("a heredoc through a function", "g() { cat; }\nn=$(g <<EOF\n<id>\nEOF\n)\n"
     "adlc_forge_pr_view \"$n\" --fields state", "defines the function g", None),
    ("tee and a file", "printf '%s' '<id>' | tee /tmp/adlcx >/dev/null\nn=$(cat /tmp/adlcx)\n"
     "adlc_forge_pr_view \"$n\"", "adlc_forge_pr_view", '"$n"'),
    ("cp", "printf '%s' '<id>' > /tmp/adlca\ncp /tmp/adlca /tmp/adlcb\nn=$(cat /tmp/adlcb)\n"
     "adlc_forge_pr_view \"$n\"", "adlc_forge_pr_view", '"$n"'),
    ("dd of=", "printf '%s' '<id>' | dd of=/tmp/adlcy 2>/dev/null\nn=$(cat /tmp/adlcy)\n"
     "adlc_forge_pr_view \"$n\"", "adlc_forge_pr_view", '"$n"'),
    ("ln -s", "printf '%s' '<id>' > /tmp/adlca\nln -s /tmp/adlca /tmp/adlcl\n"
     "n=$(cat /tmp/adlcl)\nadlc_forge_pr_view \"$n\"", "adlc_forge_pr_view", '"$n"'),
    ("another spelling of the path", "printf '%s' '<id>' > /tmp/adlcx\nn=$(cat /tmp//adlcx)\n"
     "adlc_forge_pr_view \"$n\"", "adlc_forge_pr_view", '"$n"'),
    ("a glob of the path", "printf '%s' '<id>' > /tmp/adlcx\nn=$(cat /tmp/adlc?)\n"
     "adlc_forge_pr_view \"$n\"", "adlc_forge_pr_view", '"$n"'),
    ("a file in the working copy", "n=$(cat pr-number.txt)\nadlc_forge_pr_edit \"$n\" --title x",
     "adlc_forge_pr_edit", '"$n"'),
    ("read from a file", "read -r n < pr-number.txt\nadlc_forge_pr_edit \"$n\" --title x",
     "adlc_forge_pr_edit", '"$n"'),
    ("the state file by its literal path",
     "n=$(sed -n 's/.*\"prNumber\": *\\([0-9]*\\).*/\\1/p' "
     ".adlc/specs/REQ-100-x/pipeline-state.json)\nadlc_forge_pr_ready \"$n\"",
     "adlc_forge_pr_ready", '"$n"'),
    ("printenv", "n='<id>'\nexport n\nm=$(printenv n)\nadlc_forge_pr_view \"$m\"",
     "adlc_forge_pr_view", '"$m"'),
    ("git config", "git config adlc.x '<id>'\nn=$(git config adlc.x)\nadlc_forge_pr_view \"$n\"",
     "adlc_forge_pr_view", '"$n"'),
    ("git config, read only", "n=$(git config --get adlc.pr)\nadlc_forge_pr_comment \"$n\" "
     "--body hi", "adlc_forge_pr_comment", '"$n"'),
    ("the branch's name", "n=$(git rev-parse --abbrev-ref HEAD | tr -dc 0-9)\n"
     "adlc_forge_pr_checks \"$n\"", "adlc_forge_pr_checks", '"$n"'),
    ("another PR operation's output",
     "n=$(adlc_forge_pr_view '<prNumber>' --json body -q .body)\nadlc_forge_pr_edit \"$n\" "
     "--title x", "adlc_forge_pr_edit", '"$n"'),
    ("tied, then something else merged",
     "adlc_forge_pr_view '<prNumber>' --fields state\nn=$(cat x)\nadlc_forge_pr_merge \"$n\"",
     "adlc_forge_pr_merge", '"$n"'),
    ("a forge call piped into a filter",
     'pr=$(adlc_forge_pr_create --title "<short title>" | sed -n "s/^number=//p")\n'
     'adlc_forge_pr_view "$pr" --fields state', "adlc_forge_pr_view", '"$pr"'),
    ("a list whose arguments are not literal",
     'u=$(adlc_forge_pr_list --head "$(cat h.txt)")\nadlc_forge_pr_merge "$u"',
     "adlc_forge_pr_merge", '"$u"'),
    ("a list read in a loop", 'adlc_forge_pr_list --head x | while read -r n; do '
     'adlc_forge_pr_view "$n" --fields state; done', "adlc_forge_pr_view", '"$n"'),
    ("a forge call written twice",
     "n=$(adlc_forge_pr_create --title '<short title>')\nn=$(cat x)\nadlc_forge_pr_ready \"$n\"",
     "adlc_forge_pr_ready", '"$n"'),
    ("a forge call, then read into the name",
     "n=$(adlc_forge_pr_create --title '<short title>')\nread n < x\nadlc_forge_pr_ready \"$n\"",
     "adlc_forge_pr_ready", '"$n"'),
    ("a forge call, then printf -v",
     "n=$(adlc_forge_pr_create --title '<short title>')\nprintf -v n %s '<id>'\n"
     "adlc_forge_pr_ready \"$n\"", "adlc_forge_pr_ready", '"$n"'),
    ("a forge call, then an assigning default",
     "n=$(adlc_forge_pr_create --title '<short title>')\n: \"${n:=<id>}\"\n"
     "adlc_forge_pr_ready \"$n\"", "adlc_forge_pr_ready", '"$n"'),
    ("a forge call whose name is text elsewhere",
     "n=$(adlc_forge_pr_create --title '<short title>')\nprintf 'PR %s\\n' \"$n\"\n"
     "adlc_forge_pr_ready \"$n\"", "adlc_forge_pr_ready", '"$n"'),
    ("a forge call for another repository",
     "n=$(adlc_forge_pr_create -R o/r --title '<short title>')\nadlc_forge_pr_ready \"$n\"",
     "adlc_forge_pr_ready", '"$n"'),
    # Words after the PR argument.
    ("F1 f: an option the adapter does not consume",
     "adlc_forge_pr_view --state <id> --fields state", "adlc_forge_pr_view", "<id>"),
    ("a second positional", "adlc_forge_pr_view --fields state -- '<id>'",
     "adlc_forge_pr_view", "--"),
    ("a value after an option gh consumes but the table does not name",
     "adlc_forge_pr_merge '<prNumber>' --subject '<short title>'",
     "adlc_forge_pr_merge", "'<short title>'"),
    ("an unquoted expansion as an option's value",
     't=x\nadlc_forge_pr_edit "<prNumber>" --title $t', "adlc_forge_pr_edit", "$t"),
    ("field splitting", "opt='-R other/repo'\nadlc_forge_pr_edit '<prNumber>' $opt --title x",
     "adlc_forge_pr_edit", "$opt"),
    ("field splitting of the PR", "x='5 6'\nadlc_forge_pr_view $x --fields state",
     "adlc_forge_pr_view", "$x"),
    ("a placeholder split in a variable", "x='<prNumber> 5'\nadlc_forge_pr_view $x",
     "could become code", None),
    ("an option whose name holds a value", 'adlc_forge_pr_edit "<prNumber>" -"<short title>"',
     "adlc_forge_pr_edit", '-"<short title>"'),
    ("an option of checks before its PR", "adlc_forge_pr_checks --watch '<prNumber>'",
     "adlc_forge_pr_checks", "'<prNumber>'"),
    # No PR argument: gh would take the branch's own, from config the session writes.
    ("no PR argument", "adlc_forge_pr_view --fields state", "adlc_forge_pr_view",
     "no PR argument"),
    ("no PR argument to edit", "adlc_forge_pr_edit --title '<short title>'",
     "adlc_forge_pr_edit", "no PR argument"),
    ("no PR argument to merge", "adlc_forge_pr_merge --squash", "adlc_forge_pr_merge",
     "no PR argument"),
    # The repository, the directory, the names the adapter runs, the runner's own values.
    ("F1 g: -R", "adlc_forge_pr_edit -R other/repo '<prNumber>' --title x",
     "adlc_forge_pr_edit", "-R"),
    ("F1 g: --repo=", "adlc_forge_pr_edit --repo=other/repo '<prNumber>' --title x",
     "adlc_forge_pr_edit", "--repo=other/repo"),
    ("F1 g: -R joined", "adlc_forge_pr_edit -Rother/repo '<prNumber>' --title x",
     "adlc_forge_pr_edit", "-Rother/repo"),
    ("GH_REPO", "GH_REPO=o/r adlc_forge_pr_view '<prNumber>'", "GH_REPO", None),
    ("GH_REPO unset", "unset GH_REPO\nadlc_forge_pr_view '<prNumber>'", "GH_REPO", None),
    ("GH_REPO in a substitution", "x=$(GH_REPO=o/r adlc_forge_pr_view '<prNumber>')",
     "GH_REPO", None),
    ("PATH", "PATH=/tmp:$PATH adlc_forge_pr_view '<prNumber>'", "PATH", None),
    ("cd", "cd /tmp && adlc_forge_pr_view '<prNumber>'", "changes directory (cd)", None),
    ("redefining an exempt operation", "adlc_forge_pr_list() { printf '%s' \"$1\"; }\n"
     "n=$(adlc_forge_pr_list '<id>')\nadlc_forge_pr_view \"$n\"", "adlc_forge_pr_list", None),
    ("a function named after a command the adapter runs",
     "printf() { echo '<id>'; }\nn=$(adlc_forge_pr_create --title x)\nadlc_forge_pr_ready \"$n\"",
     "defines the function printf", None),
    ("gh as a function", "gh() { echo 5; }\nadlc_forge_pr_ready '<prNumber>'",
     "defines the function gh", None),
    ("an alias", "alias p=\"printf %s '<id>'\"\nn=$(p)\nadlc_forge_pr_view \"$n\"",
     "runs alias", None),
    ("unset -f", "unset -f printf\nadlc_forge_pr_ready '<prNumber>'", "runs unset", None),
    ("hash -p", "hash -p /tmp/x gh\nadlc_forge_pr_ready '<prNumber>'", "runs hash", None),
    ("ADLC_ARG_*", "ADLC_ARG_pr=5\nadlc_forge_pr_view '<prNumber>'", "ADLC_ARG", None),
    ("ADLC_ARG through a backslash",
     "n=$(printenv ADLC_ARG\\_title)\nadlc_forge_pr_view \"$n\" --fields state",
     "ADLC_ARG", None),
    ("ADLC_ARG in the PR word", "adlc_forge_pr_view \"$(printenv ADLC_ARG\\_title)\"",
     "ADLC_ARG", None),
    # F11: a PR operation reached where its argv is not words the check reads.
    ("F11: xargs", "echo <id> | xargs adlc_forge_pr_edit --title x",
     "adlc_forge_pr_edit", "xargs"),
    ("F11: eval", "eval adlc_forge_pr_edit '<prNumber>'", "adlc_forge_pr_edit", "eval"),
    ("F11: sh -c", "sh -c 'adlc_forge_pr_edit 5 --title x'", "adlc_forge_pr_edit", "sh -c"),
    ("F11: bash -c", 'bash -c "adlc_forge_pr_view 5"', "adlc_forge_pr_view", "sh -c"),
    ("F11: a variable", "f=adlc_forge_pr_edit\n$f <id> --title x", "adlc_forge_pr_edit",
     "a variable"),
]


@pytest.mark.parametrize("case,body,op,what", REFUSED, ids=[r[0] for r in REFUSED])
def test_req719_a_call_that_is_not_a_closed_shape_is_refused(case, body, op, what):
    """BR-13 as a closed set of shapes: every call of a PR operation is its one PR argument
    first (a marked placeholder, a marked variable, or `"$n"` set once from
    `$(adlc_forge_pr_create …)` or `$(adlc_forge_pr_list …)`), then literal options and their
    one-word values; anything else is unroutable, and the reason names the operation and the
    word (or what hides it). With the canonical root and source lines, as a fence has them."""
    code = fc.ROOT_LINE + "\n" + SOURCE_FORGE + "\n" + body
    with pytest.raises(fc.Unroutable) as caught:
        fc.plan(code, "probe/SKILL.md#1:00000000")
    reason = str(caught.value)
    assert op in reason and (what is None or what in reason), reason


#: The benign paths, each of which must route and hand nothing to the refusal.
ROUTED = [
    # Marked placeholders and marked variables, in each spelling a fence uses.
    'adlc_forge_pr_view "$prNumber" --json body -q .body 2>/dev/null',
    'tmp=$(mktemp)\nadlc_forge_pr_edit "$prNumber" --body-file "$tmp" --title "$FINAL_TITLE"',
    'adlc_forge_pr_ready "$prNumber"',
    'adlc_forge_pr_view "${prNumber}" --fields state',
    "adlc_forge_pr_checks '<prNumber>'",
    'adlc_forge_pr_view "<prNumber>" --json body -q .body',
    "adlc_forge_pr_view '<prNumber>' --fields state",
    'adlc_forge_pr_edit <prNumber> 2>/dev/null',
    'tmp=$(mktemp)\nadlc_forge_pr_edit "<prNumber>" --title "<short title>" --body-file "$tmp"',
    # An option's value is anything that stays one word.
    'adlc_forge_pr_edit "$prNumber" --title "<short title>" --body "<n>"',
    "adlc_forge_pr_edit <prNumber> --body-file <id>",
    # BR-14: a name set once from what adlc_forge_pr_create or adlc_forge_pr_list prints.
    "n=$(adlc_forge_pr_create --title '<short title>' --base main)\nadlc_forge_pr_ready \"$n\"",
    "n=$(adlc_forge_pr_create --title '<short title>')\necho \"created $n\"\n"
    "adlc_forge_pr_edit \"$n\" --title '<short title>'",
    "num=$(adlc_forge_pr_create --title '<short title>')\nprintf 'PR %s\\n' \"$num\"\n"
    'adlc_forge_pr_view "${num}" --fields state',
    "n=$(adlc_forge_pr_create --title '<short title>')\n"
    "if [ -n \"$n\" ]; then adlc_forge_pr_view \"$n\" --fields state; fi",
    "n=$(adlc_forge_pr_list --head feat/x --json number --jq '.[0].number')\n"
    'adlc_forge_pr_view "$n" --fields state',
]
SOURCE_FORGE = ('if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . '
                '"$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi')


@pytest.mark.parametrize("body", ROUTED)
def test_req719_a_closed_shape_routes(body):
    """BR-13, BR-14: the shapes route, with the canonical root and source lines."""
    code = fc.ROOT_LINE + "\n" + SOURCE_FORGE + "\n" + body
    fc.plan(code)
    assert fc.unmarked_pr_arguments(code) == [] and fc.pr_operation_problems(code) == []


def test_req719_an_unmarked_pr_argument_does_not_route(copy):
    """AC-11: a fence that passes an unmarked placeholder as the PR argument of
    `adlc_forge_pr_edit` is unrouted, and `fence_census.py --check` fails naming the fence and
    the placeholder. `/architect` Step 5, whose `$prnum` is read from the state file, routes
    only through DECLARED_UNTIED, and binds no PR value."""
    path = os.path.join(copy, "validate", "SKILL.md")
    with open(UNMARKED_FIXTURE, encoding="utf-8") as fh:
        extra = fh.read()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n" + extra)
    records = fc.census(copy, ea.load("claude", copy))
    fence = fc.fences(fc.view(copy, "validate/SKILL.md"), "validate/SKILL.md")[-1]
    bad = fc.unrouted(records)
    assert [r["id"] for r in bad] == [fence.id], bad
    assert "<n>" in bad[0]["reason"] and "adlc_forge_pr_edit" in bad[0]["reason"], bad[0]
    out = subprocess.run([sys.executable, "-I", os.path.join(copy, "tools", "adlc",
                                                             "fence_census.py"), "--check"],
                         cwd=copy, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True)
    assert out.returncode == 1, out.stderr
    named = [ln for ln in out.stderr.splitlines() if ln.startswith("unrouted: ")]
    assert named and all(fence.id in ln and "<n>" in ln for ln in named), out.stderr
    architect = next(r for r in records if r["id"].startswith("architect/SKILL.md#") and
                     "MAPPER_PATHS" in r["placeholders"])
    assert architect["route"] == "runner" and "tied" not in architect, architect
    assert architect["untied"] == fc.DECLARED_UNTIED[architect["id"]]
    code = fc.fences(fc.view(copy, "architect/SKILL.md"), "architect/SKILL.md")[
        int(architect["id"].split("#")[1].split(":")[0]) - 1].code
    assert ("adlc_forge_pr_view", '"$prnum"') in fc.unmarked_pr_arguments(code)


def test_req719_the_option_table_is_read_from_the_adapter():
    """F1 f: every PR operation `partials/forge.sh` defines has an entry, and each entry names
    a function there; `view` consumes only `--fields`, unless `--json`, `-q` or `--jq` without a
    `--fields` value hands its argv to `gh`; `checks` consumes nothing. An option the table does
    not name for an operation takes no value."""
    with open(os.path.join(TOOLKIT, "partials", "forge.sh"), encoding="utf-8") as fh:
        defined = set(re.findall(r"^(adlc_forge_pr_[a-z_]+)\(\)", fh.read(), re.M))
    assert set(fc.PR_OP_VALUE_OPTIONS) == {op for op in defined if fc.is_pr_operation(op)}
    assert fc._value_options("adlc_forge_pr_view", ["7", "--fields", "state"]) == {"--fields"}
    assert fc._value_options("adlc_forge_pr_view", ["7", "--json", "body", "-q", ".body"]) == \
        fc.PR_VIEW_RAW_OPTIONS
    assert fc._value_options("adlc_forge_pr_view",
                             ["7", "--json", "body", "--fields", "state"]) == {"--fields"}
    assert fc._value_options("adlc_forge_pr_checks", ["7"]) == frozenset()
    assert fc._value_options("adlc_forge_pr_new", ["7", "--title", "x"]) == frozenset()
    assert fc.unmarked_pr_arguments("adlc_forge_pr_new '<prNumber>' --title x") == \
        [("adlc_forge_pr_new", "x")]


def test_req719_declared_untied_is_one_fence_that_needs_it(records):
    """DECLARED_UNTIED holds exactly the architect footprint fence, whose id is still in the
    census, which routes only through the table: a PR operation in it takes `"$prnum"`, which
    is none of the shapes, the same code under any other id is refused, and its record and
    the goldens name the reason under `untied`."""
    assert list(fc.DECLARED_UNTIED) == ["architect/SKILL.md#2:587fb45d"]
    fid = "architect/SKILL.md#2:587fb45d"
    rec = next(r for r in records if r["id"] == fid)
    assert rec["route"] == "runner" and rec["untied"] == fc.DECLARED_UNTIED[fid]
    code = fc.fences(fc.view(TOOLKIT, "architect/SKILL.md"), "architect/SKILL.md")[1].code
    assert fc.unmarked_pr_arguments(code), "the exemption is no longer needed: drop it"
    with pytest.raises(fc.Unroutable, match="none of the shapes"):
        fc.plan(code)
    with pytest.raises(fc.Unroutable, match="none of the shapes"):
        fc.plan(code, "architect/SKILL.md#2:00000000")
    fc.plan(code, fid)
    for adapter in fc.exec_adapters(TOOLKIT):
        with open(os.path.join(TOOLKIT, fc.golden_path(adapter.name)), encoding="utf-8") as fh:
            golden = {r["id"]: r for r in json.load(fh)["fences"]}
        assert golden[fid]["untied"] == fc.DECLARED_UNTIED[fid], adapter.name
    assert [r["id"] for r in records if r.get("untied")] == [fid]


def test_req719_the_taint_flow_is_gone():
    """The check is a closed set of shapes, not a model of where values go: the flow
    machinery it replaced is not kept beside it."""
    for name in ("tainted_vars", "_flow", "_taint_in", "_feeder", "_Parser", "_parse"):
        assert not hasattr(fc, name), name
