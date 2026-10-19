# Spec Kit extension source index

Nine extensions supply the managed workflow and independently usable documentation, QA, Project,
PR, illustration, Memory, and Progress reporting processes. Use [install by host](../docs/start/install-by-host.md) to install them, the
[extension pages](../docs/README.md#extensions) to choose, and the
[command reference](../docs/reference/commands.md) for every public command and its example.

## Versions and command coverage

| Extension | Source version | Commands |
| --- | --- | ---: |
| [assure](assure/README.md) | 2.4.0 | 3 |
| [illustrate](illustrate/README.md) | 2.5.0 | 4 |
| [memory](memory/README.md) | 2.3.0 | 7 |
| [pr](pr/README.md) | 4.3.0 | 2 |
| [progress](progress/README.md) | 1.3.0 | 5 |
| [project](project/README.md) | 2.3.0 | 2 |
| [scope](scope/README.md) | 1.8.1 | 7 |
| [user-manual](user-manual/README.md) | 1.6.0 | 4 |
| [workflow](workflow/README.md) | 1.14.0 | 13 |

Published versions live in the authoritative root [catalog](../catalog.json);
[catalog.json](catalog.json) mirrors it.
[Pending releases](pending-releases.json) identify staged versions. Check these sources when
installing. The table describes source in this checkout; catalog promotion updates published
versions independently.

## Setup, usage, and contribution

- [Prerequisites](../docs/start/prerequisites.md) and [install by host](../docs/start/install-by-host.md)
- [Managed Workflow setup](../docs/scenarios/managed-workflow.md)
- [All commands and examples](../docs/reference/commands.md) and [hooks](../docs/reference/hooks.md)
- [Licenses](../docs/reference/licenses.md)
- [Managed stages and overlays](../docs/workflow/lifecycle.md)
- [Operating guide](../docs/workflow/operating-guide.md)
- [Local packages and release process](../CONTRIBUTING.md)

Package READMEs linked above retain detailed runtime contracts. Commands register through the
consumer's Spec Kit integration; read the [host naming table](../docs/reference/commands.md#command-names).
Scope's ID is ambiguous across catalogs; use Workflow's versioned Sanduq dependency installer.
