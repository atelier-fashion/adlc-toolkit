"""Run directories, the ledger and tokens (REQ-659 BR-10)."""

import json
import os
import re
import stat
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_ledger as el  # noqa: E402


def test_run_dir_and_ledger(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path / "state"), "HOME": str(tmp_path)}
    run = el.create_run_dir(env)
    assert os.path.dirname(run) == str(tmp_path / "state" / "adlc" / "exec")
    assert re.fullmatch(r"[0-9a-f]{32}", os.path.basename(run))
    assert stat.S_IMODE(os.stat(run).st_mode) == 0o700
    assert run != el.create_run_dir(env)

    record = {"req": "REQ-901"}
    ledger = el.Ledger(run, record)
    assert ledger.accounted()
    ledger.halt_write({"prs": []})
    first = os.stat(ledger.path).st_ino
    assert ledger.accounted()
    ledger.decide("approved", "op", "shell", 42, ack_gate_change=True)
    assert os.stat(ledger.path).st_ino != first, "a ledger write replaces the file"
    doc = ledger.read()
    assert doc["decision"]["decision"] == "approved" and doc["decision"]["ackGateChange"] is True
    assert len(record["ledgerWrites"]) == 2
    assert not [n for n in os.listdir(run) if n.startswith(".tmp-")]


def test_unaccounted_ledger(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    run = el.create_run_dir(env)
    record = {"req": "REQ-901"}
    ledger = el.Ledger(run, record)
    with open(ledger.path, "w") as fh:
        json.dump({"plan": {}, "decision": {"decision": "approved"}}, fh)
    assert not ledger.accounted()
    with pytest.raises(el.LedgerError):
        ledger.halt_write({"prs": []})
    record2 = {"req": "REQ-901"}
    os.unlink(ledger.path)
    ledger2 = el.Ledger(run, record2)
    ledger2.halt_write({"prs": []})
    with open(ledger2.path, "a") as fh:
        fh.write(" ")
    with pytest.raises(el.LedgerError):
        ledger2.decide("approved", "op", "shell", 1)


def test_supersede_keeps_the_decision_on_record(tmp_path):
    run = el.create_run_dir({"XDG_STATE_HOME": str(tmp_path)})
    ledger = el.Ledger(run, {"req": "REQ-901"})
    ledger.halt_write({"prs": [1]})
    ledger.decide("approved", "op", "shell", 1)
    ledger.supersede({"prs": [2]}, "headRefOid")
    doc = ledger.read()
    assert doc["decision"] is None and doc["plan"] == {"prs": [2]}
    assert doc["superseded"][0]["supersededBecause"] == "headRefOid"


def test_find_run_newest(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    repo = tmp_path / "repo"
    repo.mkdir()
    for stamp in ("2026-01-01", "2026-02-01"):
        run = el.create_run_dir(env)
        el.atomic_json(os.path.join(run, el.RUN_RECORD),
                       {"req": "REQ-901", "primary": os.path.realpath(str(repo)),
                        "exec": {"startedAt": stamp}, "marker": stamp})
    found = el.find_run(str(repo), "REQ-901", env)
    assert el.read_json(os.path.join(found, el.RUN_RECORD))["marker"] == "2026-02-01"
    assert el.find_run(str(repo), "REQ-902", env) is None


def test_tokens():
    token = el.mint_token()
    assert len(token) == 32
    assert el.token_digest(token) != el.token_digest(token, "changes the gate: x")
    assert token not in el.token_digest(token)
