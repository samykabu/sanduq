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
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

The catalog lists published versions. Priority 10 puts it ahead of other catalogs, because one other
catalog also publishes an extension called `scope`.

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
