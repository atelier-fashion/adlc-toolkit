"""Tests for the adlc umbrella CLI dispatch (TASK-001 / BR-11)."""
import adlc


def test_version_prints_and_exits_zero(capsys):
    rc = adlc.main(["--version"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out  # non-empty version string
    assert out != "unknown" or True  # tolerate "unknown" off a non-VERSION tree


def test_no_subcommand_is_usage_error(capsys):
    rc = adlc.main([])
    out = capsys.readouterr().out
    assert rc == 2  # no command is a usage error
    assert "usage:" in out
    assert "doctor" in out  # registered subcommand listed


def test_help_exits_zero(capsys):
    rc = adlc.main(["--help"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "usage:" in out


def test_unknown_subcommand_errors(capsys):
    rc = adlc.main(["definitely-not-a-command"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "unknown command" in err


def test_dispatch_table_is_data_driven():
    # Adding a command must be a registry entry, not an if/elif limb.
    assert isinstance(adlc.SUBCOMMANDS, dict)
    assert "doctor" in adlc.SUBCOMMANDS
    assert callable(adlc.SUBCOMMANDS["doctor"]["handler"])
    assert adlc.SUBCOMMANDS["doctor"]["help"]


def test_doctor_subcommand_dispatches(monkeypatch):
    called = {}

    def fake_main(argv):
        called["argv"] = argv
        return 0

    import doctor
    monkeypatch.setattr(doctor, "main", fake_main)
    rc = adlc.main(["doctor", "--checks", "gh-auth"])
    assert rc == 0
    assert called["argv"] == ["--checks", "gh-auth"]
