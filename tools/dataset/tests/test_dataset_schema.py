"""The shared dataset schema (REQ-671 review follow-up).

``export.py``, ``publish.py`` and ``article_numbers.py`` read the columns and
``revision.json``'s schema from ``schema.py``, so the three cannot drift apart.
"""
import json
import os
import re

import pytest

import article_numbers
import export
import publish
import schema
from dataset_helpers import DATASET_DIR

SHA = "0123456789abcdef" * 2 + "01234567"
REVISION = {"source_commit": SHA, "toolkit_version": "1.2.3",
            "records": dict((k, 0) for k in schema.classify.KIND_ORDER),
            "scrub_replacements": {"credential": 0, "home-path": 2}}


def test_one_definition():
    assert export.COLUMNS is schema.COLUMNS and export.record_strings is schema.record_strings
    for module in (export, publish, article_numbers):
        for stale in ("_SHA_RE", "_VERSION_RE", "_RULE_RE", "_REVISION_KEYS", "SHA_SHORT",
                      "release_tag"):
            assert not hasattr(module, stale), (module.__name__, stale)
    with open(os.path.join(DATASET_DIR, "schema.py"), encoding="utf-8") as fh:
        source = fh.read()
    # article_numbers.py imports this module, and its test forbids a process.
    assert "subprocess" not in source and "huggingface" + "_hub" not in source


def test_release_tag():
    assert schema.release_tag("1.2.3", SHA) == "v1.2.3-" + SHA[:schema.SHA_SHORT]
    assert schema.SHA_SHORT == 12


def _changed(**fields):
    data = json.loads(json.dumps(REVISION))
    data.update(fields)
    return data


@pytest.mark.parametrize("revision, problem", [
    (REVISION, None),
    ([], "must hold exactly"),
    (_changed(extra=1), "must hold exactly"),
    (_changed(source_commit=SHA + "\n"), "source_commit"),
    (_changed(toolkit_version="1.0 beta"), "toolkit_version"),
    (_changed(records={"requirement": 1}), "records"),
    (_changed(scrub_replacements={}), "scrub_replacements"),
    (_changed(scrub_replacements={"total": 1}), "scrub_replacements"),
    (_changed(scrub_replacements={"Credential": 1}), "scrub_replacements"),
], ids=["valid", "not-object", "extra-key", "newline-sha", "spaced-version", "missing-kinds",
        "no-rules", "total-rule", "upper-rule"])
def test_publish_and_article_agree(revision, problem):
    """One rule set: publish refuses exactly what the article script refuses."""
    found = schema.revision_problem(revision)
    assert (found is None) if problem is None else (problem in found), found
    if problem is None:
        assert publish.parse_revision(json.dumps(revision)).source_commit == SHA
        article_numbers._check_revision(revision)
        return
    with pytest.raises(publish.Refused, match="^revision.json " + re.escape(found)):
        publish.parse_revision(json.dumps(revision))
    with pytest.raises(article_numbers.NumbersError, match="^revision.json: " + re.escape(found)):
        article_numbers._check_revision(revision)
