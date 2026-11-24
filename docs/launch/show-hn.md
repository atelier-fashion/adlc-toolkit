# Show HN: draft

The maintainer posts this by hand, during the launch week, from their own Hacker News
account. Nothing in this repository posts it. Its row in the
[launch checklist](../launch-checklist.md) is `post-show-hn`.

Before posting:

- Replace each named slot in square brackets, such as `[Space link, once live]`, with the
  address in the link column of that item's checklist row. The row is `live` by then,
  because this post depends on it.
- The draft states no duration. State one only if the quickstart's `quickstart-verified`
  line records a release and a measured time, and then use that figure.
- Add no figures about the project: no stars, no counts of users or installs.

## Title

```text
Show HN: ADLC, spec-driven development skills for Claude Code
```

## URL

```text
https://github.com/atelier-fashion/adlc-toolkit
```

## Text

```text
ADLC is a set of Claude Code skills, agents and templates for spec-driven development. You describe a change, and a run takes it from a written requirement to a merged pull request. Each run leaves three things in your repo: a validated spec, a reviewed PR and a captured lesson.

How a run goes:

- /adlc:spec turns a request into a requirement under .adlc/specs/, with business rules and acceptance criteria. It sorts the request into a lite lane for small changes or a full lane for the rest.

- /adlc:proceed takes that requirement to a merged PR. On the full lane it validates the spec, writes an architecture doc, breaks the work into tasks, implements them, reviews its own diff, and has a panel of review agents read it. On the lite lane it skips spec validation, the architecture and the tasks, and runs one review pass. Then it opens the pull request and merges it.

- /adlc:wrapup writes what the run learned as a lesson under .adlc/knowledge/lessons/, or a one-line reason for writing none. Later specs and reviews read those lessons.

Install, in your terminal:

  claude plugin marketplace add atelier-fashion/adlc-toolkit
  claude plugin install adlc@adlc-toolkit

The quickstart goes from that install to a merged pull request in a small sample project, in eight typed steps: https://github.com/atelier-fashion/adlc-toolkit/blob/main/docs/quickstart.md

The toolkit is built with its own process. Its .adlc/ directory holds the specs, tasks and lessons of its own development, and that record is published as a dataset: [dataset link, once live]. An article walks through it: [article link, once live]. To try the spec step without installing anything, a Hugging Face Space turns pasted notes into a draft requirement and a list of gaps, using your own Anthropic API key: [Space link, once live]

Limits:

- It runs inside Claude Code. It is not a standalone tool or a hosted service.
- Every run uses your own Claude Code plan.
- /adlc:proceed pushes branches, and opens and merges pull requests, with your gh login in the repo you run it in. The quickstart uses a throwaway private repo for that reason.
- Delegating bulk reads to another model is off by default, and the plugin install does not include it.
- The toolkit sends no usage data anywhere.

It is MIT licensed. I would like to hear where the spec or review steps get in your way.
```
