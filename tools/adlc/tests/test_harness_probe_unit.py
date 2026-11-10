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
    assert hp.BY_ID["skill-activation"].harnesses == ("gemini", "antigravity")
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
    assert full.count == 31                                      # arg-substitution, +13 REQ-707
    assert hp.plan("codex").count == 31                          # two worktree variants
    assert hp.plan("gemini").count == 31                         # skill-activation
    assert hp.plan("copilot").count == 30 and hp.plan("cursor").count == 30
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
    # Email addresses go too (scrub only; redact stays intake.sh's chain).
    mail = hp.scrub("context: The user's email address is someone@example.co.uk.", home)
    assert "someone@" not in mail and hp.REDACTED_EMAIL in mail
    assert hp.scrub("adlc-probe@localhost", home) == "adlc-probe@localhost"


def test_scrub_takes_the_login_name_and_account_ids():
    home = "/Users/somelogin"
    listing = "drwxr-xr-x@ 2 somelogin  staff  64 Oct 31 08:44 /Users/somelogin/x"
    out = hp.scrub(listing, home)
    assert "somelogin" not in out and hp.REDACTED_LOGIN in out and out.endswith("~/x")
    # Part of a longer word names no one, and a generic last component is not a login.
    assert hp.scrub("somelogin-tools", home) == "somelogin-tools"
    assert hp.scrub("the home directory", "/tmp/x/home") == "the home directory"
    record = '{\\"creator_user_id\\":\\"user-abc\\",\\"creator_account_id\\":\\"9c1b\\"}'
    scrubbed = hp.scrub(record, home)
    assert "user-abc" not in scrubbed and "9c1b" not in scrubbed
    assert hp.scrub('{"creator_user_id": "user-abc"}', home) == \
        '{"creator_user_id": "%s"}' % hp.REDACTED


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


# --- REQ-707: the runner-prefix variant of fence-vs-allowlist ------------------

def _runner(admitted=(), witness=True, nonce=True, runner=(), on_record=None, denied=False):
    """Thirteen observations. ``admitted`` names the launches whose effect appeared;
    ``runner`` the launches where the stub ran; ``on_record`` (default: every launch)
    the launches whose asked line the harness recorded."""
    out = {}
    for name in hp.RUNNER_LAUNCHES:
        obs = Obs(nonce="abcd1234", message="4321dcba" if nonce else "no", denied=denied)
        ran = name in runner or (name in admitted and hp.runner_effect(name) == "runner")
        obs.effects = {"effect": name in admitted, "witness": witness, "runner": ran,
                       "on_record": True if on_record is None else name in on_record,
                       "denied_here": denied}
        out[name] = obs
    return out


def _engine(tmp_path, harness="claude"):
    eng = hp.Engine.__new__(hp.Engine)
    eng.profile, eng.h = hp.PROFILES[harness], harness
    eng.run_dir = str(tmp_path / "run")
    eng.repo = os.path.join(eng.run_dir, "repo")
    eng.outside, eng.home = "", str(tmp_path / "home")
    return eng


def test_runner_launch_plan():
    for h in hp.NAMES:
        p = hp.plan(h, ["fence-vs-allowlist"])
        fence = [lc.variant for lc in p.launches_of("fence-vs-allowlist")]
        assert fence == list(hp.FENCE_VARIANTS + hp.RUNNER_LAUNCHES)
        assert len(fence) == 16
    assert hp.RUNNER_LAUNCHES[:2] == ("runner-positive", "runner-baseline")
    assert len(hp.RUNNER_CONTROLS) == 11


def test_decide_runner_prefix_rows():
    controls = set(hp.RUNNER_CONTROLS)
    # pass, boundary measured: positive admitted, baseline and every control refused.
    v, subs = hp.decide_runner_prefix(_runner({"runner-positive"}))
    assert (v.status, v.evidence["boundary"], v.evidence["admitted"]) == (PASS, "measured", [])
    assert subs["runner-positive"].status == PASS
    assert all(subs[c].status == PASS and subs[c].reason == "refused" for c in controls)
    # pass, boundary none: the baseline ran the stub; the controls are recorded only.
    v, subs = hp.decide_runner_prefix(_runner({"runner-positive", "runner-baseline"} | controls))
    assert (v.status, v.evidence["boundary"]) == (PASS, "none")
    assert subs["runner-baseline"].status == FAIL
    assert sorted(v.evidence["admitted"]) == sorted(controls)
    # fail: the positive half was refused.
    v, _ = hp.decide_runner_prefix(_runner(set()))
    assert v.status == FAIL and v.reason.startswith("positive-refused")
    # fail: one control admitted, named.
    v, subs = hp.decide_runner_prefix(_runner({"runner-positive", "runner-pipe"}))
    assert (v.status, v.evidence["admitted"]) == (FAIL, ["runner-pipe"])
    assert subs["runner-pipe"].status == FAIL and "runner-pipe" in v.reason
    # unknown: a baseline that is unknown is never a pass.
    obs = _runner({"runner-positive"})
    obs["runner-baseline"].timed_out = True
    v, _ = hp.decide_runner_prefix(obs)
    assert v.status == UNKNOWN
    # unknown: a control unknown with none admitted.
    obs = _runner({"runner-positive"})
    obs["runner-or"].effects["witness"] = False
    v, _ = hp.decide_runner_prefix(obs)
    assert v.status == UNKNOWN and v.reason.startswith("runner-or:")
    # unknown: a launch that never ran.
    obs = _runner({"runner-positive"})
    del obs["runner-newline"]
    assert hp.decide_runner_prefix(obs)[0].status == UNKNOWN


def test_runner_launch_reading():
    ok = _runner({"runner-positive", "runner-semicolon"})
    assert hp.read_runner_launch(ok["runner-semicolon"]) == (hp.ADMITTED, None)
    assert hp.read_runner_launch(ok["runner-and"]) == (hp.REFUSED, None)
    # REQ-664's reasons survive: no witness, no nonce.
    assert hp.read_runner_launch(_runner(witness=False)["runner-and"]) == (
        UNKNOWN, hp.WITNESS_ABSENT)
    assert hp.read_runner_launch(_runner(nonce=False)["runner-and"])[0] == UNKNOWN
    # A model that tidied the line: the runner ran, nothing on record.
    split = _runner({"runner-positive"}, runner={"runner-semicolon"}, on_record=())
    assert hp.read_runner_launch(split["runner-semicolon"]) == (UNKNOWN, hp.ASK_SPLIT)
    # A model that never ran it: nothing ran, nothing on record, no refusal on stderr.
    never = _runner(on_record=())
    assert hp.read_runner_launch(never["runner-and"]) == (UNKNOWN, hp.NOT_ATTEMPTED)
    assert hp.read_runner_launch(never["runner-positive"]) == (UNKNOWN, hp.NOT_ATTEMPTED)
    # A refusal on stderr that names the stub, with nothing run, is evidence of submission.
    assert hp.read_runner_launch(_runner(on_record=(), denied=True)["runner-and"]) == (
        hp.REFUSED, None)
    # One that does not name it (a look-around refused) is not.
    other = _runner(on_record=())
    other["runner-and"].denied = True
    assert hp.read_runner_launch(other["runner-and"]) == (UNKNOWN, hp.NOT_ATTEMPTED)


def test_ask_split_downgrades_only():
    # Every split or unattempted reading makes the variant unknown, never a pass.
    split = _runner({"runner-positive"}, runner=set(hp.RUNNER_CONTROLS),
                    on_record={"runner-positive", "runner-baseline"})
    v, subs = hp.decide_runner_prefix(split)
    assert v.status == UNKNOWN and hp.ASK_SPLIT in v.reason
    assert all(subs[c].status == UNKNOWN for c in hp.RUNNER_CONTROLS)
    # Benign path: on record, the same observations read refused and the variant passes.
    v, _ = hp.decide_runner_prefix(_runner({"runner-positive"},
                                           runner=set(hp.RUNNER_CONTROLS)))
    assert v.status == PASS
    # The rule never turns an admitted launch into anything else.
    adm = _runner({"runner-positive", "runner-subst"}, on_record=())
    assert hp.read_runner_launch(adm["runner-subst"])[0] == hp.ADMITTED


def test_runner_prefix_outside_disjunction():
    eng = hp.Engine.__new__(hp.Engine)
    eng.emit = lambda *a, **k: None
    probe = hp.BY_ID["fence-vs-allowlist"]
    for fence_effects, runner_admitted in (
            (set(), {"runner-positive"}), ({"broad-sh"}, set()),
            ({"broad-sh"}, {"runner-positive", "runner-semicolon"})):
        obs_map = _runner(runner_admitted)
        for name in hp.FENCE_VARIANTS:
            obs_map[name] = Obs(nonce="abcd1234", message="4321dcba",
                                effects={"effect": name in fence_effects})
        entry = eng._decide_fence(probe, obs_map)
        expected = hp.disjunction([hp.decide_plain(obs_map[n], n in fence_effects)
                                   for n in hp.FENCE_VARIANTS]).status
        assert entry["status"] == expected
        assert set(entry["sub_results"]) == set(hp.FENCE_VARIANTS + hp.RUNNER_LAUNCHES) | {
            hp.RUNNER_PREFIX}


def test_runner_allow_set_has_one_stub_rule(tmp_path):
    eng = _engine(tmp_path)
    for variant in hp.RUNNER_LAUNCHES:
        spec = eng._prepare_runner(hp.Launch("l01", "fence-vs-allowlist", variant), "abcd1234")
        stub = spec.paths["stub"]
        naming = [r for r in spec.allow if stub in r.text]
        expected = [] if variant == hp.RUNNER_BASELINE else [hp.Rule(stub)]
        assert naming == expected, variant
        assert not any(r.text.startswith(stub + hp.TAIL_SUFFIX) for r in spec.allow)
        assert hp.Rule("touch %s" % spec.paths["witness"], exact=True) in spec.allow
        for r in spec.allow:
            first = r.text.split()[0]
            assert first not in ("if", "[", ".", "source", "sh", "bash", "eval")
            assert "=" not in first
        assert spec.prompt.startswith("Run `touch ") and "```sh\n%s\n```" % spec.paths[
            "asked"] in spec.prompt
        assert set(spec.absent) == {spec.paths[k] for k in ("runner", "tail", "redirect",
                                                            "witness")}


def test_plain_stub_path_is_accepted(tmp_path):
    spec = _engine(tmp_path)._prepare_runner(
        hp.Launch("l01", "fence-vs-allowlist", "runner-positive"), "abcd1234")
    stub = spec.paths["stub"]
    assert hp._SAFE_PATH.match(stub) and os.path.isabs(stub)
    assert not stub.startswith(os.path.join(str(tmp_path), "run", "repo"))
    eng = _engine(tmp_path)
    eng.run_dir = str(tmp_path / "a run")
    with pytest.raises(hp.ProbeError, match="stub runner path"):
        eng._prepare_runner(hp.Launch("l01", "fence-vs-allowlist", "runner-positive"), "x")


def test_runner_allow_uses_profile_spelling():
    stub = "/tmp/adlc-probe-x/tk/fence-run"
    for h in hp.NAMES:
        if h == "codex":
            assert '["%s"]' % stub in hp.render_codex_rules([hp.Rule(stub)], [])
            continue
        assert hp.render_rule(h, hp.Rule(stub)) == hp.render_rule(
            h, hp.Rule("ls")).replace("ls", stub)


def test_stub_is_posix_and_reads_no_env(tmp_path):
    import shutil
    import subprocess
    sent, tail_sent = tmp_path / "runner", tmp_path / "tail"
    stub, tail = tmp_path / "fence-run", tmp_path / "fence-run-x"
    stub.write_text(hp.runner_stub_body(str(sent)))
    tail.write_text(hp.tail_stub_body(str(tail_sent)))
    for body in (stub.read_text(), tail.read_text()):
        assert "$HOME" not in body and "ADLC" not in body
    for shell in ("sh", "bash", "zsh", "dash"):
        if not shutil.which(shell):
            continue
        for f in (sent, tail_sent):
            if f.exists():
                f.unlink()
        clean = {k: v for k, v in os.environ.items() if k != "X"}
        env = dict(clean, X="1")
        assert subprocess.run([shell, str(stub), "run", "a b"], env=env).returncode == 0
        assert subprocess.run([shell, str(stub), "fail"], env=clean).returncode == 1
        assert subprocess.run([shell, str(tail), "q"], env=clean).returncode == 0
        lines = sent.read_text().splitlines()
        assert lines == [str(stub), "run", "a b", "X=1", str(stub), "fail", "X=unset"], shell
        assert tail_sent.read_text().splitlines() == [str(tail), "q"]


def test_runner_evidence_names_what_ran(tmp_path):
    import json
    eng = _engine(tmp_path)
    lc = hp.Launch("l01", "fence-vs-allowlist", "runner-semicolon")
    spec = eng._prepare_runner(lc, "abcd1234")
    os.makedirs(os.path.dirname(spec.paths["runner"]), exist_ok=True)
    with open(spec.paths["runner"], "w") as fh:
        fh.write("%s\nrun\nprobe\nX=unset\n" % spec.paths["stub"])
    open(spec.paths["witness"], "w").close()
    asked = spec.paths["asked"]

    def observe(stdout, stderr="", denied=False):
        res = hp.LaunchResult([], eng.repo, 0, False, None, 1.0, stdout, stderr, None, 0.0)
        obs, notes = Obs(nonce="abcd1234", message="4321dcba", denied=denied), []
        eng._observe_runner(lc, spec, res, obs, notes)
        return obs, notes

    # A denial record naming the command is the harness's own record.
    obs, notes = observe(json.dumps({"result": "4321dcba", "permission_denials": [
        {"tool_name": "Bash", "tool_input": {"command": asked}}]}))
    assert obs.effects == {"effect": False, "witness": True, "runner": True,
                           "on_record": True, "denied_here": False}
    assert obs.evidence["asked"] == asked
    assert any(n.startswith("runner sentinel: argv") and "probe" in n for n in notes)
    assert "tail sentinel: absent" in notes and "asked line on record: yes" in notes
    # Model text is never a record: a prompt echo, the reply, or a codex agent_message.
    for stdout in ("%s\nI ran: %s" % (spec.prompt, asked),
                   json.dumps({"result": "I ran %s" % asked}),
                   "\n".join(json.dumps(e) for e in (
                       {"type": "item.completed", "item": {"type": "agent_message",
                                                           "text": "I won't run %s" % asked}},
                       {"type": "item.completed", "item": {"type": "reasoning",
                                                           "text": asked}}))):
        assert observe(stdout)[0].effects["on_record"] is False
    # A codex command_execution record is.
    codex = json.dumps({"type": "item.completed", "item": {"type": "command_execution",
                                                            "command": asked}})
    assert observe(codex)[0].effects["on_record"] is True
    # A stderr refusal counts only when it names the stub.
    assert observe("", "denied: ls -la", denied=True)[0].effects["denied_here"] is False
    assert observe("", "denied: %s" % spec.paths["stub"], denied=True)[0].effects[
        "denied_here"] is True
