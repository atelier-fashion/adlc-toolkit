# Presets

Stack-shaped starter configs for `.adlc/config.yml`. Each preset captures a common combination of platforms, deploy targets, and CI patterns. Pick the one closest to your stack, copy it into your repo, and replace the placeholder values.

## Available presets

| File | Stack |
|------|-------|
| [ios-firebase-cloudrun.yml](ios-firebase-cloudrun.yml) | iOS app + Firebase (Auth/Firestore) + Cloud Run backend(s), GitHub Actions CI/CD with staging-first promotion |

## How to use a preset

From inside the repo where you're running `/init` (`/adlc:init` on the plugin install):

```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
cp "$ADLC_TOOLKIT_ROOT/presets/ios-firebase-cloudrun.yml" .adlc/config.yml
$EDITOR .adlc/config.yml
```

The first line is the toolkit's canonical root line. It sets `ADLC_TOOLKIT_ROOT` to the installed toolkit: on the symlink route the clone that `install.sh` links into `~/.claude`, and on the plugin route the plugin's cache copy (read from `~/.claude/adlc/plugin-root`, which the plugin's session hook writes).

Replace every `<placeholder>` with a real value (project name, GCP project IDs, repo paths, device names). Don't leave placeholders in — skills will fail loudly when they try to use them, but it's faster to just fill them in up front.

## What's a preset, exactly

A preset is **stack shape, not company configuration**. It declares:

- Which platforms are in play (`stack.frontends: [ios]`, `stack.backends: [cloud-run]`)
- Which sections are populated (e.g., `ios:` and `gcp:` blocks present, with placeholder values)
- Sensible defaults (e.g., `gcp.default_region: us-central1`, `ios.derived_data_clean: true`)
- Example shape for the `services:` block

It does **not** contain:

- Real project IDs, repo names, account IDs, secrets
- Specific device names — leave those as placeholder strings
- Anything proprietary to a specific company's setup

## Adding a new preset

If you have a stack combination not covered here, drop a new YAML file in this directory and update the table above. Naming convention: `<frontend>-<auth-or-data-layer>-<backend-platform>.yml`. Examples:

- `web-supabase-vercel.yml`
- `mobile-rn-firebase-aws.yml`
- `none-postgres-k8s.yml`

Open a PR against the canonical `adlc-toolkit` upstream — presets benefit from being shared.
