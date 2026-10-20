# Set up a Spec Kit project

Sanduq [extensions](../reference/glossary.md#extension) install into a Spec Kit project. This page
creates one, or prepares an existing repository, and registers the Sanduq
[catalog](../reference/glossary.md#catalog). Skip it if you only use
[portable skills](../scenarios/skills-only.md).

## 1. Install the tools

Install Spec Kit, Python and Git. The [prerequisites](prerequisites.md) page lists versions and the
install command for your OS.

```bash
specify --version
python --version
git --version
```

## 2. Initialize the project

Run this in your repository root. Pick the integration for your [host](../reference/glossary.md#host):

```bash
specify init --here --integration codex
# or, for Claude Code:
specify init --here --integration claude
```

For an existing repository, commit or back up first. Back up `.specify/`, your agent configuration
and `.github/workflows/`. Use `specify init --force` only after you have read what it overwrites.
Run `git diff` afterwards and keep your constitution, CI files and project metadata.

## 3. Register the Sanduq catalog

```bash
specify extension catalog add --name sanduq --priority 1 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

The catalog lists published versions. `catalog add` writes `.specify/extension-catalogs.yml`. While
that file exists, Spec Kit reads only the catalogs it lists, so after this command Sanduq is your
only catalog.

### If you keep Spec Kit's default catalogs

If that file also lists Spec Kit's `default` and `community` catalogs, the catalog with the
**lowest** priority number wins when two catalogs publish the same ID. The community catalog
(priority 2) publishes unrelated extensions called `scope` ("Spec Scope") and `memory` ("Spec Kit
Memory") for discovery only. With Sanduq at a higher number, `specify extension add scope` or
`add memory` refuses to install, `search` and `info` show the other product, and
`specify extension update` skips the extension without an error.

Priority 1 keeps Sanduq ahead of the community catalog, so install and update both find Sanduq's
package. If you registered Sanduq with a higher number (older guides used 10), register it again:

```bash
specify extension catalog remove sanduq
specify extension catalog add --name sanduq --priority 1 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

`specify extension info memory` shows which product you get: Sanduq's is "Sanduq Memory".

For a one-off install, use the extension's `download_url` from the [catalog](../../catalog.json),
for example `specify extension add memory --from https://github.com/samykabu/sanduq/releases/download/memory-v<version>/memory.zip`.
Spec Kit asks you to confirm. `update` still reads the catalogs, so it keeps skipping that extension.

The Workflow installer is not affected. It installs Scope from Sanduq's release and refuses a
package with the same ID from another repository. `SPECKIT_CATALOG_URL` replaces every catalog,
Sanduq's too.

## 4. Add extensions

You are ready to add extensions. Choose a path:

- One extension: [one-extension scenario](../scenarios/one-extension.md).
- A set of extensions: [à-la-carte scenario](../scenarios/a-la-carte.md) and the
  [set recipes](install-by-host.md#set-recipes).
- The managed Workflow: [managed-workflow scenario](../scenarios/managed-workflow.md).

## Limits

- Spec Kit does not install an extension's dependencies for you. See
  [who enforces dependencies](prerequisites.md#who-enforces-dependencies).
- Installing an extension does not [enable](../reference/glossary.md#enabled) its process. Run its
  init command.
