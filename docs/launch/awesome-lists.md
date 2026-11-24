# Community list pull requests: draft

The maintainer opens each pull request by hand, during the launch week, from their own
GitHub account. Nothing in this repository opens them. Their row in the
[launch checklist](../launch-checklist.md) is `awesome-list-prs`.

The lists are not chosen. This page names none of them: a list's name, address and rules
can only be checked on the list itself, and this draft was written without looking any
up. The maintainer chooses the lists by the criteria below and fills in the table.

## Choosing a list

Open a pull request against a community "awesome" list only when all three hold:

1. **It lists Claude Code plugins, skills or tooling.** Its own description says so, and
   it already holds entries of that kind.
2. **It is maintained.** Its recent pull requests are being reviewed and merged.
3. **Its contribution rules allow this entry.** Read its contributing guide before
   writing anything. Check the section the entry belongs in, the entry format, and any
   condition on what may be added, such as a license, a release or an author adding their
   own project. Skip a list whose rules exclude this entry.

Open one pull request per list, and follow the list's own template when it has one.

## The entry

Use the list's own entry format. Where it uses the common one-line form, the entry is:

```markdown
- [ADLC Toolkit](https://github.com/atelier-fashion/adlc-toolkit) - Claude Code skills, agents and templates for spec-driven development. A run takes a change from a validated spec to a reviewed, merged pull request and records a lesson. Installs as a Claude Code plugin.
```

Pull request title:

```text
Add ADLC Toolkit
```

Pull request description:

```text
This adds ADLC Toolkit, an MIT-licensed set of Claude Code skills, agents and templates for spec-driven development. A run takes a change from a validated spec to a reviewed, merged pull request and records what it learned as a lesson. It installs with two commands:

claude plugin marketplace add atelier-fashion/adlc-toolkit
claude plugin install adlc@adlc-toolkit

I maintain the toolkit. I read the contributing guide, and the entry follows its format and goes in the section it names for this kind of entry.
```

Before opening a pull request, check that its last sentence is true for that list, and
change the section or format until it is.

## The lists

One row per chosen list. Add or remove rows as needed. A row's status is `pending` until
its pull request is opened and `done` once it is, as in the launch checklist.

| list | section | entry format checked | status | pull request |
|---|---|---|---|---|
| first list, to be chosen by the maintainer | to be read from the list | no | pending | none |
| second list, to be chosen by the maintainer | to be read from the list | no | pending | none |
| third list, to be chosen by the maintainer | to be read from the list | no | pending | none |
