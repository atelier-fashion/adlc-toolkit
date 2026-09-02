"""REQ-603 AC-19 / AC-21 — compare the CURRENT gate against the PRE-REQ gate.

Three review passes asked for this and none of the prior substitutes did it:
they compared the cascade against a restatement of itself, by the same author.
This runs BOTH gate scripts — origin/main's, frozen as a fixture — over one
input matrix, backed by the SAME real adlc-read, so the only variable is the
shell layer and the reason mapping. That is exactly what BR-4 makes claims
about.

The named divergences (BR-4 D1-D5) must occur; nothing else may.

REQ-609 keeps that posture and extends it (ADR-4): parity is preserved by
REGISTRATION, not by freezing behaviour. Every outcome this REQ changes on the
frozen fixture's corpus is a named divergence D6+ with `REQ-609` as its source,
in `_MALFORMED_ROWS` below. The 24-row well-formed matrix is expected to show
none — a diff there would be a finding, and `_NAMED` is pinned to REQ-603's one
entry so that a new one cannot be added by accident.
"""
import collections
import os
import re
import subprocess
import sys

import pytest

import _child_env  # noqa: E402  (REQ-609: child interpreters need the parent's PyYAML)

_HERE = os.path.dirname(os.path.abspath(__file__))
_DELEGATE = os.path.dirname(_HERE)
_ROOT = os.path.normpath(os.path.join(_DELEGATE, "..", ".."))
_CURRENT = os.path.join(_ROOT, "partials", "delegate-gate.sh")
_FIXTURE = os.path.join(_ROOT, "partials", "tests", "fixtures", "delegate-gate.pre-req-603.sh")
_ADLC_READ = os.path.join(_DELEGATE, "adlc-read")
# The pre-REQ CLI + resolver, frozen from origin/main. D3/D4/D5 are PYTHON-layer
# divergences; comparing them needs the old Python behind the old gate, or the
# old gate merely reports the new resolver's answer and the row looks identical.
_OLD_ADLC_READ = os.path.join(_ROOT, "partials", "tests", "fixtures", "pre-req-603", "adlc-read")


def _run_gate(gate, env):
    r = subprocess.run(
        ["/bin/sh", "-c",
         f'. "{gate}"; adlc_delegate_gate_check >/dev/null 2>&1; '
         'printf "%s %s" "$?" "$ADLC_DELEGATE_GATE_REASON"'],
        capture_output=True, text=True, env=env)
    return r.stdout.strip()


def _env(tmp_path, veto=False, env_optin=False, config=None, legacy=False,
         key_var_unset=False, unreadable=False, cli=_ADLC_READ):
    # One wrapper directory PER CLI. A shared tmp_path/bin let a later
    # _env(new) call overwrite the wrapper a prior _env(old) had written, so
    # the OLD gate ran with the NEW resolver behind it. D3 passed by coincidence
    # (both CLIs agree on that row); the malformed-class rows exposed it.
    bindir = tmp_path / ("bin-old" if cli == _OLD_ADLC_READ else "bin-new")
    bindir.mkdir(exist_ok=True)
    wrapper = bindir / "adlc-read"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{cli}" "$@"\n')
    wrapper.chmod(0o755)
    e = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    # A key the REAL resolver can find, via a custom var so legacy-key
    # continuity is exercised only by the `legacy` axis.
    e["ADLC_DELEGATE_API_KEY_ENV"] = "MY_PROVIDER_KEY"
    if not key_var_unset:
        e["MY_PROVIDER_KEY"] = "sk-resolvable"
    if veto:
        e["ADLC_DISABLE_DELEGATE"] = "1"
    if env_optin:
        e["ADLC_DELEGATE_ENABLED"] = "1"
    if legacy:
        e["MOONSHOT_API_KEY"] = "sk-legacy"
    if config is not None:
        cfg = tmp_path / "config.yml"
        cfg.write_text(f"delegate:\n  enabled: {config}\n  api_key_env: MY_PROVIDER_KEY\n")
        if unreadable:
            cfg.chmod(0o000)
        e["ADLC_CONFIG"] = str(cfg)
    return _child_env.with_yaml(e)


# The full exported cross-product, with the SAME Python behind both gates. This
# isolates the shell layer: any difference here is a shell-arm difference, which
# is exactly what BR-1 removed and BR-4 makes claims about. Python-layer
# divergences (D3, D4, D5) are asserted separately below with the OLD CLI behind
# the OLD gate. Unexported variables are a KNOWN divergence (pass-3 M5): the old
# shell arms read shell scope, the probe cannot; not modelled here.
_MATRIX = [
    (veto, env_optin, config, legacy)
    for veto in (False, True)
    for env_optin in (False, True)
    for config in (None, "true", "false")
    for legacy in (False, True)
]

# BR-4's named divergences, as (inputs) -> (pre-REQ, current). Anything that
# differs between the gates and is NOT listed here is a finding.
_NAMED = {
    # D1: enabled:false, no legacy key -> label corrected, rc unchanged
    (False, False, "false", False): ("1 not-opted-in", "1 disabled-via-config"),
}


@pytest.mark.parametrize("row", _MATRIX, ids=lambda r: str(r))
def test_current_gate_matches_pre_req_gate_except_named_rows(row, tmp_path):
    veto, env_optin, config, legacy = row
    env = _env(tmp_path, veto=veto, env_optin=env_optin, config=config, legacy=legacy)
    old = _run_gate(_FIXTURE, env)
    new = _run_gate(_CURRENT, env)
    if row in _NAMED:
        assert (old, new) == _NAMED[row], f"named divergence {row} changed shape: {old!r} -> {new!r}"
    else:
        assert old == new, f"UNNAMED divergence at {row}: pre-REQ={old!r} current={new!r}"


def test_every_named_divergence_actually_diverges(tmp_path):
    """A table of exceptions is only honest if each exception is real."""
    for row, (exp_old, exp_new) in _NAMED.items():
        veto, env_optin, config, legacy = row
        env = _env(tmp_path, veto=veto, env_optin=env_optin, config=config, legacy=legacy)
        assert _run_gate(_FIXTURE, env) == exp_old, row
        assert _run_gate(_CURRENT, env) == exp_new, row


def test_d3_key_unset_diverges_fail_closed(tmp_path):
    """D3: opt-in satisfied, key var unset. pre-REQ (old gate + old CLI): ok —
    the old probe never checked the key. current: disabled-via-config, rc 0->1."""
    old_env = _env(tmp_path, config="true", key_var_unset=True, cli=_OLD_ADLC_READ)
    new_env = _env(tmp_path, config="true", key_var_unset=True)
    assert _run_gate(_FIXTURE, old_env) == "0 ok"
    assert _run_gate(_CURRENT, new_env) == "1 disabled-via-config"


def test_d4_unreadable_config_diverges_fail_closed(tmp_path):
    """D4: config exists but unreadable, legacy key exported. pre-REQ (old gate
    + old CLI): ok — unreadable read as absent, continuity granted. current:
    refuses. This is the BUG-205 outcome the REQ closes."""
    old_env = _env(tmp_path, config="false", legacy=True, unreadable=True, cli=_OLD_ADLC_READ)
    try:
        assert _run_gate(_FIXTURE, old_env) == "0 ok"
        (tmp_path / "config.yml").chmod(0o644)
        new_env = _env(tmp_path, config="false", legacy=True, unreadable=True)
        assert _run_gate(_CURRENT, new_env) == "1 disabled-via-config"
    finally:
        (tmp_path / "config.yml").chmod(0o644)


def test_d5_print_enabled_is_not_frozen_and_the_spec_says_so(tmp_path):
    """D5: --print-enabled inherited the fail-closed config rule. Three
    artifacts claimed it was frozen; it is not, and the honest thing is to
    name it. Old CLI: 1. Current CLI: 0. Same unreadable config, same key."""
    env = _env(tmp_path, config="false", legacy=True, unreadable=True)
    try:
        old = subprocess.run([sys.executable, _OLD_ADLC_READ, "--print-enabled"],
                             capture_output=True, text=True, env=env).stdout.strip()
        new = subprocess.run([sys.executable, _ADLC_READ, "--print-enabled"],
                             capture_output=True, text=True, env=env).stdout.strip()
        assert (old, new) == ("1", "0"), (old, new)
    finally:
        (tmp_path / "config.yml").chmod(0o644)


def test_old_and_new_python_agree_where_no_divergence_is_named(tmp_path):
    """The Python layer, old vs new, on a row NO divergence names: must agree.
    Guards against a Python-layer change hiding behind the shell-only matrix."""
    for cfg, legacy in ((None, True), ("true", False), ("false", False)):
        old_env = _env(tmp_path, config=cfg, legacy=legacy, cli=_OLD_ADLC_READ)
        new_env = _env(tmp_path, config=cfg, legacy=legacy)
        o = subprocess.run([sys.executable, _OLD_ADLC_READ, "--print-enabled"],
                           capture_output=True, text=True, env=old_env).stdout.strip()
        n = subprocess.run([sys.executable, _ADLC_READ, "--print-enabled"],
                           capture_output=True, text=True, env=new_env).stdout.strip()
        assert o == n, (cfg, legacy, o, n)


# --- Malformed-config classes the 24-row matrix could not observe -----------
# Pass 4: the config axis was (None, "true", "false"), so no BR-4 D4-class row was
# ever compared against the pre-REQ gate. These rows are.
#
# Every pair below is MEASURED, never assumed: the first version of this test
# expected the old gate to grant on an undecodable byte in a comment, and was
# wrong. A row whose pair DIFFERS carries a divergence id and the REQ that owns
# it (REQ-609 ADR-4: parity is preserved by registration, not by freezing
# behaviour). A row whose pair MATCHES carries neither, and says why it does not
# move — several of those changed mechanism without changing outcome, which is
# worth recording precisely because it is not a divergence.
# `test_req_609_divergences_are_registered` holds those two facts to each other,
# so a later change that flips a row cannot land unregistered.

_Row = collections.namedtuple("_Row", "divergence source label make old new")

_GRANT = "0 ok"
_REFUSE = "1 disabled-via-config"


def _cfg_dir(tmp_path):
    d = tmp_path / "adlc"; d.mkdir(); return str(d)

def _cfg_file(tmp_path, body):
    f = tmp_path / "config.yml"; f.write_bytes(body); return str(f)


_MALFORMED_ROWS = [
    # -- REQ-603's D4 class, on a shape the 24-row matrix could not carry -----
    # The pre-REQ reader's errors="replace" turns the byte into U+FFFD, the key
    # stops matching `enabled`, {} -> continuity -> grant. REQ-603's reader
    # already refused on the decode; REQ-609 refuses on the same input for the
    # same reason class (`undecodable`), so the pair is unchanged by this REQ.
    _Row("D4", "REQ-603",
         "undecodable byte in the key (D4 class: old reads it as absent)",
         lambda t: _cfg_file(t, b"delegate:\n  enabl\xe9d: false\n"),
         _GRANT, _REFUSE),

    # Undecodable byte inside a COMMENT: replace() leaves `enabled: false`
    # parseable, so the OLD gate refuses on the operator's written false. The
    # current gate also refuses, but for a different reason — since REQ-609 the
    # decode is strict, so the file is `undecodable` before anything reads the
    # block (BR-3). Same outcome, different mechanism: not a divergence, and
    # recorded so the row stays a measured fact rather than an assumption.
    _Row(None, None,
         "undecodable byte in a comment (both refuse — old on the false, new on the decode)",
         lambda t: _cfg_file(t, b"delegate:\n  enabled: false  # d\xe9sactiv\xe9\n"),
         _REFUSE, _REFUSE),

    # -- REQ-609's divergences (ADR-4), each discharging a REQ-603 BR-14 -------
    # -- fail-open: the old gate GRANTS on all six, the current one refuses. ---
    # D6: BR-4 — a non-regular file is malformed with no carve-out. The old
    # reader read a directory as an unreadable file, which it called absence,
    # which fell through to legacy-key continuity.
    _Row("D6", "REQ-609",
         "directory at the path (REQ-609 BR-4: old grants through continuity)",
         _cfg_dir, _GRANT, _REFUSE),

    # D7: BR-3/BR-7 — a real parser reads the block behind a header comment.
    # The flat reader discarded the whole section on the trailing comment and
    # then granted, which is the shape a pass-3 reviewer opened with.
    _Row("D7", "REQ-609",
         "comment on the header (REQ-609 BR-3: old discards the block and grants)",
         lambda t: _cfg_file(t, b"delegate:  # settings\n  enabled: false\n"),
         _GRANT, _REFUSE),

    # D8: BR-4 again, on the shape BUG-205 was reported against —
    # `ADLC_CONFIG=/dev/null` turned delegation ON, because the carve-out
    # returned {} and {} is absence. A device node is not a machine without a
    # config.
    _Row("D8", "REQ-609",
         "/dev/null at the path (REQ-609 BR-4: the BUG-205 shape)",
         lambda t: "/dev/null", _GRANT, _REFUSE),

    # D9: BR-2 — a repeated key is a silent override in a governance file. The
    # old reader took the last `enabled` it saw, so a `true` appended under an
    # operator's `false` won without saying so.
    _Row("D9", "REQ-609",
         "a second enabled key (REQ-609 BR-2: old takes the last, new refuses)",
         lambda t: _cfg_file(t, b"delegate:\n  enabled: false\n  enabled: true\n"),
         _GRANT, _REFUSE),

    # D10: BR-3 — a leading BOM made the first key `\ufeffdelegate`, which
    # matched nothing, so the section read as absent and continuity granted.
    _Row("D10", "REQ-609",
         "BOM before the header (REQ-609 BR-3: old grants, new reads enabled: false)",
         lambda t: _cfg_file(t, b"\xef\xbb\xbfdelegate:\n  enabled: false\n"),
         _GRANT, _REFUSE),

    # D11: BR-7 — an unknown key refuses rather than being skipped. `enbaled:
    # false` silently ignored is an exfiltration the operator wrote down that
    # they did not want (LESSON-483).
    _Row("D11", "REQ-609",
         "a misspelled enabled key (REQ-609 BR-7: old skips it and grants)",
         lambda t: _cfg_file(t, b"delegate:\n  enbaled: false\n"),
         _GRANT, _REFUSE),

    # -- REQ-609 changes the MECHANISM here, not the outcome ------------------
    # A nested mapping hoisting `enabled: true` over a written `false` was a
    # pass-3 finding, but the pre-REQ reader happened to keep the last match and
    # refuse anyway. REQ-609 refuses it as an unknown key (BR-7). Both refuse,
    # so nothing is registered — measured, not assumed.
    _Row(None, None,
         "nested mapping over a written false (both refuse, for different reasons)",
         lambda t: _cfg_file(t, b"delegate:\n  nested:\n    enabled: true\n  enabled: false\n"),
         _REFUSE, _REFUSE),

    # The benign path, and the one row here that must stay a GRANT on both
    # gates. BR-6 made an absent `delegate` section mean *unconfigured* rather
    # than malformed; if that had come out wrong, every machine whose shared
    # config carries only a `forge:` section would have lost continuity. A
    # fail-closed REQ needs one row that proves it did not close the door on the
    # people it was not aimed at.
    _Row(None, None,
         "a config with only a forge section (benign path: both grant)",
         lambda t: _cfg_file(t, b"forge:\n  provider: github\n"),
         _GRANT, _GRANT),
]


@pytest.mark.parametrize("row", _MALFORMED_ROWS, ids=lambda r: r.label)
def test_malformed_classes_against_pre_req_gate(row, tmp_path):
    """Run BOTH gates on one malformed-config shape and hold each to its
    registered outcome (REQ-609 AC-1).

    The assertion is on the PAIR, not on the current gate alone: a row that
    silently stopped diverging — because the fixture rotted, or because the old
    CLI stopped being reachable — would otherwise still pass while measuring
    nothing.
    """
    path = row.make(tmp_path)
    old_env = _env(tmp_path, cli=_OLD_ADLC_READ, legacy=True)
    old_env["ADLC_CONFIG"] = path
    new_env = _env(tmp_path, legacy=True)
    new_env["ADLC_CONFIG"] = path
    assert _run_gate(_FIXTURE, old_env) == row.old, (row.label, "pre-REQ")
    assert _run_gate(_CURRENT, new_env) == row.new, (row.label, "current")


def test_req_609_divergences_are_registered():
    """ADR-4's bookkeeping, checked both ways.

    `test_every_named_divergence_actually_diverges` makes the same demand of
    `_NAMED`: a table of exceptions is only honest if each exception is real.
    Here the demand runs in both directions, because both failures are possible:
    a row registered as a divergence that no longer diverges is a stale
    exception, and a row that diverges without a registration is an unrecorded
    behaviour change — which is the one thing ADR-4 exists to prevent.

    Structural only. The runtime half — that the declared pairs are what the two
    gates actually produce — is `test_malformed_classes_against_pre_req_gate`.
    """
    for row in _MALFORMED_ROWS:
        diverges = row.old != row.new
        assert diverges == (row.divergence is not None), (
            "%s: diverges=%s but divergence=%r" % (row.label, diverges, row.divergence))
        assert diverges == (row.source is not None), row.label

    registered = [r for r in _MALFORMED_ROWS if r.source == "REQ-609"]
    # Two at minimum — the pair TASK-094 flipped and left for registration. More
    # than one, because a single-element table hides every ordering and
    # uniqueness bug in the check above (LESSON-399).
    assert len(registered) >= 2
    ids = [r.divergence for r in registered]
    assert len(set(ids)) == len(ids), ids
    for divergence_id in ids:
        assert re.match(r"^D[0-9]+$", divergence_id), divergence_id
        # REQ-603 owns D1-D5 and this REQ preserves them as-is (Out of Scope);
        # reusing one of its numbers would overwrite a ratified record.
        assert int(divergence_id[1:]) > 5, divergence_id


def test_well_formed_matrix_registers_no_req_609_divergence():
    """ADR-4: the 24-row well-formed matrix must show ZERO new divergence.

    `test_current_gate_matches_pre_req_gate_except_named_rows` proves the
    behavioural half by running both gates over the matrix. This pins the other
    half — that a future REQ-609-era divergence there was not quietly *made* to
    pass by adding a row to `_NAMED`. D1 is REQ-603's and is the only entry.
    """
    assert set(_NAMED) == {(False, False, "false", False)}
