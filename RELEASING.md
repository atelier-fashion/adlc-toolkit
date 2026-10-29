# Releasing the ADLC toolkit

A release moves plugin users to a new version. The plugin's `version` is pinned to
`VERSION` (REQ-669 ADR-3), so a merge to `main` alone changes nothing for them. They
move when a release is tagged and they run `claude plugin update`. Symlink-route users
get every merge to `main` the moment they pull, release or not.

Every step here is a **maintainer action**. The version scheme is the
semver-flavored, epoch-based one at the top of [`CHANGELOG.md`](CHANGELOG.md). The
existing release tags are annotated `vX.Y.Z` tags on `main`.

## The release sequence

Do these in order. `X.Y.Z` is the new version throughout.

1. **Start from a green `main`.** Check out `main` at the commit you mean to release,
   with a clean tree, and cut a release branch from it (`release/vX.Y.Z`). Every gate
   passes:

   ```bash
   tools/lint-skills/check.sh
   python3 -m pytest tools -q
   sh partials/tests/run.sh
   node --test 'workflows/tests/*.test.js'
   node --test 'space/tests/*.test.js'
   node space/build.mjs --check                # the Space's toolkit data matches this tree (REQ-670 BR-3)
   ./install.sh --dry-run                      # on a symlink-route machine: zero actions
   ```

   The end-to-end plugin check, `tools/adlc/tests/e2e/plugin-sandbox.sh` (REQ-669
   TASK-131), also **exits 0**. Exit 0 means every check ran and passed. Exit 2 means
   nothing failed but some checks were skipped: the run is incomplete and does not clear
   this gate. An offline run cannot exit 0, because its model and GitHub checks skip.
   Exit 1 is a failure. Those checks need network, `gh` auth and model calls, so the
   script is not part of the default test run. Run it with model access and a throwaway
   repo whose name contains `e2e`, then delete the repo:

   ```bash
   sh tools/adlc/tests/e2e/plugin-sandbox.sh --with-model --throwaway-repo OWNER/adlc-e2e-YYYYMMDD --keep
   ```

2. **Bump `VERSION`** to `X.Y.Z`, the bare version and a newline. Then regenerate the
   Space's toolkit data, which carries the version (REQ-670), so the release commit
   holds the file the Space will serve:

   ```bash
   node space/build.mjs
   ```

3. **Bump the plugin manifest.** Set `version` in
   [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) to the same `X.Y.Z`.
   `.claude-plugin/marketplace.json` carries no version and stays as it is. The
   `plugin-manifest` lint check fails when `plugin.json`'s `version` differs from
   `VERSION`. Then validate both manifests and cross-check them:

   ```bash
   tools/lint-skills/check.sh
   node space/build.mjs --check                # the regenerated Space data matches the bumped VERSION
   claude plugin validate . --strict
   claude plugin validate .claude-plugin/plugin.json --strict
   claude plugin tag --dry-run .               # checks plugin.json and the marketplace entry agree
   ```

   `claude plugin tag` would create an `adlc--vX.Y.Z` tag. Run it with `--dry-run`
   only. The toolkit's release tag is the `vX.Y.Z` tag in step 6.

4. **Write the CHANGELOG entry.** Rename `## [Unreleased]` to
   `## [X.Y.Z] — YYYY-MM-DD`, and open a new empty `## [Unreleased]` above it. The entry
   states the plugin version in its own line, right under the heading:

   ```markdown
   Plugin: `adlc@adlc-toolkit` X.Y.Z (`claude plugin update adlc@adlc-toolkit`).
   ```

   If vendored partials, templates, `ETHOS.md` or the workflow engine changed in the
   release, the entry says which ones, because `/template-drift` reports them `stale` in
   every consumer project until it re-runs `/init` (`/adlc:init` on the plugin install).

5. **Merge to `main`.** Steps 2 to 4 go in one commit on the release branch, merged
   through a pull request with every gate from step 1 green on it.

6. **Tag the merge commit** with an annotated tag, and push it:

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z — <one-line summary of the release>"
   git push origin vX.Y.Z
   ```

7. **Check that `claude plugin update` installs it.** Use a sandbox `HOME` with the
   previous release installed, never your own `~/.claude`:

   ```bash
   claude plugin marketplace update adlc-toolkit
   claude plugin update adlc@adlc-toolkit
   claude plugin list                          # adlc@adlc-toolkit shows X.Y.Z
   ```

   Then start a session in a project that ran `/adlc:init` and run
   `/adlc:template-drift`. Its baseline line names `adlc plugin X.Y.Z`. If either check
   fails, the release is not done: fix forward with a patch release, since the tag is
   already public.

8. **Submit to the Claude directory, or update the listing.** Go to
   [claude.ai/directory/manage](https://claude.ai/directory/manage). The portal needs
   a **paid claude.ai plan**. The first release files a new submission for the `adlc`
   plugin from `atelier-fashion/adlc-toolkit`. Later releases update that listing.

   - **File count.** The directory holds a plugin with more than 512 files for a human
     reviewer. This repo is well over that: `git ls-files | wc -l` printed more than 700
     when this file was written. The hold slows the review; it does not reject the submission.
   - **No top-level `bin/`.** The claude.ai sync path rejects one, so the CLI lives in
     `scripts/`, and the `plugin-manifest` lint check fails on a top-level `bin/`.
     Whether a directory install goes through that sync path at all is open (REQ-669
     OQ-4). After the first directory install, record in REQ-669's `verification.md`
     whether `adlc` reached the session's PATH (BR-20).
   - **Hooks.** The one hook command is a path inside `${CLAUDE_PLUGIN_ROOT}`, which is
     what the directory's checklist asks for. README.md's "What the plugin runs and
     writes" is the description of what it does.

   This step is complete when the submission is **filed** and its reference is
   recorded, not when Anthropic accepts it (REQ-669 BR-15).

9. **Record the submission reference.** The reference exists only after step 8, when
   the release entry is already merged and tagged. So add it in a follow-up commit to
   `main` that edits that release's CHANGELOG entry, on the line after the plugin
   version:

   ```markdown
   Claude directory: <submission reference>, filed YYYY-MM-DD.
   ```

   For a listing update, record the update's reference the same way. For REQ-669's
   first submission, also record it in
   `.adlc/specs/REQ-669-claude-code-plugin-marketplace-install/verification.md`.
   The tag stays where step 6 put it.

## The Hugging Face Space (REQ-670)

The `space/` directory is a static Hugging Face Space that runs `/spec` intake in the
visitor's browser, under the visitor's own Anthropic key. It is rebuilt from a tagged
release, never from an arbitrary commit, so the toolkit version it shows is a real one.
Deploying publishes it, so each step below is a maintainer action, taken with the
maintainer's go-ahead.

1. **Check out the release tag** in a clean clone: `git checkout vX.Y.Z`.
2. **Build and check.** `node space/build.mjs` regenerates `space/toolkit-data.js` from
   `templates/requirement-template.md`, the marked gap rules in `spec/SKILL.md`, the
   budget and redaction chain in `partials/intake.sh`, the install lines in `README.md`
   and `VERSION`. At a tag it must change nothing, because step 2 regenerated it after
   the `VERSION` bump and step 3 checked it:

   ```bash
   node space/build.mjs --check
   node --test 'space/tests/*.test.js'
   ```

3. **Push `space/`'s contents to the Space repository.** The Space is its own git
   repository on Hugging Face (`sdk: static`, card in `space/README.md`). Copy
   everything in `space/` except `build.mjs` and `tests/` to the Space repository's
   root, then commit with the tag in the message and push. The first time, create the
   Space under the owning account or organization first. Keep write access to the Space
   to the maintainers: anyone who can push to it can serve the page that handles
   visitors' keys.
   After the push, confirm that the Space serves the tagged files. Compare a hash of each
   served file with the one at the tag, for example
   `curl -s https://<space-host>/intake.js | shasum -a 256` against `shasum -a 256 space/intake.js`.
4. **Check it live (AC-1).** Open the Space. Before entering a key, confirm that the page
   shows the disclosure and the model id. Then paste the sample transcript from
   `space/sample.js` with a real key, and confirm that the result has every template
   section and at least one gap with a severity and a justification. Download it and
   confirm that the file matches the page. Never record the key anywhere.
5. **Record the URL, once it is live (BR-13).** Add the Space URL to the root
   `README.md` in a commit to `main`. Until the Space is live there is no link to it.
   Add the REQ-671 dataset link to the card the same way, once the dataset is live.
   Before that, the card carries no dataset line at all.

The model is `space/config.json`'s `model`. Changing it is a config edit and a redeploy,
with no code change (BR-9).

## After a release

- When vendored files changed, consumer projects need a re-sync. `/template-drift`
  (`/adlc:template-drift` on the plugin route) lists the `stale` files, and
  re-running `/init` (`/adlc:init` on the plugin install) refreshes them. Re-sync per
  file and byte for byte rather than trusting a summary (LESSON-465).
- The maintainer's own machine is on the symlink route and already runs `main`. Keep
  the plugin off it, or `adlc doctor` reports a doubled install. Test the plugin route
  in a sandbox `HOME`.
