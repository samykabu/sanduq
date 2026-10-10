# Spec Kit extension source index

Eight extensions supply the managed workflow and independently usable documentation, QA, Project,
PR, illustration, and Memory processes. Use [setup](../docs/getting-started.md) to install them and
the [extension guide](../docs/extensions.md) for every public command and its practical example.

## Versions and command coverage

| Extension | Source version | Commands |
| --- | --- | ---: |
| [assure](assure/README.md) | 2.3.1 | 3 |
| [illustrate](illustrate/README.md) | 2.2.1 | 4 |
| [memory](memory/README.md) | 2.1.1 | 7 |
| [pr](pr/README.md) | 4.2.1 | 2 |
| [project](project/README.md) | 2.2.1 | 2 |
| [scope](scope/README.md) | 1.6.0 | 7 |
| [user-manual](user-manual/README.md) | 1.5.1 | 4 |
| [workflow](workflow/README.md) | 1.9.0 | 13 |

Published versions live in the authoritative root [catalog](../catalog.json);
[catalog.json](catalog.json) mirrors it.
[Pending releases](pending-releases.json) identify staged versions. Check these sources when
installing. The table describes source in this checkout; catalog promotion updates published
versions independently.

## Setup, usage, and contribution

- [Install and initialize](../docs/getting-started.md#managed-workflow)
- [All commands, prerequisites, and expected outputs](../docs/extensions.md)
- [Managed stages and overlays](../docs/skill-guide.md)
- [Operating guide](../docs/workflow-guide.md)
- [Local packages and release process](../CONTRIBUTING.md)

Package READMEs linked above retain detailed runtime contracts. Commands register through the
consumer's Spec Kit integration; read the [host naming table](../docs/getting-started.md#command-names).
Scope's ID is ambiguous across catalogs; use Workflow's versioned Sanduq dependency installer.
