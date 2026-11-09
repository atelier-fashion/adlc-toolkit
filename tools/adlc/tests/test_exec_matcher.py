"""exec_matcher: Claude's exec-scope matching, pinned to the REQ-682 probe rows (BR-2, BR-7)."""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_adapter as ea  # noqa: E402
import exec_matcher as em  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
BRANCH = "feat/REQ-901-thing"
TK = "/abs/tk"

#: Rows 1-15 of the architecture's evidence table: (row, allow, deny, command, admitted).
#: Rows 16-18 are Claude's path checks, which a command matcher does not model; BUG-265's
#: live rows `file-scope-write` and `file-scope-read` pin them.
PROBE_ROWS = [
    (1, ["Bash(touch p-plain:*)"], [], "touch p-plain", True),
    (2, ["Bash(touch p-plain:*)"], [], "touch p-plain; touch p-compound", False),
    (3, ["Bash(touch p-plain:*)"], [], "touch p-plain && touch p-and", False),
    (3, ["Bash(touch p-plain:*)"], [], "touch p-plain\ntouch p-newline", False),
    (4, ["Bash(touch p-plain:*)"], [], "X=1 touch p-plain-envprefix", False),
    (5, ["Bash(touch p-plain:*)"], [], "touch p-plain-sub-$(echo x)", False),
    (6, ["Bash(touch p-plain:*)"], [], "touch 'p-plain-q;touch p-quoted'", False),
    (7, ["Bash(touch p-plain:*)"], [], "touch p-plain-redir > f", False),
    (8, ["Bash(touch p-plain:*)"], [], "if [ -d . ]; then touch p-plain-if; fi", False),
    (9, ["Bash(. %s/:*)" % TK], [], ". %s/ok.sh" % TK, False),
    (10, ["Bash(. %s/:*)" % TK], [], ". %s/../evil.sh" % TK, False),
    (10, ["Bash(. %s/:*)" % TK], [], ". %s/fn.sh && pfn" % TK, False),
    (11, ["Bash(%s/runner:*)" % TK], [], "%s/runner a" % TK, True),
    (12, ["Bash(%s/runner:*)" % TK], [], "%s/runner-evil" % TK, False),
    (13, ["Bash(%s/runner:*)" % TK], [], "Y=1 %s/runner env" % TK, False),
    (14, ["Bash(ADLC_TOOLKIT_ROOT=:*)", "Bash(PROBE_ENV=:*)"], [],
     "ADLC_TOOLKIT_ROOT=x touch p-env", False),
    (14, ["Bash(ADLC_TOOLKIT_ROOT=:*)", "Bash(PROBE_ENV=:*)"], [], "PROBE_ENV=1 touch p-env",
     False),
    (15, ["Bash(PROBE_ENV=:*)", "Bash(touch:*)"], ["Bash(touch p-denied:*)"],
     "PROBE_ENV=1 touch p-denied", False),
]


@pytest.fixture(scope="module")
def adapter():
    return ea.load("claude", TOOLKIT)


@pytest.fixture(scope="module")
def policy(adapter):
    allow, deny = adapter.tiers(BRANCH, write_roots=["/abs/wc"], read_roots=[TK])
    return {"allow": allow, "deny": deny}


@pytest.mark.parametrize("row,allow,deny,cmd,expected", PROBE_ROWS)
def test_probe_rows_verdicts(row, allow, deny, cmd, expected):
    assert em.admits({"allow": allow, "deny": deny}, cmd) is expected, (row, em.explain(
        {"allow": allow, "deny": deny}, cmd))


def test_probe_rows_14_15_env_prefix():
    """Row 14: an env-prefixed command is not admitted by a bare allow on the prefix. Row 15:
    a deny matches through the prefix, so the refusal is the deny's."""
    allow = {"allow": ["Bash(ADLC_TOOLKIT_ROOT=:*)", "Bash(touch:*)"], "deny": []}
    assert em.explain(allow, "ADLC_TOOLKIT_ROOT=x touch a")[1] == em.REFUSE_ENV
    denied = {"allow": ["Bash(PROBE_ENV=:*)"], "deny": ["Bash(touch p-denied:*)"]}
    assert em.deny_hits(denied, "PROBE_ENV=1 touch p-denied") == [
        ("PROBE_ENV=1 touch p-denied", "Bash(touch p-denied:*)")]


def test_statements_split_outside_quotes_only():
    assert [s.text for s in em.statements("a; b && c || d | e\nf")] == list("abcdef")
    assert [s.text for s in em.statements("touch 'x;y' \"p && q\"")] == ["touch 'x;y' \"p && q\""]
    assert [s.text for s in em.statements("if [ -f a ]; then b; else c; fi")] == [
        "[ -f a ]", "b", "c"]
    assert [s.text for s in em.statements("a \\\n  b")] == ["a b"]


@pytest.mark.parametrize("cmd,why", [
    (". x.sh", em.REFUSE_SOURCE), ("source x.sh", em.REFUSE_SOURCE),
    ("echo `id`", em.REFUSE_NESTED), ('echo "$(id)"', em.REFUSE_NESTED),
    ("echo a > f", em.REFUSE_REDIRECT), ("echo a >> f", em.REFUSE_REDIRECT),
    ("cat < f", em.REFUSE_REDIRECT), ("A=1 echo", em.REFUSE_ENV),
    ("cat <<EOF", em.REFUSE_UNMEASURED), ("( echo a )", em.REFUSE_UNMEASURED),
    ("echo $HOME", em.REFUSE_UNMEASURED), ("for x in a; do", em.REFUSE_UNMEASURED),
    ("# a comment", em.REFUSE_UNMEASURED), ("echo 'open", em.REFUSE_UNMEASURED),
])
def test_refusals(cmd, why):
    assert em.refusal(cmd) == why


@pytest.mark.parametrize("cmd", ["ls 2>/dev/null", "ls >/dev/null", "ls > /dev/null",
                                 "ls &>/dev/null", "grep -e 'a>b' f", "echo 'it''s $5'"])
def test_benign_statements_have_no_refusal(cmd):
    assert em.refusal(cmd) is None


def test_no_deny_tier_spelling_admitted_in_any_form(adapter, policy):
    """BR-2, AC-3: every deny-tier spelling, plain, env-prefixed, under `git -C` and as the
    second statement of a compound command, is refused by the rendered exec policy."""
    spellings = em.deny_tier_spellings(adapter.adapter, TOOLKIT)
    assert len(spellings) > 30
    checked = 0
    for spelling in spellings:
        for shape, form in em.wrapped_forms(spelling):
            assert not em.admits(policy, form), (shape, form, em.explain(policy, form))
            checked += 1
    assert checked > len(spellings) * 8


def test_policy_fixture_with_opener_or_merge_allow_fails(adapter, policy):
    """AC-3: each of these added to the policy is found by the policy check."""
    spellings = em.deny_tier_spellings(adapter.adapter, TOOLKIT)
    # The rendered policy itself is sound, so each problem below is the added entry's.
    assert em.policy_problems(policy, spellings) == []
    for bad in ("Bash(adlc_forge_pr_merge:*)", "Bash(. :*)", "Bash(source:*)", "Bash(if:*)",
                "Bash(sh:*)", "Bash(eval:*)", "Bash(python3:*)", "Bash(git push origin:*)"):
        widened = {"allow": policy["allow"] + [bad], "deny": policy["deny"]}
        assert em.policy_problems(widened, spellings), bad
    # A deny-tier spelling the deny tier itself names stays refused under a wide allow.
    assert not em.admits({"allow": policy["allow"] + ["Bash(gh pr:*)"],
                          "deny": policy["deny"]}, "gh pr merge 1")


def test_current_exec_allows_still_admitted(policy):
    """Benign path: what the pipeline runs today stays admitted."""
    for cmd in ("git status", "git status --short", "git push -u origin %s" % BRANCH,
                "git push origin %s" % BRANCH, "git push", "ls", "ls -t .adlc/knowledge/lessons",
                "git log --oneline -3 2>/dev/null", "git branch --show-current"):
        assert em.admits(policy, cmd), (cmd, em.explain(policy, cmd))
    for cmd in ("git push -u origin %s --force" % BRANCH, "git push -u origin %s main" % BRANCH,
                "git push origin main"):
        assert not em.admits(policy, cmd), cmd


def test_wildcard_rule_text():
    rule = em.Rule("Bash(git -C * push --force:*)")
    assert rule.matches("git -C /x push --force origin main")
    assert not rule.matches("git -C /x push origin main")
    exact = em.Rule("Bash(git push origin +*)")
    assert exact.matches("git push origin +HEAD:main") and not exact.matches("git push origin a")


def test_deny_hits_see_through_wrappers(policy):
    for cmd in ("git push --force", "X=1 git push --force", "git -C /wc push --force",
                "git status; gh pr merge 3", "A=1 B=2 rm -rf /tmp/x"):
        assert em.deny_hits(policy, cmd), cmd
    assert em.deny_hits(policy, "git status && ls") == []
