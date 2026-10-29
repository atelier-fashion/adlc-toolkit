"""What the scrub looks for (REQ-671 BR-3).

This module only finds things; ``scrub.py`` replaces what it finds.
``residue.py`` re-implements the checks on its own, so a gap in this module is
not automatically a gap in the residue pass (architecture layer 3).

Name boundaries are look-arounds on ``[A-Za-z0-9]``, never ``\\b``: a hyphen or
an underscore separates words, so ``atelier-web-staging`` and ``admin-api_v2``
both contain a name. A name's own separators match any of ``-``, ``_``, a space
or nothing, so ``teton-code``, ``teton_code``, ``Teton Code`` and ``tetoncode``
are one name.
"""
import re

import credential_redact

_L = r"(?<![A-Za-z0-9])"
_R = r"(?![A-Za-z0-9])"

#: (a) A whole JWT, header to signature. It runs before the shared chains: the
#: wide chain's JWT arm stops at the second dot and would leave the signature.
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")

#: (a) Credential shapes the shared chains do not cover, applied by the dataset
#: scrub only, after them: Hugging Face, Google and underscore-style ``sk_`` keys,
#: any-case ``bearer`` and ``basic`` with base64 punctuation, a ``curl -u`` pair,
#: a key-like assignment written with ``:``, ``=`` or quotes whose value runs to
#: whitespace or a closing quote, a hex run longer than a SHA, and a 40+
#: character mixed-class base64 run. ASCII classes, as the shell chains run
#: under ``LC_ALL=C``.
EXTRA_CREDENTIAL = re.compile(
    r"hf_[A-Za-z0-9]{30,}|ya29\.[A-Za-z0-9_-]{20,}|sk_[A-Za-z0-9_-]{20,}"
    r"|(?i:bearer|basic)[ \t]+[A-Za-z0-9._~+/=-]{16,}"
    r"|(?<![A-Za-z0-9])-u[ \t]+[^\s:]+:[^\s]{6,}"
    r"|[\"']?[A-Za-z_-]*(?i:secret|passw(?:or)?d|pass|api[-_]?key|access[-_]?key|private[-_]?key"
    r"|token|credential)[A-Za-z_-]*[\"']?[ \t]*[:=][ \t]*[\"']?[^\s\"'`]{8,}"
    r"|(?<![0-9a-fA-F])[0-9a-f]{41,}(?![0-9a-fA-F])"
    r"|(?<![A-Za-z0-9+/=_-])(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])"
    r"(?=[A-Za-z0-9+/]*[0-9])[A-Za-z0-9+/]{40,}={0,2}",
    re.ASCII)

#: Every credential pattern the dataset scrub applies, in order: the whole JWT,
#: then the shared chains (whose assignment arms consume a whole value), then the
#: extra shapes.
CREDENTIAL_PATTERNS = (JWT_RE,) + credential_redact.ALL_PATTERNS + (EXTRA_CREDENTIAL,)

#: A private key: the record is excluded, not redacted line by line, because
#: the key's body lines match nothing on their own.
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")

#: (b) A home or machine-local absolute path and the rest of its path token.
#: ``/Users/`` in any case and with no left boundary; ``/home/`` and
#: ``/private/`` after anything but a path or word character (the
#: ``partials/lesson-check.sh`` BR-12 rule), so ``https://host/home/x`` is not a
#: hit and ``/tmp//home/x`` is.
_PATH_TAIL = r"[^\s`'\"<>()\[\]{}|,;*]*"
HOME_PATH_RE = re.compile(
    r"(?:/[Uu][Ss][Ee][Rr][Ss]/|(?<![A-Za-z0-9_.-])/(?:home|private)/)" + _PATH_TAIL)

#: (c) An email address. Only letters and digits end it, so markdown emphasis
#: (``_a@b.com_``) does not hide one.
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}" + _R)

#: (e) A commit SHA: 7 to 40 hex characters, either case, with at least one
#: digit, so an all-letter English word (``defaced``) is not one.
SHA_RE = re.compile(r"(?<![A-Za-z0-9])(?=[0-9a-fA-F]*[0-9])[0-9a-fA-F]{7,40}" + _R)

#: A ``#<n>`` issue or pull-request reference, including ``name#50``; not an
#: HTML character reference (``&#123;``).
PR_REF_RE = re.compile(r"(?<!&)#[0-9]+" + _R)

#: Characters that may sit next to a ``repo-context`` name in plain prose.
#: Anything else (``/``, ``@``, ``#``, a backtick, ``=``, ``[``…) names a repo.
PROSE_BEFORE = frozenset(" \t(\"'*_")
PROSE_AFTER = frozenset(" \t.,;:!?)\"'*_")

_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?"


def _bare(name):
    """A repo name as compared: lower case, without a ``.git`` suffix."""
    name = name.lower()
    return name[:-4] if name.endswith(".git") else name


#: What may stand between a name's parts: a hyphen of any kind, an underscore,
#: a space, or nothing.
SEPARATOR = "[-_ \u2010-\u2015\u2212]?"


#: The same without a space: the organization's name with a space is the
#: company's name in prose and citations, not a repository.
SEPARATOR_NO_SPACE = "[-_\u2010-\u2015\u2212]?"


def flex(name, separator=SEPARATOR):
    """A name's regex body with ``separator`` between its parts."""
    return separator.join(re.escape(p) for p in re.split(r"[-_ ]+", name))


def name_pattern(names, separator=SEPARATOR):
    """One case-insensitive whole-word pattern for ``names``, longest first."""
    bodies = [flex(n, separator) for n in sorted(names, key=len, reverse=True)]
    return re.compile(_L + "(?:" + "|".join(bodies) + ")" + _R, re.IGNORECASE)


class Detectors(object):
    """The detectors one DenyList implies."""

    def __init__(self, dl):
        org = re.escape(dl.organization)
        self.org = dl.organization.lower()
        self.public = frozenset(n.lower() for n in dl.public_repos)
        self.denied = frozenset(r.name.lower() for r in dl.repos)
        #: Names that may follow ``<org>/`` in scrubbed output.
        repos = dl.repos + ((dl.organization_repo,) if dl.organization_repo else ())
        self.allowed_after_org = self.public | frozenset(
            r.placeholder.lower() for r in repos) | frozenset(["private-repo"])
        self.emails = frozenset(dl.email_allowlist)
        owners = [re.escape(dl.organization)] + [
            flex(n) for n in sorted((p.name for p in dl.people), key=len, reverse=True)]
        #: (e) A GitHub or gist URL, with or without a scheme, into the organization
        #: or a maintainer account; group 1 is the owner, group 2 the repo or gist.
        self.owner_url_re = re.compile(
            r"(?:https?://)?(?<![A-Za-z0-9.-])(?:www\.|gist\.)?github\.com/(%s)/(%s)"
            r"[^\s`'\"<>()\[\]{}|]*" % ("|".join(owners), _NAME), re.IGNORECASE)
        #: (f) ``<org>/<name>``; group 1 is the name.
        self.org_ns_re = re.compile(r"(?<![A-Za-z0-9_.-])%s/(%s)" % (org, _NAME), re.IGNORECASE)
        #: (d) One pattern per repo entry, its aliases included; the
        #: organization's own name, used as a repository, last.
        self.repo_res = [(r, name_pattern((r.name,) + tuple(r.aliases))) for r in dl.repos]
        if dl.organization_repo:
            self.repo_res.append((dl.organization_repo,
                                  name_pattern([dl.organization], SEPARATOR_NO_SPACE)))
        #: (g) Every person, longest name first, so a full name is one hit.
        self.people_re = name_pattern([p.name for p in dl.people]) if dl.people else None
        self.people_placeholder = dl.people[0].placeholder if dl.people else ""

    # --- per-line queries --------------------------------------------------

    def email_hits(self, line):
        return [m for m in EMAIL_RE.finditer(line) if m.group(0).lower() not in self.emails]

    def private_url_hits(self, line):
        return [m for m in self.owner_url_re.finditer(line)
                if m.group(1).lower() != self.org or _bare(m.group(2)) not in self.public]

    def org_ns_hits(self, line, allowed):
        """``<org>/<name>`` matches whose name is not in ``allowed``."""
        return [m for m in self.org_ns_re.finditer(line) if _bare(m.group(1)) not in allowed]

    def line_has_ref(self, line):
        return bool(SHA_RE.search(line) or PR_REF_RE.search(line))

    def _names_org(self, repo, line, end):
        """True when an ``org-context`` match ending at ``end`` is the org itself."""
        return repo.match == "org-context" and bool(re.match(r"/[A-Za-z0-9]", line[end:end + 2]))

    def is_prose(self, line, start, end):
        """True when ``line[start:end]`` is used as a word, not as a repo name."""
        before = line[start - 1] if start else " "
        after = line[end] if end < len(line) else " "
        if before not in PROSE_BEFORE or after not in PROSE_AFTER:
            return False
        if line[end:end + 4].lower() == ".git":
            return False
        if re.search(r"\|[ \t]*$", line[:start]) and re.match(r"[ \t]*\|", line[end:]):
            return False  # a whole table cell
        return True

    def repo_spans(self, line, repo, pattern, force=None):
        """Spans of ``repo`` the scrub must replace on ``line``.

        A ``token`` entry: every whole-word occurrence. A ``repo-context`` or
        ``org-context`` entry: every occurrence that is not plain prose
        (:meth:`is_prose`), or every occurrence when ``force`` is true. ``force``
        defaults to "the line carries a SHA or a ``#<n>`` reference"; the scrub
        also forces a line with any other private-repository hit. The
        organization's name followed by ``/<name>`` is the organization, not a
        repository, and is never a span.
        """
        spans = []
        if force is None:
            force = self.line_has_ref(line)
        for m in pattern.finditer(line):
            s, e = m.span()
            if self._names_org(repo, line, e):
                continue
            if repo.match == "token" or force or not self.is_prose(line, s, e):
                spans.append((s, e))
        return spans

    def plain_prose(self, line, repo, pattern, force=None):
        """Occurrences of a context entry left in place as plain prose."""
        if repo.match == "token":
            return []
        named = set(self.repo_spans(line, repo, pattern, force))
        return [m.span() for m in pattern.finditer(line)
                if m.span() not in named and not self._names_org(repo, line, m.end())]

    def home_path_private(self, line):
        """True when a home path on ``line`` points outside every public repo."""
        for m in HOME_PATH_RE.finditer(line):
            parts = set(p.lower() for p in m.group(0).split("/"))
            if not parts & self.public:
                return True
        return False

    def has_denylist_hit(self, line):
        """True when ``line`` names a private repository in any detected way."""
        if self.private_url_hits(line) or self.org_ns_hits(line, self.public):
            return True
        if self.home_path_private(line):
            return True
        return any(self.repo_spans(line, r, p) for r, p in self.repo_res)
