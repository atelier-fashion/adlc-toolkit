# X thread: draft

The maintainer posts this by hand, during the launch week, from their own X account.
Nothing in this repository posts it. Its row in the
[launch checklist](../launch-checklist.md) is `post-x`.

Before posting:

- Replace each named slot in square brackets, such as `[Space link, once live]`, with the
  address in the link column of that item's checklist row. The row is `live` by then,
  because this post depends on it.
- The draft states no duration. State one only if the quickstart's `quickstart-verified`
  line records a release and a measured time, and then use that figure.
- Add no figures about the project: no stars, no counts of users or installs.

Each post is one fenced block, in order. Each fits in 280 characters, counting a link or a
named slot as the 23 characters X counts for a link.

## Post 1

```text
ADLC is a set of Claude Code skills for spec-driven development. A run takes a change from a written requirement to a merged pull request, and leaves three things in your repo: a validated spec, a reviewed PR and a captured lesson.

https://github.com/atelier-fashion/adlc-toolkit
```

## Post 2

```text
/adlc:spec turns a request into a requirement with acceptance criteria, and sorts it into a lite or a full lane.

/adlc:proceed builds it, reviews the diff, opens the PR and merges it.

/adlc:wrapup writes down what the run learned, for later runs to read.
```

## Post 3

```text
Install, in your terminal:

claude plugin marketplace add atelier-fashion/adlc-toolkit
claude plugin install adlc@adlc-toolkit

The quickstart goes from there to a merged PR in a sample project, in eight typed steps:
https://github.com/atelier-fashion/adlc-toolkit/blob/main/docs/quickstart.md
```

## Post 4

```text
To try the spec step without installing anything: a Hugging Face Space turns pasted notes into a draft requirement and a list of gaps, using your own Anthropic API key.

[Space link, once live]
```

## Post 5

```text
The toolkit is built with its own process. Its specs, tasks and lessons are published as a dataset:
[dataset link, once live]

An article about it:
[article link, once live]
```

## Post 6

```text
Limits: it runs inside Claude Code, and every run uses your own Claude Code plan. It opens and merges PRs with your gh login, so the quickstart uses a throwaway repo. It sends no usage data anywhere. MIT licensed.
```
