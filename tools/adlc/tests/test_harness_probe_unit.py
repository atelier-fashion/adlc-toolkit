"""REQ-664: the pure half of `adlc harness probe` — data, plan and verdict rules.

No harness, no subprocess: these pin the rules every end-to-end case relies on,
so a regression names the rule rather than a scenario.
"""

import os
import string

import pytest

import harness_probe as hp
from harness_probe import FAIL, NA, PASS, UNKNOWN, Obs, Verdict


# --- catalogue and coverage (BR-6) -------------------------------------------

def test_catalogue_and_coverage():
    ids = [p.id for p in hp.CATALOGUE]
    assert ids == ["git-write-main", "git-write-worktree", "ask-tier-deny",
                   "skill-activation", "shell-timeout", "trust-then-headless",
                   "session-start-context", "stdin-prompt", "fence-vs-allowlist",
                   "transcript-locate", "arg-substitution"]
    assert set(hp.RUN_ORDER) == set(ids)
    assert hp.RUN_ORDER[0] == "trust-then-headless" and hp.RUN_ORDER[-1] == "transcript-locate"
    # Twelve §6 items, 6.1 split in two.
    assert sorted(hp.COVERAGE, key=lambda k: (int(k.split(".")[1].rstrip("ab")), k)) == [
        "6.1a", "6.1b", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9",
        "6.10", "6.11", "6.12"]
    items = {k.rstrip("ab") for k in hp.COVERAGE}
    assert items == {"6.%d" % n for n in range(1, 13)}
    assert hp.COVERAGE["6.1a"] == {"probes": ["git-write-main"], "note": "headless only"}
    assert hp.COVERAGE["6.3"]["probes"] == ["ask-tier-deny", "git-write-main"]
    for key in ("6.2", "6.5", "6.7"):
        assert hp.COVERAGE[key]["status"] == "not-probed" and hp.COVERAGE[key]["reason"]
    named = {pid for entry in hp.COVERAGE.values() for pid in entry.get("probes", [])}
    assert named == set(ids), "every probe answers some §6 item and nothing else"
    # Benign path: every known id is accepted by --only; an unknown one is not.
    for pid in ids:
        hp.plan("claude", [pid])
    with pytest.raises(ValueError):
        hp.plan("claude", ["no-such-probe"])


def test_applicability():
    assert hp.BY_ID["skill-activation"].harnesses == ("gemini",)
    assert hp.BY_ID["arg-substitution"].harnesses == ("claude",)
    for pid in ("git-write-main", "ask-tier-deny", "fence-vs-allowlist", "transcript-locate"):
        assert hp.BY_ID[pid].harnesses == hp.NAMES
    assert hp.BY_ID["git-write-worktree"].variants("codex") == (
        "root-is-worktree", "writable-roots-repo")
    assert hp.BY_ID["git-write-worktree"].variants("claude") == ("-",)
    assert hp.BY_ID["transcript-locate"].variants("claude") == ()


# --- nonce (BR-5, BR-16, AC-17) ----------------------------------------------

def test_nonce_shape():
    seen = set()
    allowed = set(string.ascii_lowercase + string.digits)
    for _ in range(5000):
        n = hp.new_nonce()
        assert len(n) == 8 and set(n) <= allowed
        assert n != n[::-1]
        seen.add(n)
    assert len(seen) > 4990


def test_bare_nonce_echo_never_counts():
    obs = Obs(message="the code is abcd1234", nonce="abcd1234")
    assert not obs.nonce_found()
    obs.message = "4321dcba"
    assert obs.nonce_found()


# --- plan (BR-4, BR-12, ADR-8) -----------------------------------------------

def test_plan_counts():
    full = hp.plan("claude")
    assert [lc.lid for lc in full.launches] == ["l%02d" % i for i in range(1, full.count + 1)]
    assert full.launches[0].probe == "trust-then-headless"
    assert len(full.launches_of("ask-tier-deny")) == 7
    assert full.launches_of("transcript-locate") == []
    assert full.launches_of("skill-activation") == []          # n/a on claude
    assert full.count == 18                                      # arg-substitution
    assert hp.plan("codex").count == 18                          # two worktree variants
    assert hp.plan("gemini").count == 18                         # skill-activation
    assert hp.plan("copilot").count == 17 and hp.plan("cursor").count == 17
    # --only on a trust-file harness launches trust-then-headless implicitly, first.
    only = hp.plan("codex", ["shell-timeout"])
    assert [lc.probe for lc in only.launches] == ["trust-then-headless", "shell-timeout"]
    assert only.implicit == ("trust-then-headless",)
    # ...but not on a flag harness, and not for a probe that launches nothing.
    assert [lc.probe for lc in hp.plan("cursor", ["shell-timeout"]).launches] == ["shell-timeout"]
    assert hp.plan("codex", ["transcript-locate"]).count == 0
    assert hp.shell_timeout_selected(only)
    assert not hp.shell_timeout_selected(hp.plan("claude", ["git-write-main"]))


# --- combinators (BR-5) ------------------------------------------------------

def test_combinators():
    p, f, u, n = Verdict(PASS), Verdict(FAIL), Verdict(UNKNOWN, "timeout"), Verdict(NA, "why")
    assert hp.conjunction([p, p]).status == PASS
    assert hp.conjunction([p, f]).status == FAIL
    assert hp.conjunction([u, f]).status == FAIL
    assert hp.conjunction([p, u]).as_dict() == {"status": UNKNOWN, "reason": "timeout"}
    assert hp.conjunction([p, n]).status == PASS                 # copilot: hooks alone
    assert hp.conjunction([n, n]).as_dict() == {"status": NA, "reason": "why"}
    assert hp.disjunction([f, p]).status == PASS
    assert hp.disjunction([f, f]).status == FAIL
    assert hp.disjunction([f, u]).as_dict() == {"status": UNKNOWN, "reason": "timeout"}
    assert hp.disjunction([n, f]).status == FAIL
    assert hp.disjunction([n, n]).as_dict() == {"status": NA, "reason": "why"}


def test_plain_and_exit_exempt_rules():
    assert hp.decide_plain(Obs(exit_code=0), True).status == PASS
    assert hp.decide_plain(Obs(exit_code=0), False).status == FAIL
    assert hp.decide_plain(Obs(exit_code=3), True).reason == "binary-exit-3"
    assert hp.decide_plain(Obs(timed_out=True, exit_code=None), True).reason == "timeout"
    assert hp.decide_plain(Obs(refused="x"), True).reason == "launch-refused"
    assert hp.decide_plain(Obs(stale=True), True).reason == hp.STALE
    assert hp.decide_plain(Obs(message_state="none"), True, needs_message=True).reason == hp.NO_MESSAGE
    # shell-timeout: sentinel present passes even on a non-zero session exit.
    st = lambda **kw: hp.decide_exit_exempt(Obs(**kw), "effect", PASS)  # noqa: E731
    assert st(exit_code=1, effects={"effect": True}).status == PASS
    assert st(nonce="abcd1234", message="4321dcba").status == FAIL
    assert st(exit_code=3, message_state="absent").reason == hp.ASK_NOT_REACHED
    assert st(timed_out=True).reason == "timeout"
    assert st(message_state="none", effects={"effect": True}).reason == hp.NO_MESSAGE


# --- ask-tier-deny (BR-5, BR-17, AC-6, AC-16) --------------------------------

def _atd(effects, nonce=True, witness=None, overrides=None):
    """Seven observations. ``effects`` names the launches whose command ran."""
    out = {}
    for name in hp.ATD_VARIANTS + hp.ATD_CONTROLS:
        obs = Obs(nonce="abcd1234", message="4321dcba" if nonce else "no")
        obs.effects = {"effect": name in effects,
                       "witness": (name in hp.ATD_VARIANTS) if witness is None else witness}
        out[name] = obs
    for name, kw in (overrides or {}).items():
        for k, v in kw.items():
            setattr(out[name], k, v)
    return out


def test_ask_tier_deny_gating():
    # perform: the allow is necessary (baseline did nothing) and the deny held.
    probe, subs = hp.decide_ask_tier_deny(_atd({"allow-only", "allow-only-git-c"}))
    assert probe.status == PASS
    assert subs["lone-deny"].as_dict() == {"status": NA, "reason": hp.LONE_DENY_NA}
    assert subs["deny-under-allow"].status == PASS and subs["wrapped-allow"].status == PASS
    assert subs["baseline"].status == FAIL and subs["allow-only"].status == PASS
    # refuse: the allowed control did not run, so the held deny proves nothing.
    probe, subs = hp.decide_ask_tier_deny(_atd(set()))
    assert probe.as_dict() == {"status": UNKNOWN, "reason":
                               "precondition-unmet: allow-only control did not run the command"}
    assert subs["wrapped-allow"].reason == \
        "precondition-unmet: allow-only-git-c control did not run the command"
    # refuse-silent: the control never reached the ask -> the probe says so.
    probe, subs = hp.decide_ask_tier_deny(_atd(set(), nonce=False))
    assert probe.as_dict() == {"status": UNKNOWN, "reason": hp.ASK_NOT_REACHED}
    assert all(subs[c].reason == hp.ASK_NOT_REACHED for c in hp.ATD_CONTROLS)
    # runs-all: the allow was not required; lone-deny is decided and fails.
    probe, subs = hp.decide_ask_tier_deny(_atd(set(hp.ATD_VARIANTS + hp.ATD_CONTROLS)))
    assert probe.status != PASS
    assert subs["lone-deny"].status == FAIL
    assert subs["deny-under-allow"].reason == \
        "precondition-unmet: allow not required (baseline ran the command)"
    assert subs["wrapped-allow"].reason == \
        "precondition-unmet: allow not required (baseline-git-c ran the command)"
    # no-witness: the config may not have loaded, so no pass.
    probe, subs = hp.decide_ask_tier_deny(_atd({"allow-only", "allow-only-git-c"}, witness=False))
    assert subs["deny-under-allow"].reason == hp.WITNESS_ABSENT
    assert probe.status == UNKNOWN
    # a deny that did not hold is fail.
    probe, subs = hp.decide_ask_tier_deny(
        _atd({"allow-only", "allow-only-git-c", "deny-under-allow", "wrapped-allow"}))
    assert subs["deny-under-allow"].status == FAIL and probe.status == FAIL
    # gemini abort: exit 53 on the deny, no final message -> never pass.
    probe, subs = hp.decide_ask_tier_deny(_atd(
        {"allow-only", "allow-only-git-c"},
        overrides={v: {"exit_code": 53, "message": "", "message_state": "absent"}
                   for v in hp.ATD_VARIANTS}))
    assert probe.as_dict() == {"status": UNKNOWN, "reason": hp.ASK_NOT_REACHED}


def test_ask_tier_deny_variant_keys():
    _probe, subs = hp.decide_ask_tier_deny(_atd(set()))
    assert set(subs) == set(hp.ATD_VARIANTS + hp.ATD_CONTROLS)
    assert "deny-under-allow" in subs and "wrapped-allow" in subs
    assert not any("env-prefix" in k or "shell-opener" in k for k in subs)


# --- rendering ---------------------------------------------------------------

def test_render_rules_per_harness():
    r, e = hp.Rule("git commit"), hp.Rule("touch /x/y", exact=True)
    assert hp.render_rule("claude", r) == "Bash(git commit:*)"
    assert hp.render_rule("claude", e) == "Bash(touch /x/y)"
    assert hp.render_rule("copilot", r) == "shell(git commit:*)"
    assert hp.render_rule("gemini", r) == "run_shell_command(git commit)"
    assert hp.render_rule("cursor", r) == "Shell(git commit)"
    rules = hp.render_codex_rules([r], [hp.Rule("git push --force origin HEAD:refs/heads/x")])
    assert 'prefix_rule(pattern = ["git", "commit"], decision = "allow")' in rules
    assert '"--force"' in rules and 'decision = "forbidden"' in rules
    policy = hp.render_gemini_policy([e])
    assert 'commandPrefix = "touch /x/y"' in policy and 'decision = "deny"' in policy
    assert hp.FENCE_FIRST_TOKEN == 'ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}";'


# --- redaction, ~ rewrite, tails (BR-9) --------------------------------------

def test_redaction_and_home():
    home = "/Users/someone"
    text = ("key sk-" + "a" * 24 + " and AKIA" + "B" * 16 + " ghp_" + "c" * 36 +
            " Bearer " + "d" * 24 + "\nMY_API_KEY=secret123 path /Users/someone/x")
    out = hp.scrub(text, home)
    assert "sk-" not in out and "AKIA" not in out and "ghp_" not in out
    assert "secret123" not in out and "Bearer d" not in out
    assert "/Users/someone" not in out and "~/x" in out
    assert out.count(hp.REDACTED) == 5
    assert hp.redact("nothing to see") == "nothing to see"      # benign path


def test_tail_cap():
    assert hp.tail("x" * 10, 4) == "xxxx"
    assert len(hp.tail("é" * 5000).encode()) <= hp.EVIDENCE_CAP
    assert hp.tail("short") == "short"


# --- --only merge (BR-9, AC-10) ----------------------------------------------

def _existing(version, tool="t1"):
    return {"harness_version": version, "probe_tool_version": tool,
            "probes": {p.id: {"status": PASS, "ran_at": "2026-10-01T00:00:00Z"}
                       for p in hp.CATALOGUE}}


def test_merge_only():
    fresh = {"shell-timeout": {"status": FAIL, "ran_at": "2026-10-29T00:00:00Z"}}
    probes, summary = hp.merge_only(_existing("1.0"), fresh, ["shell-timeout"], "1.0", "t1")
    assert probes["shell-timeout"]["status"] == FAIL
    assert probes["git-write-main"] == {"status": PASS, "ran_at": "2026-10-01T00:00:00Z"}
    assert summary == "kept 10 prior entries"
    probes, summary = hp.merge_only(_existing("1.0"), fresh, ["shell-timeout"], "1.1", "t1")
    assert probes["git-write-main"]["status"] == UNKNOWN
    assert probes["git-write-main"]["reason"] == "not-run-this-version"
    assert summary == "dropped 10: version changed from 1.0 to 1.1"
    probes, _ = hp.merge_only(_existing("1.0", tool="t0"), fresh, ["shell-timeout"], "1.0", "t1")
    assert probes["git-write-main"]["reason"] == "not-run-this-version"
    assert list(probes) == [p.id for p in hp.CATALOGUE]
