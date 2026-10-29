"""The scrub rules (REQ-671 BR-3), applied to every raw line (BR-5).

Each rule replaces what ``detectors.py`` finds, and every replacement is a
finding ``{rule, file, line, action: "replaced"}``. The order is fixed:

1. (a) ``credential``: the shared chains from ``tools/adlc/credential_redact.py``
   and the dataset's extra shapes.
2. The line's private-repository hits are computed here, before any rule below
   replaces a name or a path, so (e) ``private-sha`` and the forced
   ``repo-context`` replacement can see them.
3. (c) ``email``: before (g), so a name inside an address cannot hide it.
4. (b) ``home-path``: before (d) and (g), so a username or repo name inside a
   path goes with the whole path, not word by word.
5. (e) ``private-url``, (f) ``org-namespace``, (e) ``private-sha``,
   (d) ``denylist``, (g) ``person``.

The scrub replaces. It decides that a record is unpublishable only for a
private key, whose body lines match nothing on their own (:meth:`Scrubber.blocking`).
Other records are excluded by the frontmatter recognizer and the residue pass.
"""
import re
from collections import namedtuple

import credential_redact
import detectors

Finding = namedtuple("Finding", "rule file line action")
ProseHit = namedtuple("ProseHit", "file line name")

RULES = ("credential", "email", "home-path", "private-url", "org-namespace",
         "private-sha", "denylist", "person")

_WORKTREE_PREFIX_RE = re.compile(r"^(?:\.worktrees/[^/]+/|\.claude/worktrees/[^/]+/)")
_SENTENCE_START_RE = re.compile(r"(?:^[ \t>*#|-]*|[.!?:][ \t]+)$")


def _home_path_replacement(path, public_repos):
    """Keep the repo-relative tail of a path inside a public repo; drop the rest."""
    rest = re.sub(r"^/[^/]+/", "", path)  # drop the /Users/, /home/ or /private/ root
    if not rest:
        return "<home>/"
    for repo in public_repos:
        m = re.search(r"(?:^|/)%s(?:/(.*))?$" % re.escape(repo), rest)
        if m:
            tail = _WORKTREE_PREFIX_RE.sub("", m.group(1) or "")
            return "<home>/%s/%s" % (repo, tail) if tail else "<home>/" + repo
    return "<local-path>"


def _replace_spans(line, spans, replacement):
    """Replace non-overlapping ``spans`` (any order) with ``replacement``."""
    out = line
    for s, e in sorted(set(spans), reverse=True):
        rep = replacement(out[s:e], out[:s]) if callable(replacement) else replacement
        out = out[:s] + rep + out[e:]
    return out


class Scrubber(object):
    """Scrub text against one DenyList."""

    def __init__(self, dl):
        self.det = detectors.Detectors(dl)
        self.public_repos = dl.public_repos

    def scrub_line(self, line):
        """Return ``(line, [(rule, count)], [prose names])`` for one line."""
        det = self.det
        counts = []

        n = 0
        for pattern in detectors.CREDENTIAL_PATTERNS:
            line, k = pattern.subn(credential_redact.REPLACEMENT, line)
            n += k
        counts.append(("credential", n))

        had_private = det.has_denylist_hit(line)
        force = had_private or det.line_has_ref(line)

        hits = [m.span() for m in det.email_hits(line)]
        line = _replace_spans(line, hits, "<email>")
        counts.append(("email", len(hits)))

        hits = [m.span() for m in detectors.HOME_PATH_RE.finditer(line)]
        line = _replace_spans(line, hits, lambda text, _: _home_path_replacement(
            text, self.public_repos))
        counts.append(("home-path", len(hits)))

        hits = [m.span() for m in det.private_url_hits(line)]
        line = _replace_spans(line, hits, "[link removed]")
        counts.append(("private-url", len(hits)))

        hits = [m.span(1) for m in det.org_ns_hits(line, det.public | det.denied)]
        line = _replace_spans(line, hits, "private-repo")
        counts.append(("org-namespace", len(hits)))

        n = 0
        if had_private:
            hits = [m.span() for m in detectors.SHA_RE.finditer(line)]
            line = _replace_spans(line, hits, "<sha>")
            n = len(hits)
        counts.append(("private-sha", n))

        prose = []
        total = 0
        for repo, pattern in det.repo_res:
            spans = det.repo_spans(line, repo, pattern, force)
            prose.extend(line[s:e] for s, e in det.plain_prose(line, repo, pattern, force))
            line = _replace_spans(line, spans, repo.placeholder)
            total += len(spans)
        counts.append(("denylist", total))

        n = 0
        if det.people_re is not None:
            spans = [m.span() for m in det.people_re.finditer(line)]

            def placeholder(_, before, ph=det.people_placeholder):
                if _SENTENCE_START_RE.search(before):
                    return ph[:1].upper() + ph[1:]
                return ph
            line = _replace_spans(line, spans, placeholder)
            n = len(spans)
        counts.append(("person", n))
        return line, counts, prose

    def blocking(self, text):
        """Line numbers on which ``text`` holds a private key (excludes the record)."""
        return [i for i, line in enumerate(text.split("\n"), 1)
                if detectors.PRIVATE_KEY_RE.search(line)]

    def scrub_text(self, text, path):
        """Scrub every line; return ``(text, findings, prose_hits)``.

        A context entry's plain-prose uses are kept only while the record holds
        no placeholder for it: once one line names the repository, the same word
        elsewhere in the record would reverse the placeholder, so every
        occurrence in the record is replaced.
        """
        out = []
        findings = []
        prose_hits = []
        for lineno, line in enumerate(text.split("\n"), 1):
            new, counts, prose = self.scrub_line(line)
            out.append(new)
            for rule, n in counts:
                findings.extend(Finding(rule, path, lineno, "replaced") for _ in range(n))
            prose_hits.extend(ProseHit(path, lineno, name) for name in prose)
        for repo, pattern in self.det.repo_res:
            if repo.match == "token" or not any(repo.placeholder in line for line in out):
                continue
            for i, line in enumerate(out):
                spans = self.det.repo_spans(line, repo, pattern, force=True)
                if spans:
                    out[i] = _replace_spans(line, spans, repo.placeholder)
                    findings.extend(Finding("denylist", path, i + 1, "replaced") for _ in spans)
            prose_hits = [p for p in prose_hits if not pattern.fullmatch(p.name)]
        return "\n".join(out), findings, prose_hits
