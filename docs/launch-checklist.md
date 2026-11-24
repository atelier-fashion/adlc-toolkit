# Launch checklist

The toolkit launches in one coordinated launch week, after the plugin release, the
Hugging Face Space, the dataset and the article are all live (maintainer, 2026-11-23).
No post goes out and no pull request to a community list is opened before then.

This page sequences that launch. Every step on it is the maintainer's, done by hand.
Nothing in this repository posts, submits or publishes anything on its behalf. The posts
are drafted under [`launch/`](launch/), and the maintainer posts each one by hand.

This table is the one place launch progress is written down. Other pages name a row's id
instead of restating its status.

## Statuses

- `pending`: not started, or not yet checked.
- `ready`: built and checked, and waiting only on a dependency or on the launch week.
- `live`: published and reachable by anyone. The row's link is then the address where it
  is live.
- `done`: a one-off action completed, such as a submission filed, a post made or a
  schedule set.

A row may be `live` or `done` only when every row it depends on is `live` or `done`.
Before a row is `live`, its link is a file in this repository or `none`, never an
address.

The README may link the Space, the dataset or the article only when that row is `live`.
The `readme-first-screen` lint reads this table and fails a README that links one early.

## The checklist

Rows are in dependency order: a row depends only on rows above it. `depends on` lists ids,
or `none`.

| id | item | depends on | owner | status | link |
|---|---|---|---|---|---|
| plugin-release | Plugin release (REQ-669): cut and tag the release by `RELEASING.md` steps 1 to 7, ending with `claude plugin update` installing it in a sandbox `HOME` | none | maintainer | pending | [RELEASING.md](../RELEASING.md) |
| directory-submission | Claude directory submission (REQ-669): file it and record its reference, `RELEASING.md` steps 8 and 9. Filing completes it; acceptance is not waited for | plugin-release | maintainer | pending | [RELEASING.md](../RELEASING.md) |
| space | Hugging Face Space (REQ-670): deploy `space/` from the release tag under the owning account, run the live check, and record its address in the README and in this row | plugin-release | maintainer | pending | [RELEASING.md](../RELEASING.md#the-hugging-face-space-req-670) |
| dataset | Hugging Face dataset (REQ-671): export from the release, read the scrub report, publish, run the at-publish checks, and record its address in the README and in this row | plugin-release | maintainer | pending | [tools/dataset/README.md](../tools/dataset/README.md) |
| article | Companion article (REQ-671): publish the draft on the Hugging Face blog with every number from `tools/dataset/article_numbers.py` run against the published revision, with its Space, dataset and install links, and record its address in the README and in this row | plugin-release, space, dataset | maintainer | pending | [article draft](../tools/dataset/article/draft.md) |
| readme-quickstart-verified | README and quickstart verified on the release (REQ-672): run the quickstart end to end in a sandbox `HOME` with a model and a throwaway repo, then set the page's `quickstart-verified` line to the release, the minutes and the date | plugin-release | maintainer | pending | [quickstart.md](quickstart.md) |
| demo-recording | Demo recording (REQ-672): record the quickstart against the release with `tools/launch/record_demo.py`, check it, commit `docs/demo.cast` and `docs/demo.gif` together, and show it on the README's first screen | readme-quickstart-verified | maintainer | pending | none |
| adoption-snapshot-scheduled | Adoption snapshot (REQ-672): run `tools/launch/adoption_snapshot.py` once by hand with the Space and dataset ids, then schedule it at least weekly, so a baseline row exists before the first post | space, dataset | maintainer | pending | none |
| post-show-hn | Show HN post, posted by hand | plugin-release, space, dataset, article, demo-recording, adoption-snapshot-scheduled | maintainer | pending | [show-hn.md](launch/show-hn.md) |
| post-reddit-claudeai | r/ClaudeAI post, posted by hand | plugin-release, space, dataset, article, demo-recording, adoption-snapshot-scheduled | maintainer | pending | [reddit-claudeai.md](launch/reddit-claudeai.md) |
| post-x | X thread, posted by hand | plugin-release, space, dataset, article, demo-recording, adoption-snapshot-scheduled | maintainer | pending | [x-thread.md](launch/x-thread.md) |
| awesome-list-prs | Pull requests adding the toolkit to community lists of Claude Code plugins and skills, opened by hand, on lists chosen by the criteria in the draft | plugin-release, space, dataset, article, demo-recording, adoption-snapshot-scheduled | maintainer | pending | [awesome-lists.md](launch/awesome-lists.md) |

A post row moves to `ready` once the maintainer has read its draft and agrees with every
sentence in it, and to `done` once it is posted.

## What needs the maintainer's word

Each of these spends the maintainer's model plan, uses their accounts, or speaks for the
project in public. Nothing here is run or posted without the maintainer saying so:

- a real quickstart run, from plugin install to a merged pull request, against the
  release, and the time it took (`readme-quickstart-verified`);
- the demo recording, which runs the same steps with a model (`demo-recording`);
- a real adoption snapshot against the GitHub and Hugging Face APIs, and its schedule
  (`adoption-snapshot-scheduled`);
- every post and every pull request to a community list (`post-show-hn`,
  `post-reddit-claudeai`, `post-x`, `awesome-list-prs`);
- the release, the directory submission, and publishing the Space, the dataset and the
  article, by the steps their rows link.

## Checking this table

```sh
python3 tools/launch/launch_checklist.py
```

It prints each row and `launch-checklist: N rows, 0 violations`, and exits 0. It exits 1
and names each violation when a required id is missing, a status is not one of the four
above, a row depends on an id that is not above it, a link names a file that does not
exist, an address appears before its row is `live`, or a post row's draft is missing. It
exits 2 when it cannot read the file or finds no row.
