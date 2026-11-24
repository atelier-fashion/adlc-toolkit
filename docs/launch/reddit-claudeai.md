# r/ClaudeAI post: draft

The maintainer posts this by hand, during the launch week, from their own Reddit
account. Nothing in this repository posts it. Its row in the
[launch checklist](../launch-checklist.md) is `post-reddit-claudeai`.

Before posting:

- Read the subreddit's current rules on self-promotion and post flair, and follow them.
  This draft was written without looking them up.
- Replace each named slot in square brackets, such as `[Space link, once live]`, with the
  address in the link column of that item's checklist row. The row is `live` by then,
  because this post depends on it.
- The draft states no duration. State one only if the quickstart's `quickstart-verified`
  line records a release and a measured time, and then use that figure.
- Add no figures about the project: no stars, no counts of users or installs.

## Title

```text
ADLC: Claude Code skills that take a change from a written spec to a merged PR, and record what the run learned
```

## Body

```markdown
I maintain ADLC, a set of Claude Code skills, agents and templates for spec-driven development. It is open source under the MIT license: https://github.com/atelier-fashion/adlc-toolkit

A run produces three things you can read in your own repo:

- **a validated spec**: `/adlc:spec` turns your request into a requirement under `.adlc/specs/`, with business rules and acceptance criteria, and sorts it into a lite lane for small changes or a full lane for the rest;
- **a reviewed PR**: `/adlc:proceed` implements the requirement, reviews its own diff, has review agents read it (one pass on the lite lane, a panel on the full lane), then opens the pull request and merges it;
- **a captured lesson**: `/adlc:wrapup` writes what the run learned under `.adlc/knowledge/lessons/`, or one line saying why there was nothing to keep. Later specs and reviews read those lessons.

On the full lane, `/adlc:proceed` also validates the spec, writes an architecture doc and breaks the work into tasks before it writes code. On the lite lane it skips those three steps.

**Install**, in your terminal:

    claude plugin marketplace add atelier-fashion/adlc-toolkit
    claude plugin install adlc@adlc-toolkit

Then start a new Claude Code session. Every skill is namespaced on this install: `/adlc:init`, `/adlc:spec`, `/adlc:proceed`.

**Quickstart.** This page goes from that install to a merged pull request in a small sample project, in eight typed steps: https://github.com/atelier-fashion/adlc-toolkit/blob/main/docs/quickstart.md

It needs git, the GitHub CLI signed in, and Claude Code. It creates a private throwaway repo in your account, and the page shows how to delete it.

**Without installing.** A Hugging Face Space runs the spec step in your browser: paste meeting notes and it returns a draft requirement and a list of gaps, using your own Anthropic API key. [Space link, once live]

**The toolkit's own record.** The toolkit is built with its own process. Its specs, tasks and lessons are published as a dataset: [dataset link, once live]. The article about it: [article link, once live]

**Limits**

- It runs inside Claude Code. It is not a standalone tool or a hosted service.
- Every run uses your own Claude Code plan.
- `/adlc:proceed` pushes branches, and opens and merges pull requests, with your `gh` login. Try it on a throwaway repo first, as the quickstart does.
- Delegating bulk reads to another model is off by default, and the plugin install does not include it.
- The toolkit sends no usage data anywhere.

I would like to hear where the process gets in your way, and which step you would cut.
```
