"""The residue pass (REQ-671 BR-2, architecture layer 3).

Runs over text that is supposed to be clean already: one record's scrubbed text
and parsed fields, then the exact JSONL, card and revision about to be written.
Any hit means the scrub missed something, and the caller excludes the record or
refuses the export. It never repairs.

It does not reuse ``detectors.py``. Its checks are written again here, broader
where that is cheap (any ``/users/``, any private name outside plain prose, any
email not on the allow list), so a gap in the scrub's own detectors is not
automatically a gap here (LESSON-614). It also scans the text after NFKC
normalization with format characters removed, so a zero-width space or a
full-width slash cannot split a name past both layers.
"""
import re
import unicodedata
from collections import namedtuple

import credential_redact

Hit = namedtuple("Hit", "detector line")

_EXTRA_CREDENTIAL = (
    re.compile(r"hf_[A-Za-z0-9]{30,}|ya29\.[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]+\.eyJ"
               r"|sk_[A-Za-z0-9_-]{20,}", re.ASCII),
    re.compile(r"PRIVATE KEY-----"),
    re.compile(r"(?:bearer|basic)[ \t]+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE | re.ASCII),
    re.compile(r"(?:secret|pass|api[-_]?key|access[-_]?key|private[-_]?key|token|credential)"
               r"[A-Za-z_-]*[\"']?[ \t]*[:=][ \t]*[\"']?[^\s\"'`]{8,}", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])-u[ \t]+[^\s:]+:[^\s]{6,}"),
    re.compile(r"[0-9a-f]{41,}", re.IGNORECASE),
    re.compile(r"(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[0-9])"
               r"[A-Za-z0-9+/]{40,}", re.ASCII),
)
_HOME = re.compile(r"/users/|(?<![a-z0-9_.-])/(?:home|private)/|[a-z]:\\users\\", re.IGNORECASE)
_EMAIL = re.compile(r"[^\s@<>()\[\]{}\"'`,;|:/=]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
                    r"\.[A-Za-z]{2,}(?![A-Za-z0-9])")
_REF = re.compile(r"(?<![a-z0-9])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}(?![a-z0-9])|(?<!&)#[0-9]+(?![A-Za-z0-9])",
                  re.IGNORECASE)
_SCRUB_MARK = re.compile(r"consumer-repo-[0-9]+|private-repo|\[link removed\]")
#: Placeholders the scrub writes. Masked before the credential checks, so that
#: ``secret=<local-path>`` is not read as an assignment.
_PLACEHOLDERS = re.compile(r"<home>|<local-path>|<email>|<sha>|\[REDACTED\]|\[link removed\]")
_PROSE_BEFORE = " \t(\"'*_"
_PROSE_AFTER = " \t.,;:!?)\"'*_"


def _words(name, separator=r"[-_ ]?"):
    return separator.join(re.escape(p) for p in re.split(r"[-_ ]+", name))


#: Hyphens of every kind, read as ``-`` after normalization.
_DASHES = dict.fromkeys(list(range(0x2010, 0x2016)) + [0x2212, 0xfe63, 0xff0d], "-")


def _word_re(names):
    names = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:%s)(?![a-z0-9])" % "|".join(map(_words, names)),
                      re.IGNORECASE)


class Checker(object):
    """The residue checks one DenyList implies, written independently of the scrub."""

    def __init__(self, dl):
        self.allow_email = frozenset(e.lower() for e in dl.email_allowlist)
        self.token = _word_re([n for r in dl.repos if r.match == "token"
                               for n in (r.name,) + tuple(r.aliases)]
                              + [p.name for p in dl.people])
        context = [n for r in dl.repos if r.match != "token" for n in (r.name,) + tuple(r.aliases)]
        self.context = _word_re(context) if context else None
        #: (name pattern, placeholder) for each context entry: a record that holds
        #: both reverses the placeholder.
        self.pairs = [(_word_re((r.name,) + tuple(r.aliases)), r.placeholder)
                      for r in dl.repos if r.match != "token"]
        if dl.organization_repo:
            self.pairs.append((re.compile(r"(?<![a-z0-9])%s(?![a-z0-9]|/[a-z0-9])"
                                          % _words(dl.organization, "[-_]?"), re.IGNORECASE),
                               dl.organization_repo.placeholder))
        self.org = dl.organization.lower()
        self.org_repo = bool(dl.organization_repo)
        allowed = set(n.lower() for n in dl.public_repos) | set(
            r.placeholder.lower() for r in dl.repos) | {"private-repo"}
        if dl.organization_repo:
            allowed.add(dl.organization_repo.placeholder.lower())
        self.allowed_after_org = allowed
        self.ns = re.compile(r"(?<![a-z0-9_.-])%s/([a-z0-9][a-z0-9_.-]*)" % re.escape(self.org),
                             re.IGNORECASE)
        people = sorted((p.name for p in dl.people), key=len, reverse=True)
        self.personal_url = re.compile(r"github\.com/(?:%s)/" % "|".join(map(_words, people)),
                                       re.IGNORECASE) if people else None

    def _named(self, line, m):
        """True when a context-name match is not plain prose."""
        s, e = m.span()
        before = line[s - 1] if s else " "
        after = line[e] if e < len(line) else " "
        if before not in _PROSE_BEFORE or after not in _PROSE_AFTER:
            return True
        if line[e:e + 4].lower() == ".git":
            return True
        return bool(re.search(r"\|[ \t]*$", line[:s]) and re.match(r"[ \t]*\|", line[e:]))

    def scan_line(self, line):
        fired = []
        masked = _PLACEHOLDERS.sub(" ", line)
        if credential_redact.find(masked, credential_redact.ALL_PATTERNS) or any(
                p.search(masked) for p in _EXTRA_CREDENTIAL):
            fired.append("credential")
        if any(m.group(0).lower().strip(".") not in self.allow_email
               for m in _EMAIL.finditer(line)):
            fired.append("email")
        if _HOME.search(line):
            fired.append("home-path")
        if self.token.search(line):
            fired.append("denylist")
        marked = bool(_REF.search(line) or _SCRUB_MARK.search(line))
        if self.context and any(marked or self._named(line, m)
                                for m in self.context.finditer(line)):
            fired.append("denylist")
        if self.org_repo:
            # Without a space: "Atelier Fashion" is the company's name.
            for m in re.finditer(r"(?<![a-z0-9])%s(?![a-z0-9])" % _words(self.org, "[-_]?"),
                                 line, re.IGNORECASE):
                if re.match(r"/[a-z0-9]", line[m.end():m.end() + 2], re.IGNORECASE):
                    continue
                if marked or self._named(line, m):
                    fired.append("org-repo")
                    break
        for m in self.ns.finditer(line):
            name = m.group(1).lower()
            name = name[:-4] if name.endswith(".git") else name
            if name.rstrip("._-") not in self.allowed_after_org:
                fired.append("org-namespace")
                break
        if self.personal_url and self.personal_url.search(line):
            fired.append("private-url")
        return fired


def _normalized(text):
    """NFKD, without format characters or combining marks, every hyphen as ``-``, NFKC."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cf", "Mn"))
    return unicodedata.normalize("NFKC", text.translate(_DASHES))


def scan(text, checker):
    """Scan every line of ``text`` and of its normalized form; return :class:`Hit` list.

    Also flags a context entry's name anywhere in a ``text`` that holds its
    placeholder: the pair would reverse the placeholder.
    """
    hits = []
    for lineno, line in enumerate(text.split("\n"), 1):
        hits.extend(Hit(name, lineno) for name in checker.scan_line(line))
    for pattern, placeholder in checker.pairs:
        if placeholder in text:
            for lineno, line in enumerate(text.split("\n"), 1):
                if pattern.search(line):
                    hits.append(Hit("denylist (name beside its placeholder)", lineno))
    norm = _normalized(text)
    if norm != text:
        seen = set(hits)
        for lineno, line in enumerate(norm.split("\n"), 1):
            for name in checker.scan_line(line):
                hit = Hit(name + " (after normalization)", lineno)
                if Hit(name, lineno) not in seen and hit not in hits:
                    hits.append(hit)
    return hits
