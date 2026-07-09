# Spec Kit Extensions

Spec Kit (`specify`) extensions hosted by the Resal Marketplace. These hook into the Spec Kit
lifecycle (`/speckit.*` workflow) — distinct from the Claude Code **plugins** under
[`plugins/`](../plugins/), which provide skills/slash-commands.

| Extension | ID | Command | Description |
|-----------|----|---------|-------------|
| Detailed PR Generator | `pr` | `/speckit-pr-generate` | Generate a feature **CHANGELOG** + plain-English **feature-details** doc, include architecture/process diagram assets when relevant, then create/update the PR description under "What have been developed and how to review it". Optional `after_implement` hook. |
| How-To-Test | `how-to-test` | `/speckit-how-to-test-document` | Generate QA-facing How-To-Test manuals after implementation, including diagram assets, screenshots, and API samples, with `/speckit-how-to-test-analyze` for pre-implementation E2E/API/screenshot/diagram readiness. Optional `after_implement` and `after_tasks` hooks. |
| PR Review Processor | `pr-review` | `/speckit-pr-review-process` | Process GitHub PR review comments through an approval-gated classify, fix/reply, push, and resolve workflow. Manual command. |

## Installing an extension

You need the `specify` CLI and a Spec Kit project (a `.specify/` directory).

### Option A — by name, via the catalog

1. Add this repo's extension catalog to your project (or user) config
   `.specify/extension-catalogs.yml`:

   ```yaml
   catalogs:
     - name: resal
       url: https://raw.githubusercontent.com/ResalApps/resal-marketplace/master/extensions/catalog.json
       priority: 1
       install_allowed: true
       description: Resal-hosted Spec Kit extensions
   ```

   …or add it with the CLI:

   ```bash
   specify extension catalog add --name resal --priority 1 --install-allowed \
     --description "Resal-hosted Spec Kit extensions" \
     https://raw.githubusercontent.com/ResalApps/resal-marketplace/master/extensions/catalog.json
   ```

2. Install:

   ```bash
   specify extension add pr
   specify extension add how-to-test
   specify extension add pr-review
   ```

   > Requires both a catalog URL that `specify` can fetch over unauthenticated HTTPS and a
   > published release ZIP (see *Publishing* below). Private GitHub repositories return 404 from
   > `raw.githubusercontent.com` to unauthenticated callers, so use Option B until the catalog and
   > release asset are publicly reachable.

#### Stale catalog → installs an old version / 404 on the release ZIP

`specify` caches the fetched catalog **per project for 1 hour**
(`.specify/extensions/.cache/`, `CACHE_DURATION = 3600`). Right after a new release, an install can
still resolve the *previous* version and fail with, e.g.:

```text
Downloading Detailed PR Generator v1.0.0...
Error: Failed to download extension from .../releases/download/pr-v1.0.0/pr.zip: HTTP Error 404: Not Found
```

That's the client cache, not the catalog — the published [`catalog.json`](catalog.json) already points
at the new release. Clear the cache and retry (run from the Spec Kit project where you installed):

```powershell
Remove-Item -Recurse -Force .specify\extensions\.cache   # bash: rm -rf .specify/extensions/.cache
specify extension add pr
```

It should then download the current version. Alternatively, just wait up to an hour for the cache to
expire. There is no `--refresh` flag on `extension add` today.

### Option B — local dev install from a clone (works today)

Clone this repo, then point `--dev` at the extension directory (an **external** path, not inside the
target project's `.specify/extensions/`):

```bash
git clone https://github.com/ResalApps/resal-marketplace
cd <your-spec-kit-project>
specify extension add --dev /path/to/resal-marketplace/extensions/pr
```

PowerShell example from a local Windows clone:

```powershell
specify extension add --dev "D:\Projects\Resal\resal-marketplace\extensions\pr"
specify extension add --dev "D:\Projects\Resal\resal-marketplace\extensions\how-to-test"
specify extension add --dev "D:\Projects\Resal\resal-marketplace\extensions\pr-review"
```

> ⚠️ Never run `specify extension add --dev` against a path that is already inside the target
> project's `.specify/extensions/` — the CLI deletes the destination before copying, which wipes the
> source when source == destination. Always install from an external clone path.

### Option C — from a release ZIP URL

```bash
specify extension add --from https://github.com/ResalApps/resal-marketplace/releases/download/pr-v1.0.0/pr.zip
```

## Using the `pr` extension

After install, the command is available as `/speckit-pr-generate`. It registers an **optional**
`after_implement` hook (Spec Kit prompts before running it), and can be run manually anytime —
typically once the PR exists, to inject the feature-details into its description. See
[`pr/README.md`](pr/README.md).

When the implementation changed architecture or process flow, the command also generates HTML and
PNG diagram assets through the `architecture-diagram` and `process-flow-diagram` skills.

## Using the `how-to-test` extension

After install, the manual command is available as `/speckit-how-to-test-document`. It registers an
**optional** `after_implement` hook, which is the recommended supported phase because implementation
completion validation has passed. If a target project has a review hook, run it after that review;
otherwise run it before PR handoff or human QA review.

The same extension also provides `/speckit-how-to-test-analyze` as an **optional** `after_tasks`
readiness hook for missing E2E/API/screenshot/diagram tasks. See [`how-to-test/README.md`](how-to-test/README.md).
The readiness hook now also looks for missing diagram-generation tasks when architecture or workflow
changes need documentation visuals.

## Using the `pr-review` extension

After install, the command is available as `/speckit-pr-review-process`. It is intentionally manual, because
PR review comments only exist after reviewers or bots leave feedback on an open PR. The
`/devtools:pr-review` skill remains available for the same workflow outside Spec Kit. See
[`pr-review/README.md`](pr-review/README.md).

## Publishing (maintainers)

### Automated — CI/CD (default)

Releases are cut automatically by the [`Release extensions`](../.github/workflows/release-extensions.yml)
GitHub Actions workflow. It runs **only when files under `extensions/` change** on `master`, and for
each changed `extensions/<id>/` it:

1. **Bumps the version** — patch by default. To control it, either edit `version:` in
   `extensions/<id>/extension.yml` yourself (CI honours an already-ahead version verbatim) or run the
   workflow manually (Actions → *Release extensions* → *Run workflow*) and pick `bump`
   (patch/minor/major) or `set_version`.
2. **Updates [`catalog.json`](catalog.json)** — sets that extension's `version` and `download_url`
   (and `updated_at`). A **brand-new** `extensions/<id>/` folder gets a full catalog entry generated
   automatically (the `pr` entry is the template), so adding an extension is enough to publish it.
3. **Packages** `dist/<id>.zip` via [`scripts/package.sh`](scripts/package.sh).
4. **Commits** the version/catalog changes back to `master` with `[skip ci]` (so it doesn't loop).
5. **Creates a GitHub release** tagged `<id>-v<version>` with the ZIP attached, and uploads the ZIP as
   a workflow artifact.

So the normal flow is just: edit the extension under `extensions/<id>/`, push to `master`, done.

### Manual (fallback)

The same packaging can be done by hand if needed:

```bash
extensions/scripts/package.sh pr           # builds dist/pr.zip
gh release create pr-v1.0.0 dist/pr.zip \
  --title "pr extension v1.0.0" \
  --notes "Detailed PR Generator extension v1.0.0"
```

The release tag (`pr-v1.0.0`) and asset name (`pr.zip`) must match the `download_url` in
[`catalog.json`](catalog.json). Bump the version in `pr/extension.yml`, `pr/CHANGELOG.md`, and
`catalog.json` together, then cut a new release.
