"""The DenyList recognizer (REQ-671 BR-3d, architecture "The DenyList").

The DenyList decides what may leave the machine, so it is read by a
recognizer, not a reader (LESSON-614): strict JSON with a repeated key refused,
then a closed schema that names every key and type. Anything the schema does
not name is an error, never a skipped line. A malformed DenyList refuses the
export.
"""
import json
import re
from collections import namedtuple

#: Where the DenyList lives in the repository. The export reads it from the
#: commit it exports, never from the working tree, so an uncommitted edit
#: cannot weaken the gate (LESSON-718) and the commit determines the output.
REPO_PATH = "tools/dataset/denylist.json"

#: ``token``: every whole-word occurrence is a hit. ``repo-context``: only an
#: occurrence used as a repository name. ``org-context`` is internal: the
#: organization's own name used as a repository (``organization_repo``).
MATCH_MODES = ("token", "repo-context")

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PHRASE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 ._-]*[A-Za-z0-9])?$")
_TOP_KEYS = ("organization", "organization_repo", "public_repos", "repos", "people",
             "email_allowlist")
_REPO_KEYS = ("name", "placeholder", "match", "aliases")
_PERSON_KEYS = ("name", "placeholder")

Repo = namedtuple("Repo", "name placeholder match aliases")
Person = namedtuple("Person", "name placeholder")
DenyList = namedtuple("DenyList", "organization organization_repo public_repos repos people "
                                  "email_allowlist")


class DenyListError(Exception):
    """The DenyList is missing or malformed; the export must not run."""


def _refuse_repeated_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise DenyListError("repeated key %r" % key)
        seen.add(key)
    return dict(pairs)


def _str(value, where):
    if not isinstance(value, str) or not value.strip():
        raise DenyListError("%s must be a non-empty string" % where)
    if value != value.strip():
        raise DenyListError("%s has surrounding whitespace" % where)
    return value


def _name(value, where, pattern=_NAME_RE):
    _str(value, where)
    if not pattern.match(value):
        raise DenyListError("%s %r is not a plain name ([A-Za-z0-9._-], starting "
                            "with a letter or digit)" % (where, value))
    return value


def _list(value, where):
    if not isinstance(value, list):
        raise DenyListError("%s must be a list" % where)
    return value


def _exact_keys(obj, keys, where):
    if not isinstance(obj, dict):
        raise DenyListError("%s must be an object" % where)
    unknown = sorted(set(obj) - set(keys))
    missing = [k for k in keys if k not in obj]
    if unknown:
        raise DenyListError("%s has unknown key(s) %s" % (where, ", ".join(unknown)))
    if missing:
        raise DenyListError("%s is missing key(s) %s" % (where, ", ".join(missing)))


def parse(text):
    """Recognize DenyList JSON text; return a :class:`DenyList` or raise."""
    try:
        data = json.loads(text, object_pairs_hook=_refuse_repeated_keys)
    except DenyListError:
        raise
    except ValueError as exc:
        raise DenyListError("not valid JSON (%s)" % exc)
    _exact_keys(data, _TOP_KEYS, "the DenyList")

    org = _name(data["organization"], "organization")
    org_repo = data["organization_repo"]
    if org_repo is not None:
        _exact_keys(org_repo, ("placeholder",), "organization_repo")
        org_repo = Repo(org, _name(org_repo["placeholder"], "organization_repo.placeholder"),
                        "org-context", ())
    public = tuple(_name(v, "public_repos[%d]" % i)
                   for i, v in enumerate(_list(data["public_repos"], "public_repos")))
    if not public:
        raise DenyListError("public_repos must name at least one repository")

    repos = []
    for i, obj in enumerate(_list(data["repos"], "repos")):
        where = "repos[%d]" % i
        _exact_keys(obj, _REPO_KEYS, where)
        match = obj["match"]
        if match not in MATCH_MODES:
            raise DenyListError("%s.match must be one of %s" % (where, ", ".join(MATCH_MODES)))
        aliases = tuple(_name(a, "%s.aliases[%d]" % (where, j), _PHRASE_RE)
                        for j, a in enumerate(_list(obj["aliases"], where + ".aliases")))
        repos.append(Repo(_name(obj["name"], where + ".name"),
                          _name(obj["placeholder"], where + ".placeholder"), match, aliases))

    people = []
    for i, obj in enumerate(_list(data["people"], "people")):
        where = "people[%d]" % i
        _exact_keys(obj, _PERSON_KEYS, where)
        people.append(Person(_name(obj["name"], where + ".name", _PHRASE_RE),
                             _str(obj["placeholder"], where + ".placeholder")))

    emails = tuple(_str(v, "email_allowlist[%d]" % i).lower()
                   for i, v in enumerate(_list(data["email_allowlist"], "email_allowlist")))
    for e in emails:
        if e.count("@") != 1:
            raise DenyListError("email_allowlist entry %r is not an address" % e)

    names = [n.lower() for n in public] + [p.name.lower() for p in people]
    for r in repos:
        names += [r.name.lower()] + [a.lower() for a in r.aliases]
    dupes = sorted(set(n for n in names if names.count(n) > 1))
    if dupes:
        raise DenyListError("name(s) listed more than once: %s" % ", ".join(dupes))
    all_repos = repos + ([org_repo] if org_repo else [])
    placeholders = [r.placeholder.lower() for r in all_repos]
    if len(set(placeholders)) != len(placeholders):
        raise DenyListError("two repos share a placeholder; each private repo maps "
                            "to its own placeholder")
    denied = names + [org.lower()]
    for ph in [r.placeholder for r in all_repos] + [p.placeholder for p in people]:
        for name in denied:
            if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(name), ph.lower()):
                raise DenyListError("placeholder %r contains the name %r" % (ph, name))

    return DenyList(org, org_repo, public, tuple(repos), tuple(people), emails)


def load(path):
    """Read and recognize the DenyList at ``path`` (tests and tooling)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise DenyListError("cannot read %s (%s)" % (path, exc.strerror or exc))
    return parse_bytes(raw, path)


def parse_bytes(raw, where):
    """Recognize DenyList bytes read from ``where`` (a path or a blob name)."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise DenyListError("%s is not UTF-8" % where)
    return parse(text)
