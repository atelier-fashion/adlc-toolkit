---
name: canary
description: Canary deployment with smoke tests — deploy to a zero-traffic revision, run health checks, and promote on success. Use when the user says "canary deploy", "deploy with canary", "smoke test the deploy", or wants deployment confidence before going live.
argument-hint: Optional repo id (from .adlc/config.yml) or service name — auto-detected from current worktree if omitted
---

# /canary — Canary Deployment with Smoke Tests

You are deploying code through a canary process: deploy a zero-traffic revision, verify it works, then promote to live traffic. This prevents broken deploys from reaching users.

## Ethos

!`cat .adlc/ETHOS.md 2>/dev/null || cat ~/.claude/skills/ETHOS.md 2>/dev/null || echo "No ethos found"`

## Context

- Current directory: !`pwd`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- GCP project: !`gcloud config get-value project 2>/dev/null || echo "No GCP project configured"`
- Active Cloud Run services: !`gcloud run services list --format="table(SERVICE,REGION,URL)" 2>/dev/null || echo "gcloud not configured"`

## Input

Target: $ARGUMENTS

## Prerequisites

1. `gcloud` CLI must be authenticated and configured with the correct project
2. The service must already exist on Cloud Run (this skill deploys revisions, not new services)
3. A Docker image must be available (either build locally or use the latest from Artifact Registry)

## Service Resolution

Service configuration lives in **`.adlc/config.yml`** in the primary repo under a `services:` block, keyed by repo id. This is the single source of truth — no service names, regions, or image paths should be hardcoded in this skill.

**Expected config shape** (primary repo `.adlc/config.yml`):

```yaml
repos:
  api:
    path: ../api
  web:
    path: ../web

services:
  api:
    cloud_run_service: api
    region: us-central1
    image_path: us-central1-docker.pkg.dev/<gcp-project>/api/api
  web:
    cloud_run_service: web
    region: us-central1
    image_path: us-central1-docker.pkg.dev/<gcp-project>/web/web
```

**Resolution order**:
1. If `$ARGUMENTS` is a repo id defined under `repos:` in the primary's config, look up `services[<repo-id>]` and use that. If the repo id has no `services:` entry, stop and ask the user to add one.
2. If `$ARGUMENTS` is a Cloud Run service name already (e.g., the user passed `api` and it matches `services.*.cloud_run_service`), use that entry.
3. If no argument: detect which repo the current cwd is inside by walking up to find a git root and matching it against `repos[*].path` (resolve each to an absolute path first). Then look up its service.
4. If the project has no `.adlc/config.yml` (single-repo legacy setup) AND the current repo has a top-level `Dockerfile` and a single Cloud Run service name that matches the repo basename, fall back to auto-detection: service name = repo basename, region = `us-central1`, image path = `$(gcloud config get-value project)/<service>`. Surface this fallback in the logs so the user knows it's being inferred.
5. If none of the above resolves, stop with a clear error: "Could not determine Cloud Run service. Add a `services:` block to `.adlc/config.yml` or pass the service name as an argument."

**Operating worktree**: if the resolved repo has a feature-branch worktree (e.g., `.worktrees/REQ-xxx`) that matches the current `/proceed` pipeline, build from inside that worktree. Otherwise build from the repo's main checkout. The caller can also pass the worktree path explicitly. (As of REQ-380, `/canary` is no longer auto-invoked from `/proceed` — operators run it manually when a production canary is needed.)

## Instructions

### Step 1: Build and Push Image

1. Determine the image tag: use the current git SHA (`git rev-parse --short HEAD`)
2. Build the Docker image:
   ```bash
   docker build -t <IMAGE_PATH>:canary-<SHA> ./<subdir if needed>
   ```
3. Push to Artifact Registry:
   ```bash
   docker push <IMAGE_PATH>:canary-<SHA>
   ```

If the user says "use latest" or the image was already built by CI, skip the build and use the `:latest` tag from Artifact Registry.

### Step 2: Deploy Canary Revision (Zero Traffic)

Deploy a new revision that receives NO traffic:

```bash
gcloud run deploy <SERVICE_NAME> \
  --image=<IMAGE_PATH>:canary-<SHA> \
  --region=us-central1 \
  --no-traffic \
  --tag=canary \
  --format="json"
```

This creates a tagged revision accessible at `https://canary---<SERVICE_NAME>-<hash>.a.run.app` without affecting production traffic.

Capture the canary URL from the output.

### Step 3: Health Checks

Run basic health checks against the canary URL:

1. **Liveness**: `curl -s -o /dev/null -w "%{http_code}" <CANARY_URL>/health`
   - Expected: `200`
   - Retry up to 3 times with 5-second intervals (cold start grace period)

2. **Readiness**: `curl -s -o /dev/null -w "%{http_code}" <CANARY_URL>/api/health`
   - Expected: `200` (or the service's documented readiness endpoint)

If health checks fail after 3 retries, go to Step 6 (Rollback).

### Step 4: Smoke Tests

Run smoke tests against the canary URL. Load test definitions from the **primary repo's** `.adlc/context/smoke-tests.md` if it exists, otherwise use defaults. In cross-repo mode the primary's smoke-tests.md is the authoritative source for every service — sibling repos do not need their own copy.

**Default smoke tests** (API services):
```
GET  /health              -> 200
GET  /api/health          -> 200
```

**Custom smoke tests** (from `.adlc/context/smoke-tests.md`):
Each entry should specify: method, path, expected status, optional body pattern.

For each test:
```bash
RESPONSE=$(curl -s -w "\n%{http_code}" <CANARY_URL><PATH>)
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)
```

Report results:
```
## Smoke Test Results

| Test | Method | Path | Expected | Actual | Status |
|------|--------|------|----------|--------|--------|
| Health | GET | /health | 200 | 200 | PASS |
| API Health | GET | /api/health | 200 | 200 | PASS |

Result: 2/2 passed
```

If any test fails, go to Step 6 (Rollback).

### Step 5: Promote to Production

All checks passed — promote the canary revision to 100% traffic:

```bash
gcloud run services update-traffic <SERVICE_NAME> \
  --region=us-central1 \
  --to-tags=canary=100
```

Verify promotion:
```bash
gcloud run services describe <SERVICE_NAME> \
  --region=us-central1 \
  --format="table(status.traffic[].percent,status.traffic[].revisionName,status.traffic[].tag)"
```

Confirm canary revision is now serving 100% traffic.

Remove the canary tag (clean up):
```bash
gcloud run services update-traffic <SERVICE_NAME> \
  --region=us-central1 \
  --remove-tags=canary
```

Report:
```
Canary promoted to production.
Service: <SERVICE_NAME>
Revision: <REVISION_NAME>
URL: <PRODUCTION_URL>
All smoke tests passed.
```

### Step 6: Rollback (Failure Path)

If health checks or smoke tests fail:

1. Delete the canary revision tag (so it's not addressable):
   ```bash
   gcloud run services update-traffic <SERVICE_NAME> \
     --region=us-central1 \
     --remove-tags=canary
   ```

2. Report the failure:
   ```
   CANARY FAILED — rolled back.
   Service: <SERVICE_NAME>
   Failed revision: canary-<SHA>

   Failures:
   - [list failed health checks or smoke tests]

   Production traffic is unchanged — still serving the previous revision.
   ```

3. Suggest next steps:
   - Check Cloud Run logs: `gcloud run services logs read <SERVICE_NAME> --region=us-central1 --limit=50`
   - Investigate the failure locally
   - Fix and re-run `/canary`

### Step 7: Update Pipeline State (if in /proceed context)

If `pipeline-state.json` exists for the current REQ:
1. Add a `canary` entry to `phaseHistory` with the result (passed/failed)
2. Include: service name, revision, smoke test results, canary URL

## Smoke Test Configuration

To customize smoke tests, create `.adlc/context/smoke-tests.md` with this format:

```markdown
# Smoke Tests

## api
| Method | Path | Expected Status | Body Pattern |
|--------|------|-----------------|--------------|
| GET | /health | 200 | |
| GET | /api/health | 200 | |
| GET | /api/v1/config | 200 | "version" |

## web
| Method | Path | Expected Status | Body Pattern |
|--------|------|-----------------|--------------|
| GET | / | 200 | |
| GET | /api/health | 200 | |
```

The keys above (`api`, `web`) are repo ids — the same ids you used under `repos:` in `.adlc/config.yml`. `/canary` looks up the smoke tests for the service it's deploying by matching repo id.

## What This Skill Does NOT Do

- It does not create new Cloud Run services — the service must already exist
- It does not handle iOS deployments — TestFlight is already a canary-like process
- It does not modify CI/CD workflows — it's a manual deployment confidence tool
- It does not handle database migrations — run those separately before deploying
