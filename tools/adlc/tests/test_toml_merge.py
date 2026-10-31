"""REQ-655 BR-5: the TOML scanner fails closed, and a merge moves no byte it does not own."""

import pytest

import toml_merge as tm

VALUES = {"sandbox_mode": "workspace-write", "approval_policy": "on-request"}
REFUSE = {"sandbox_mode": ["danger-full-access"], "approval_policy": ["never"]}
TABLE = "sandbox_workspace_write"


def merge(text):
    return tm.merge_owned(text, VALUES, REFUSE, ("profile",), TABLE)


def test_fresh_file_gets_exactly_the_owned_keys():
    out = merge("")
    assert out.text == 'sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n'
    assert out.added == ["sandbox_mode", "approval_policy"]


def test_merge_keeps_every_other_key():
    out = merge('model = "x"\n')
    assert out.text.startswith('model = "x"\n') and "sandbox_mode" in out.text
    assert out.conflicts == []


def test_a_second_merge_changes_nothing():
    once = merge('model = "x"\n').text
    assert merge(once).text == once


def test_keys_go_above_the_first_header_and_the_table_stays_byte_identical():
    table = '[tui]\ntheme = "dark"   # a comment\n\n[projects."/a/b"]\ntrust_level = "trusted"\n'
    text = 'model = "x"\n\n' + table
    out = merge(text)
    assert out.text.endswith(table)
    assert out.text.index("sandbox_mode") < out.text.index("[tui]")
    found = tm.scan(out.text, tuple(VALUES), TABLE)
    assert list(found.top) == ["model", "sandbox_mode", "approval_policy"]


def test_an_owned_key_with_another_value_is_reported_and_left():
    text = 'sandbox_mode = "read-only"\n'
    out = merge(text)
    assert 'sandbox_mode = "read-only"' in out.text
    assert out.conflicts and "read-only" in out.conflicts[0]


@pytest.mark.parametrize("line", ['sandbox_mode = "danger-full-access"\n',
                                  'approval_policy = "never"\n'])
def test_a_refused_posture_raises(line):
    with pytest.raises(tm.PostureRefused):
        merge(line)


@pytest.mark.parametrize("text,construct", [
    ('sandbox_mode = "a"\nsandbox_mode = "b"\n', "duplicate key"),
    ('[t]\nsandbox_mode = "x"\n', "inside a table"),
    ('a.b = 1\n', "dotted key"),
    ('sandbox_workspace_write.writable_roots = []\n', "dotted key"),
    ('note = """\nx\n"""\n', "multi-line string"),
    ("note = '''x'''\n", "multi-line string"),
    ('roots = [\n  "a",\n]\n', "multi-line array"),
    ('"sandbox_mode" = "x"\n', "quoted key spelling"),
    ("'approval_policy' = 'x'\n", "quoted key spelling"),
    ('x = { a = 1 }\n', "top-level inline table"),
    ('[[a]]\nb = 1\n', "[[array-of-tables]]"),
    ('[sandbox_workspace_write]\na = 1\n[sandbox_workspace_write]\nb = 2\n',
     "duplicate [sandbox_workspace_write]"),
    ('["sandbox_workspace_write"]\na = 1\n', "quoted [sandbox_workspace_write]"),
    ('[ sandbox_workspace_write ]\na = 1\n', "spaced [sandbox_workspace_write]"),
    ('profile = "x"\n', "top-level profile"),
    ('a = 1\r\n', "CRLF"),
    ('﻿a = 1\n', "BOM"),
    ('a = 1', "missing trailing newline"),
])
def test_each_fail_closed_construct(text, construct):
    with pytest.raises(tm.TomlConstructError) as err:
        merge(text)
    assert construct in str(err.value)


@pytest.mark.parametrize("text,construct", [
    ('sandbox_mode = "danger\\u002dfull-access"\n', "not a plain string"),
    ('sandbox_mode = 5\n', "not a plain string"),
    ('["sandbox_workspace\\u005fwrite"]\n', "escaped key"),
    ('note =\n', "key with no value"),
])
def test_what_would_hide_a_refused_value_fails_closed(text, construct):
    with pytest.raises(tm.TomlConstructError) as err:
        merge(text)
    assert construct in str(err.value)


def test_a_literal_string_is_still_refused():
    with pytest.raises(tm.PostureRefused):
        merge("sandbox_mode = 'danger-full-access'\n")


def test_strings_and_arrays_hide_nothing():
    text = ('note = "a [b] # c = d"\n'
            "lit = 'sandbox_mode = \"x\"'\n"
            'arr = ["x]", "#y", "=z", ["n"]]  # a comment with = and [\n'
            '[t]\nv = "[not] a header"\n')
    found = tm.scan(text, tuple(VALUES), TABLE)
    assert list(found.top) == ["note", "lit", "arr"]
    assert found.headers == ["t"]
    assert merge(text).text.endswith('[t]\nv = "[not] a header"\n')


def test_a_quoted_header_naming_another_table_is_classified():
    text = '[projects."/Users/x/repo"]\ntrust_level = "trusted"\n'
    assert tm.scan(text, tuple(VALUES), TABLE).headers == ["projects./Users/x/repo"]


def test_union_creates_the_table_at_the_end():
    out = tm.union_list('model = "x"\n', TABLE, "writable_roots", "/a/.git")
    assert out == 'model = "x"\n\n[sandbox_workspace_write]\nwritable_roots = ["/a/.git"]\n'


def test_union_adds_under_an_existing_header():
    text = '[sandbox_workspace_write]\nnetwork_access = false\n\n[tui]\nx = 1\n'
    out = tm.union_list(text, TABLE, "writable_roots", "/a")
    assert out == ('[sandbox_workspace_write]\nwritable_roots = ["/a"]\nnetwork_access = false\n'
                   '\n[tui]\nx = 1\n')


def test_union_keeps_every_entry_and_is_idempotent():
    text = '[sandbox_workspace_write]\nwritable_roots = ["/one", "/two"]  # mine\n'
    out = tm.union_list(text, TABLE, "writable_roots", "/three")
    assert out == ('[sandbox_workspace_write]\n'
                   'writable_roots = ["/one", "/two", "/three"]  # mine\n')
    assert tm.union_list(out, TABLE, "writable_roots", "/two") == out


def test_union_ignores_a_bracket_in_the_trailing_comment():
    text = '[sandbox_workspace_write]\nwritable_roots = ["/one"]  # see [docs]\n'
    out = tm.union_list(text, TABLE, "writable_roots", "/two")
    assert out == ('[sandbox_workspace_write]\n'
                   'writable_roots = ["/one", "/two"]  # see [docs]\n')


def test_union_into_an_empty_array():
    out = tm.union_list('[sandbox_workspace_write]\nwritable_roots = []\n', TABLE,
                        "writable_roots", "/a")
    assert 'writable_roots = ["/a"]' in out


def test_union_refuses_what_is_not_a_string_array():
    with pytest.raises(tm.TomlConstructError):
        tm.union_list('[sandbox_workspace_write]\nwritable_roots = 3\n', TABLE,
                      "writable_roots", "/a")
