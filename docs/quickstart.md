# Quickstart: from install to a merged pull request

This page takes you from installing the ADLC plugin to a merged pull request in a small
sample project. `/adlc:init` sets the project up, `/adlc:spec` writes a requirement for
one small change, and `/adlc:proceed` builds the change, reviews it, opens a pull
request, merges it and records what the run learned.

You type eight things in all: five shell commands, one reply and two prompts. Each one is
in its own box below, followed by what you should see.

<!-- quickstart-verified: none -->
Timing: this page has not been measured against a release yet, so it gives no time for a run.

## What you need

- git
- a GitHub account, with the GitHub CLI `gh` installed and signed in to it (`gh auth status` shows the account)
- Claude Code, signed in

It needs no cloud project, no preset, no deploy target and no delegation setup.

The toolkit's own scripts run with `python3` and a POSIX shell. On macOS the Command Line
Tools that provide git provide both.

The quickstart creates a private repository named `adlc-quickstart` in your GitHub
account, and a directory of the same name where you run step 3. [Clean up](#clean-up)
shows how to delete both. The run counts toward your Claude Code usage, like any other
session.

## The eight steps

### 1. Add the marketplace

In your terminal:

<!-- quickstart-step: shell -->
```sh
claude plugin marketplace add atelier-fashion/adlc-toolkit
```

Claude Code adds this repository as a plugin marketplace named `adlc-toolkit` and exits
without an error. It keeps a copy of the repository on your machine, which step 3 uses.

### 2. Install the plugin

<!-- quickstart-step: shell -->
```sh
claude plugin install adlc@adlc-toolkit
```

Claude Code installs the `adlc` plugin from that marketplace and exits without an error.
On this install every skill name starts with `adlc:`, as in `/adlc:init`.

### 3. Make the sample project

Run this in the directory that should hold the new project. The directory your terminal
starts in is fine.

<!-- quickstart-step: shell e2e=existing-repo -->
```sh
sh ~/.claude/plugins/marketplaces/adlc-toolkit/examples/quickstart/new-project.sh adlc-quickstart
```

The script copies the sample project into a new directory, `adlc-quickstart`, and makes
the first commit on `main`. The sample is a greeter written in POSIX `sh`: `greet.sh`, its
test `tests/greet.test.sh`, and a `README.md` that states the project's name, purpose,
stack, scope and layout. Then the script runs
`gh repo create adlc-quickstart --private --source adlc-quickstart --push`, and `gh`
reports that it created the repository and pushed to it. The last line is:

```text
new-project: adlc-quickstart is ready. Next: cd adlc-quickstart
```

The script changes nothing and says why when `adlc-quickstart` already exists, when git
or `gh` is missing, when git has no name and email, or when `gh` is not signed in.

### 4. Go into the project

<!-- quickstart-step: shell -->
```sh
cd adlc-quickstart
```

Nothing is printed.

### 5. Start Claude Code with `/adlc:init`

<!-- quickstart-step: shell e2e=init-prompt -->
```sh
claude "/adlc:init"
```

This starts Claude Code in the project with `/adlc:init` as its first prompt. If the
session opens without running it, see [What has not been checked](#what-has-not-been-checked).

Claude Code may first ask whether you trust the files in this folder. You made the folder
in step 3, so choose yes. Until `/adlc:init` has written the project's allowlist, Claude
Code also asks before it runs a command or writes a file. This is a throwaway project made
for this page, so approve each one.

`/adlc:init`'s instructions tell it to read `README.md`, take the project's name, what it
does, its stack, its scope and its layout from there, and ask you to confirm them instead
of asking for each one. Later in the same run, its instructions ask whether this repo
shares features with other repos, which ADLC calls sibling repos.

### 6. Answer `/adlc:init`

When `/adlc:init` shows what it read from `README.md` and asks you to confirm it, reply:

<!-- quickstart-step: answer -->
```text
Yes, use what you read in README.md as it is. This repo has no sibling repos, so skip the cross-repo config. When you finish, commit what you wrote and push it to main.
```

This one reply confirms the five facts and answers the sibling-repos question before it
is asked. `/adlc:init` then creates `.adlc/`, with the project context, the templates and
the knowledge directories, and writes `.claude/settings.json`, `AGENTS.md` and
`CLAUDE.md`. It ends with a summary of what it made and of the ADLC workflow. If it asks
the sibling-repos question again anyway, answer no.

The last sentence of the reply matters. `/adlc:proceed` starts its branch from `main` on
GitHub, so the project setup has to be pushed there before step 8. `git status` should
then show nothing to commit.

### 7. Ask for the change

<!-- quickstart-step: prompt -->
```text
/adlc:spec Add a --name option to greet.sh so that "sh greet.sh --name Ada" prints "Hello, Ada", and add one line to README.md that documents it
```

`/adlc:spec` writes a requirement under `.adlc/specs/`, shows it to you, and prints its
lane on one line, which should start `Lane: lite (triaged)`. The change touches
`greet.sh`, `README.md` and the test, and changes no schema, dependency or CI file, so
`/adlc:spec`'s triage rules put it in the lite lane. Its instructions ask clarifying
questions only when a request is vague or ambiguous, and this one names the file, the
option, the output and the README line.

It ends by naming the next step, `/adlc:proceed` with the new requirement's id. The id
comes from a counter on your machine, so it may be `REQ-001` or another number. It may
print the skill name without the `adlc:` prefix; type it with the prefix.

### 8. Run the pipeline

Type this, with `REQ-xxx` replaced by the id `/adlc:spec` printed in step 7, for example
`/adlc:proceed REQ-001`:

<!-- quickstart-step: prompt e2e=req-id -->
```text
/adlc:proceed REQ-xxx
```

`/adlc:proceed` is written to run to the end without asking you anything. For a lite-lane
requirement it skips spec validation, architecture and the task breakdown. It works in
its own git worktree on a `feat/` branch: it implements the change and its test, runs one
review pass, checks that the diff stayed inside the lite lane, pushes the branch, opens a
pull request, and merges it itself. It then runs `/adlc:wrapup`, which writes a lesson
under `.adlc/knowledge/lessons/` or gives a one-line reason for writing none, starting
`NO_ENTRY:`. The run's final report starts with `merged`.

Claude Code may still ask you to approve a command, such as the merge: the settings
`/adlc:init` wrote keep one-way moves on Claude Code's ask list on purpose. Approve them for
this project. If the run stops with a question of its own, it is at one of the halt points
its instructions name, such as a question from its review or a merge conflict, and it says
which.

## Clean up

These are not part of the eight steps. Leave Claude Code first.

To see the merged pull request, run `gh pr list --state merged` in `adlc-quickstart`, or
`gh repo view --web` to open the repository in your browser.

To delete the GitHub repository, run this in `adlc-quickstart`. `gh` asks you to confirm
first. If it says it needs the `delete_repo` scope, run `gh auth refresh -s delete_repo`,
then run it again. Afterwards, `gh auth refresh -r delete_repo` removes that scope again.
Or delete the repository from its Settings page on github.com instead.

```sh
gh repo delete
```

Then delete the local directory:

```sh
cd .. && rm -rf adlc-quickstart
```

Keep the plugin for your own projects, or remove it with
`claude plugin uninstall adlc@adlc-toolkit`.

## What has not been checked

The `quickstart-verified` line at the top of this page reads `none`: no run of this page
against a release is recorded. While it does:

- The page gives no time for a run.
- What `/adlc:init` asks comes from its instructions, not from a recorded run: that it asks
  you once to confirm what it read in `README.md`, and that the reply in step 6 also
  settles its sibling-repos question.
- No recorded run shows that `claude "/adlc:init"` starts a session with `/adlc:init` as
  its first prompt. If the session opens without running it, type `/adlc:init` at the
  prompt.
- No recorded run shows that the reply in step 6 gets the project setup committed and
  pushed. If `git status` shows setup files still uncommitted after step 6, run
  `git add -A && git commit -m "adlc init" && git push` before step 7.
