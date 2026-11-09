"""The fence census: every fence an exec run can meet has a route (REQ-682 BR-1, BR-8, AC-2)."""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import exec_matcher as em  # noqa: E402
import exec_prompt as ep  # noqa: E402
import fence_census as fc  # noqa: E402
import recording_stubs as rs  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
FIXTURE = os.path.join(HERE, "fixtures", "exec-fence", "extra-fences.md")
ROUTES = ("direct", "runner", "engine", "excised")


@pytest.fixture(scope="module")
def records():
    return fc.census(TOOLKIT)


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
    """Benign path: the unmodified tree reports no unrouted fence."""
    assert fc.unrouted(records) == []


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


def test_direct_fences_admitted_statement_by_statement(records):
    """AC-2's positive half: a `direct` fence's statements are admitted over the rendered
    ExecPolicy, as written or as the exec notes tell the model to run it (LESSON-779)."""
    policy = fc.exec_policy(TOOLKIT)
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
    with open(os.path.join(TOOLKIT, fc.GOLDEN), encoding="utf-8") as fh:
        golden = fh.read()
    assert golden == fc.dumps(fc.golden_doc(records)), \
        "harness/claude/exec-fence-census.json is stale: run fence_census.py --write"
    assert not fc.GOLDEN.startswith("harness/claude/rendered/")
    assert fc.main(["--check"]) == 0


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
    bad = {r["id"].split(":")[0]: r for r in fc.unrouted(fc.census(copy))}
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
    with open(os.path.join(TOOLKIT, fc.GOLDEN), encoding="utf-8") as fh:
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
    rec = next(r for r in fc.census(TOOLKIT) if r["id"].startswith("proceed/SKILL.md#1:"))
    assert rec["route"] == "runner" and "flag" not in rec["placeholders"]
