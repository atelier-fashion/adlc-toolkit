"""Scrub rules (a)\u2013(g) and the residue pass (REQ-671 BR-3, BR-2, BR-5; TASK-152).

Every rule has a case that must fire and a case that must not (LESSON-440).
The DenyList under test is a fixture, so the cases do not depend on which repos
the committed file names; one case checks the committed file wires up.
"""
import json
import os

import pytest

import credential_redact
import denylist
import residue
import scrub
from dataset_helpers import DATASET_DIR

FIXTURE = {
    "organization": "acme-org",
    "organization_repo": None,
    "public_repos": ["open-tool"],
    "repos": [
        {"name": "secret-api", "placeholder": "consumer-repo-1", "match": "token", "aliases": []},
        {"name": "web-app", "placeholder": "consumer-repo-2", "match": "token", "aliases": []},
        {"name": "platform", "placeholder": "consumer-repo-3", "match": "repo-context", "aliases": []},
    ],
    "people": [{"name": "Dana", "placeholder": "the maintainer"}],
    "email_allowlist": ["noreply@anthropic.com", "git@github.com"],
}


@pytest.fixture
def scrubber():
    s = scrub.Scrubber(denylist.parse(json.dumps(FIXTURE)))
    s.checker = residue.Checker(denylist.parse(json.dumps(FIXTURE)))
    return s


def _line(scrubber, text):
    out, counts, prose = scrubber.scrub_line(text)
    return out, dict((r, n) for r, n in counts if n), prose


def _clean(scrubber, text):
    return scrubber.checker.scan_line(text) == []


def test_rule_a_credentials(scrubber):
    out, counts, _ = _line(scrubber, "aws AKIAABCDEFGHIJKLMNOP gh ghp_%s key sk-%s"
                           % ("a" * 36, "b" * 24))
    assert out == "aws [REDACTED] gh [REDACTED] key [REDACTED]"
    assert counts == {"credential": 3}
    benign = "the GITHUB_TOKEN variable was unset"
    assert _line(scrubber, benign) == (benign, {}, [])


def test_rule_b_home_paths(scrubber):
    out, counts, _ = _line(
        scrubber, "edit /Users/someone/GitHub/open-tool/.worktrees/REQ-1/tools/x.py now")
    assert out == "edit <home>/open-tool/tools/x.py now"
    assert counts == {"home-path": 1}
    assert _line(scrubber, "under `/Users/` and /private/tmp/x")[0] == \
        "under `<home>/` and <local-path>"
    assert _line(scrubber, "a /home/someone/notes.txt")[0] == "a <local-path>"
    for benign in ("~/.claude/skills/partials", "/tmp/home/x", "https://host/home/x",
                   "relative tools/dataset/export.py"):
        assert _line(scrubber, benign) == (benign, {}, []), benign


def test_rule_b_keeps_this_repos_tail(scrubber):
    out, _, _ = _line(scrubber, "/Users/x/GitHub/open-tool/.claude/worktrees/wt/partials/a.sh")
    assert out == "<home>/open-tool/partials/a.sh"
    assert _line(scrubber, "/Users/x/GitHub/secret-api/src/a.py")[0] == "<local-path>"


def test_rule_c_emails(scrubber):
    out, counts, _ = _line(scrubber, "mail jane.doe+x@example.co.uk or noreply@anthropic.com")
    assert out == "mail <email> or noreply@anthropic.com"
    assert counts == {"email": 1}
    for benign in ("install adlc@adlc-toolkit", "Co-Authored-By: noreply@anthropic.com",
                   "git@github.com:acme-org/open-tool.git", "@pytest.fixture"):
        assert _line(scrubber, benign)[1] == {}, benign


def test_rule_d_denylist_token_and_repo_context(scrubber):
    out, counts, _ = _line(scrubber, "secret-api, Secret-API and secret-api-staging; web-app")
    assert out == "consumer-repo-1, consumer-repo-1 and consumer-repo-1-staging; consumer-repo-2"
    assert counts == {"denylist": 4}
    assert _line(scrubber, "secret-apiary and mysecret_api stay")[1] == {}

    # repo-context: replaced where it names a repository ...
    for text, expected in (
            ("see ../platform/src", "see ../consumer-repo-3/src"),
            ("the `platform` repo", "the `consumer-repo-3` repo"),
            ("| platform | 57 |", "| consumer-repo-3 | 57 |"),
            ("acme-org/platform#12", "acme-org/consumer-repo-3#12"),
            ("swept `platform@main STALE`", "swept `consumer-repo-3@main STALE`"),
            ("platform `main`: `ad38896`", "consumer-repo-3 `main`: `<sha>`")):
        assert _line(scrubber, text)[0] == expected, text
    # ... and left, but reported, in plain prose.
    out, counts, prose = _line(scrubber, "Every platform piece worked.")
    assert out == "Every platform piece worked." and counts == {} and prose == ["platform"]


def test_rule_e_private_urls_and_shas(scrubber):
    out, counts, _ = _line(
        scrubber, "fixed in [#9](https://github.com/acme-org/secret-api/pull/9) at abc1234f")
    assert out == "fixed in [#9]([link removed]) at <sha>"
    assert counts == {"private-url": 1, "private-sha": 1}
    benign = "public https://github.com/acme-org/open-tool/pull/205 at abc1234f"
    assert _line(scrubber, benign) == (benign, {}, [])
    assert _line(scrubber, "a defaced word and 1234567 here")[1] == {}


def test_rule_f_org_namespace(scrubber):
    out, counts, _ = _line(scrubber, "acme-org/unlisted-thing and acme-org/open-tool")
    assert out == "acme-org/private-repo and acme-org/open-tool"
    assert counts == {"org-namespace": 1}
    out, counts, _ = _line(scrubber, "https://github.com/acme-org/unlisted-thing/blob/x")
    assert out == "[link removed]" and counts == {"private-url": 1}
    for benign in ("acme-org/open-tool.git", "~/GitHub/acme-org/.adlc/x", "acme-org alone"):
        assert _line(scrubber, benign)[1] == {}, benign


def test_rule_g_person(scrubber):
    out, counts, _ = _line(scrubber, "Dana ran it. Then dana's fix, per Dana.")
    assert out == "The maintainer ran it. Then the maintainer's fix, per the maintainer."
    assert counts == {"person": 3}
    assert _line(scrubber, "Danaher and Adana stay")[1] == {}


def test_scrub_covers_frontmatter_lines(scrubber):
    text = "---\ntitle: \"key AKIAABCDEFGHIJKLMNOP\"\nnot a key: /Users/x/y\n---\nbody\n"
    out, findings, _ = scrubber.scrub_text(text, "f.md")
    assert "AKIA" not in out and "/Users/" not in out
    assert sorted((f.rule, f.line) for f in findings) == [("credential", 2), ("home-path", 3)]
    assert all(f.action == "replaced" and f.file == "f.md" for f in findings)


PLANTED = [
    "aws AKIAABCDEFGHIJKLMNOP",
    "path /Users/someone/x",
    "mail jane@example.com",
    "repo secret-api",
    "repo-context ../platform/x",
    "url https://github.com/acme-org/web-app/pull/1",
    "org acme-org/unlisted",
    "person Dana",
]


def test_residue_detects_unscrubbed_and_clears_scrubbed(scrubber):
    for text in PLANTED:
        assert not _clean(scrubber, text), text
        assert _clean(scrubber, scrubber.scrub_line(text)[0]), text
    for benign in ("Every platform piece worked.", "noreply@anthropic.com",
                   "acme-org/open-tool", "acme-org/private-repo", "acme-org/consumer-repo-1"):
        assert _clean(scrubber, benign), benign


def test_residue_scan_reports_lines(scrubber):
    hits = residue.scan("ok\nDana here\nok", scrubber.checker)
    assert hits == [residue.Hit("denylist", 2)]


def test_committed_denylist_scrubs_its_own_names():
    dl = denylist.load(os.path.join(DATASET_DIR, "denylist.json"))
    s = scrub.Scrubber(dl)
    for repo in dl.repos:
        text = "see ../%s/src" % repo.name
        out = s.scrub_line(text)[0]
        assert repo.name not in out and repo.placeholder in out
        assert residue.Checker(dl).scan_line(out) == []


# --- mutation-killing cases (REQ-671 verify) --------------------------------------
#
# A second fixture adds the organization-as-a-repository entry and aliases, so
# the cases above keep their meaning. "Secret API" is also reachable through the
# name's own separators; "Hush Service" is reachable only as an alias.

FIXTURE_ORG = json.loads(json.dumps(FIXTURE))
FIXTURE_ORG["organization_repo"] = {"placeholder": "consumer-repo-9"}
FIXTURE_ORG["repos"][0]["aliases"] = ["Secret API", "Hush Service"]


@pytest.fixture
def org_scrubber():
    dl = denylist.parse(json.dumps(FIXTURE_ORG))
    s = scrub.Scrubber(dl)
    s.checker = residue.Checker(dl)
    return s


def _fires_and_clears(scrubber, text, detector):
    """The raw line trips ``detector`` in the residue pass; the scrubbed line is clean."""
    assert detector in scrubber.checker.scan_line(text), text
    assert _clean(scrubber, scrubber.scrub_line(text)[0]), text


# (1) Credential arms only the wide chain carries.

@pytest.mark.parametrize("text, expected", [
    ("password = correcthorse", "[REDACTED]"),
    ("token ghs_%s end" % ("a1B2c" * 6), "token [REDACTED] end"),
])
def test_wide_chain_credentials(scrubber, text, expected):
    assert _line(scrubber, text) == (expected, {"credential": 1}, [])
    _fires_and_clears(scrubber, text, "credential")


def test_wide_chain_url_userinfo(scrubber):
    text = "https://user:hunter22@example.com/x"
    out, counts, _ = _line(scrubber, text)
    assert "hunter22" not in out and counts == {"credential": 1}
    _fires_and_clears(scrubber, text, "credential")


@pytest.mark.parametrize("benign", [
    "password = short1",  # under the 8 characters the assignment arm wants
    "ghs_short and gho_",
    "https://example.com/x and git@github.com:o/r",
])
def test_wide_chain_benign(scrubber, benign):
    assert _line(scrubber, benign) == (benign, {}, [])
    assert _clean(scrubber, benign)


def test_wide_assignment_arm_wants_equals():
    # The wide chain's assignment arm wants "=", so prose naming a variable is
    # not a credential there. (The intake chain's "<NAME>_TOKEN:" arm still
    # redacts this line through the scrub, fail-closed by shell parity.)
    assert credential_redact.WIDE_PATTERN.search("GITHUB_TOKEN: was unset in CI") is None
    assert credential_redact.WIDE_PATTERN.search("GITHUB_TOKEN = was_unset_in_CI")


# (2) The dataset's extra credential shapes (EXTRA_CREDENTIAL).

@pytest.mark.parametrize("text, secret", [
    ("hf hf_%s end" % ("aB3" * 12)[:34], "aB3aB3"),
    ("ya ya29.%s end" % ("aB3_-" * 5), "aB3_-"),
    ("authorization: bearer abcdefghijklmnopqrst+/==", "abcdefghijklmnopqrst"),
    ('"api_key": "abcd1234efgh5678ijkl"', "abcd1234efgh5678ijkl"),
    ("blob %s end" % ("AbCd0123" * 6)[:44], "AbCd0123"),
])
def test_extra_credential_arms(scrubber, text, secret):
    out, counts, _ = _line(scrubber, text)
    assert secret not in out and "[REDACTED]" in out, out
    assert counts == {"credential": 1}, counts


@pytest.mark.parametrize("benign", [
    "commit 0123456789abcdef0123456789abcdef01234567 landed",
    "tools/adlc/tests/test_x.py",
    "a-very-long-lowercase-kebab-slug-that-goes-on-and-on-for-ever-and-ever",
    "bearer of news",
    '"api_key": "short"',
    "the hf_ prefix and ya29. prefix",
])
def test_extra_credential_benign(scrubber, benign):
    assert _line(scrubber, benign) == (benign, {}, [])


def test_whole_jwt_replaced_signature_included(scrubber):
    # PRODUCTION BUG (REQ-671 verify): the wide chain's JWT arm stops at the
    # second dot and runs first, so it replaces header and payload and leaves
    # the signature; the whole-JWT arm in EXTRA_CREDENTIAL never sees an eyJ.
    # Input "tok eyJabc.eyJdef.sig123 end" scrubs to "tok [REDACTED]sig123 end".
    out, counts, _ = _line(scrubber, "tok eyJabc.eyJdef.sig123 end")
    assert out == "tok [REDACTED] end"
    assert counts == {"credential": 1}


# (3) An email inside markdown emphasis.

def test_email_inside_emphasis(scrubber):
    out, counts, _ = _line(scrubber, "mail _jane@example.com_ and __x@y.org__ now")
    assert "jane" not in out and "x@y" not in out and out.count("<email>") == 2
    assert counts == {"email": 2}
    for benign in ("pin react@18.3.1", "install adlc@adlc-toolkit"):
        assert _line(scrubber, benign) == (benign, {}, []), benign


# (4) repo-context: the contexts that name a repository, and line forcing.

@pytest.mark.parametrize("text, expected", [
    ("platform#50", "consumer-repo-3#50"),
    ("[platform#9](https://github.com/acme-org/platform/pull/9)",
     "[consumer-repo-3#9]([link removed])"),
    ("clone platform.git", "clone consumer-repo-3.git"),
    ("see ?repo=platform", "see ?repo=consumer-repo-3"),
    ("platform@main", "consumer-repo-3@main"),
    ("see ../platform/x and the platform again", "see ../consumer-repo-3/x and the consumer-repo-3 again"),
    # another repo's ``name#50`` is a reference, so the whole line is forced
    ("the platform piece, see other#50", "the consumer-repo-3 piece, see other#50"),
])
def test_repo_context_names_a_repo(scrubber, text, expected):
    out, counts, prose = _line(scrubber, text)
    assert out == expected and prose == []
    assert "platform" not in out
    _fires_and_clears(scrubber, text, "denylist")


def test_repo_context_plain_prose_kept_and_reported(scrubber):
    assert _line(scrubber, "the platform team") == ("the platform team", {}, ["platform"])
    assert _clean(scrubber, "the platform team")
    # an HTML character reference is not a ``#<n>`` reference, so it forces nothing
    text = "the platform piece &#123; here"
    assert _line(scrubber, text) == (text, {}, ["platform"])


# (5) A name's separator variants, its aliases, and its boundaries.

@pytest.mark.parametrize("text", ["secret_api", "SECRET-API", "secretapi", "Secret API",
                                  "Hush Service", "hush_service", "HUSHSERVICE"])
def test_name_separator_variants_and_aliases(org_scrubber, text):
    out, counts, _ = _line(org_scrubber, "see %s now" % text)
    assert out == "see consumer-repo-1 now" and counts == {"denylist": 1}, out
    _fires_and_clears(org_scrubber, "see %s now" % text, "denylist")


@pytest.mark.parametrize("benign", ["secret-apiary", "mysecret-api", "secret-api2",
                                    "hush servicer", "the hush"])
def test_name_needs_no_alnum_on_either_side(org_scrubber, benign):
    assert _line(org_scrubber, benign) == (benign, {}, []), benign
    assert _clean(org_scrubber, benign), benign


def test_alias_unknown_without_the_entry(scrubber):
    assert _line(scrubber, "Hush Service")[1] == {}


# (6) The organization's name used as a repository (organization_repo).

@pytest.mark.parametrize("text, expected", [
    ("acme-org#497", "consumer-repo-9#497"),
    ("| acme-org | 3 |", "| consumer-repo-9 | 3 |"),
    ("the `acme-org` repo", "the `consumer-repo-9` repo"),
    ("~/GitHub/acme-org/.adlc/x", "~/GitHub/consumer-repo-9/.adlc/x"),
    ("acme-org#4 at abc1234", "consumer-repo-9#4 at <sha>"),
])
def test_org_as_repo_replaced(org_scrubber, text, expected):
    assert _line(org_scrubber, text)[0] == expected
    _fires_and_clears(org_scrubber, text, "org-repo")


def test_org_as_repo_keeps_the_organization(org_scrubber):
    assert _line(org_scrubber, "acme-org/open-tool") == ("acme-org/open-tool", {}, [])
    assert _line(org_scrubber, "acme-org/other") == ("acme-org/private-repo",
                                                     {"org-namespace": 1}, [])
    assert _line(org_scrubber, "the acme-org team") == ("the acme-org team", {}, ["acme-org"])
    for benign in ("acme-org/open-tool", "acme-org/private-repo", "the acme-org team"):
        assert _clean(org_scrubber, benign), benign


def test_org_as_repo_needs_the_entry(scrubber):
    for text in ("acme-org#497", "| acme-org |", "`acme-org`", "acme-org#4 at abc1234"):
        assert _line(scrubber, text) == (text, {}, []), text
        assert _clean(scrubber, text), text


# (7) A personal GitHub namespace, and a scheme-less private URL.

@pytest.mark.parametrize("text", ["https://github.com/dana/side-project",
                                  "github.com/acme-org/secret-api/pull/3"])
def test_personal_and_schemeless_urls(scrubber, text):
    assert _line(scrubber, "at %s now" % text) == ("at [link removed] now",
                                                   {"private-url": 1}, [])
    assert not _clean(scrubber, text)


def test_other_accounts_urls_kept(scrubber):
    for benign in ("https://github.com/danaher/tool", "github.com/acme-org/open-tool/pull/3"):
        assert _line(scrubber, benign) == (benign, {}, []), benign
        assert _clean(scrubber, benign), benign


# (8) SHAs: removed only on a line with a private hit.

def test_sha_rules(scrubber):
    assert _line(scrubber, "secret-api ABCDEF1234567") == ("consumer-repo-1 <sha>",
                                                           {"denylist": 1, "private-sha": 1}, [])
    assert _line(scrubber, "secret-api defaced 1234567")[0] == "consumer-repo-1 defaced <sha>"
    benign = "nothing private abc1234 and ABCDEF1234567"
    assert _line(scrubber, benign) == (benign, {}, [])


# (9) A home path on a private line, and a lower-case /users/.

def test_home_path_with_sha(scrubber):
    assert _line(scrubber, "/Users/x/GitHub/secret-api at abc1234") == (
        "<local-path> at <sha>", {"home-path": 1, "private-sha": 1}, [])
    assert _line(scrubber, "cd /users/jdoe/x") == ("cd <local-path>", {"home-path": 1}, [])
    _fires_and_clears(scrubber, "cd /users/jdoe/x", "home-path")


# (10) Unicode: format characters and full-width forms do not hide a hit.

@pytest.mark.parametrize("text, detector", [
    ("Da​na wrote it", "denylist"),
    ("see secret­-api", "denylist"),
    ("／Users／x", "home-path"),
])
def test_residue_scan_normalizes(scrubber, text, detector):
    out = scrubber.scrub_line(text)[0]
    assert scrubber.checker.scan_line(out) == []  # the plain scan alone misses it
    assert residue.scan(out, scrubber.checker) == [
        residue.Hit(detector + " (after normalization)", 1)]
    assert residue.scan("Dana wrote it", scrubber.checker) == [residue.Hit("denylist", 1)]
    assert residue.scan("plain été text", scrubber.checker) == []


# (11) A private key excludes its record; the regex text in a doc does not.

def test_blocking_private_key(scrubber):
    text = "intro\n-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk\n-----END OPENSSH PRIVATE KEY-----"
    assert scrubber.blocking(text) == [2]
    assert scrubber.blocking("the regex -----BEGIN [A-Z ]*PRIVATE KEY in docs\nok") == []


@pytest.mark.parametrize("text", [
    "authorization: bearer abcdefghijklmnopqrst+/==",
    '"api_key": "abcd1234efgh5678ijkl"',
    "blob " + "Ab1" * 15,
])
def test_residue_catches_the_dataset_only_credential_shapes(scrubber, text):
    """The residue pass checks the scrub's extra credential shapes on its own."""
    assert "credential" in scrubber.checker.scan_line(text)
    assert _clean(scrubber, scrubber.scrub_line(text)[0])


@pytest.mark.parametrize("text", [
    "pin react@18.3.1 here",
    "the platform &#123; entity",
    "a 40-hex sha " + "a1" * 20,
])
def test_residue_does_not_fire_on_versions_entities_or_shas(scrubber, text):
    assert _clean(scrubber, text), text


@pytest.mark.parametrize("text", [
    "SECRET_KEY = 'django-insecure-abc$def#ghi%jkl'",
    "password=abcdefghijklmnop!@#$secretTail",
    '"password": "p@ssw0rd-hunter2-2024"',
    "x-api-key: abcdef1234567890abcd",
    "curl -u admin:S3cretPassw0rd!",
    "OPENAI_KEY=sk_proj_abcdefghijklmnopqrstuv",
    "Authorization: Basic dXNlcjpwYXNzd29yZDEyMzQ=",
    "key " + "a1b2" * 16,
])
def test_whole_secret_value_is_redacted(scrubber, text):
    """No tail of a secret survives (the verify regression: a value with ``$``/``!``)."""
    out = scrubber.scrub_line(text)[0]
    assert "[REDACTED]" in out
    for tail in ("def#ghi", "secretTail", "hunter2", "abcdef1234567890abcd", "S3cret",
                 "abcdefghijklmnopqrstuv", "dXNlcjpw", "a1b2a1b2"):
        assert tail not in out, (text, out)
    assert _clean(scrubber, out)


@pytest.mark.parametrize("text, gone", [
    ("secret\u2011api and the web", "secret"),        # non-breaking hyphen
    ("secret\u2013api", "secret"),                     # en dash
    ("https://gist.github.com/dana/0123456789abcdef", "dana"),
])
def test_typographic_dashes_and_gists(scrubber, text, gone):
    out = scrubber.scrub_line(text)[0]
    assert gone not in out.lower() or "consumer-repo" in out or "[link removed]" in out
    assert _clean(scrubber, out)


def test_residue_strips_combining_marks(scrubber):
    assert scrubber.checker.scan_line("Da\u034fna") == []  # hidden from a line scan ...
    assert residue.scan("Da\u034fna", scrubber.checker)   # ... not from the normalized scan


def test_record_with_a_repo_use_replaces_its_prose_uses(scrubber):
    """Prose next to the placeholder in one record would reverse it (verify finding)."""
    text = "1. **platform** (26 files)\nsee ../platform/src for the platform"
    out, findings, prose = scrubber.scrub_text(text, "f.md")
    assert "platform" not in out.replace("consumer-repo", "")
    assert prose == []
    benign, _, prose = scrubber.scrub_text("1. **platform** (26 files)", "g.md")
    assert "**platform**" in benign and [p.name for p in prose] == ["platform"]


def test_residue_flags_a_name_beside_its_placeholder(scrubber):
    hits = residue.scan("consumer-repo-3 (26)\nthe **platform** list", scrubber.checker)
    assert [h.line for h in hits if "placeholder" in h.detector] == [2]
    assert residue.scan("the **platform** list", scrubber.checker) == []
