---
title: ADLC Spec Intake
emoji: 📝
colorFrom: indigo
colorTo: gray
sdk: static
app_file: index.html
pinned: false
license: mit
short_description: Turn meeting notes into a draft requirement and a gap list
---

# ADLC Spec Intake

Paste meeting notes, a chat transcript or a ticket dump, and get back:

- a draft `requirement.md` in the [ADLC toolkit](https://github.com/atelier-fashion/adlc-toolkit)'s requirement template, and
- a list of what your notes don't answer. Each gap is a specific question, marked **blocking** or **assumption**, with a one-sentence reason.

This is the `/spec` intake step from the toolkit, the one step that needs nothing but text and a model.
The toolkit's template, its gap rules and its source budget (8000 lines) are built into this page from a tagged toolkit release.

## Your key and your text

- The page calls Anthropic's API **from your browser, with your own API key**. You pay for the call, and nothing passes through a server of ours.
- **Nothing is stored**: no key, no text and no result. There are no logs, no browser storage and no analytics.
- Some common credential formats are removed from your text before it is sent. Other secrets are not, so check what you paste.
- Consider a separate key with a low spend limit, and revoke it when you are done.
- Don't paste anything you may not share with Anthropic.

With no key, the page shows a sample run on a synthetic transcript.

## Carry on locally

Install the toolkit as a Claude Code plugin:

```
claude plugin marketplace add atelier-fashion/adlc-toolkit
claude plugin install adlc@adlc-toolkit
```

Then, in your repository, run `/adlc:spec --intake notes.md`.
