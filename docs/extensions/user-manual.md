# User Manual

**Purpose:** create an application manual once, then update only the affected pages as each
feature ships. One Markdown source produces End User, Administrator/Operator and Technical
Reference editions in HTML and PDF.

| | |
| --- | --- |
| Lifecycle phase | After `tasks` and after `implement`; at application release |
| Hooks | Two optional hooks ([hooks](../reference/hooks.md)) |
| Commands | `init`, `analyze`, `update`, `release` ([reference](../reference/commands.md#user-manual)) |
| Requires | Illustrate 2.x, enforced by `deps.py ensure` |
| Standalone | Yes |
| License | PolyForm Noncommercial 1.0.0 |

The manual skills are [vendored](../../vendor.lock.json) from
[sanduq-skills](https://github.com/samykabu/sanduq-skills).

## Setup

```bash
specify extension add illustrate
specify extension add user-manual
```

```text
$speckit-user-manual-init Discover Booking, Payments and Operations modules; interview me, require English and offer Arabic.
```

Init interviews you and proposes a module map. Nothing is scaffolded until you approve the map. Init
then writes `User-Manual/requirements.lock`; install it with
`python -m pip install -r User-Manual/requirements.lock`. In the managed Workflow, select the manual
through `$speckit-workflow-init`. PDF builds need the libraries in
[prerequisites](../start/prerequisites.md#mkdocs-and-pdf-libraries).

## Example

```text
$speckit-user-manual-analyze Find refund tutorial, API, entity, release and screenshot gaps in this feature's tasks.
$speckit-user-manual-update Update only the affected refund pages and assets; build the private preview.
$speckit-user-manual-release Build the approved v3.0.0 audience and language HTML archives and PDFs.
```

Material for MkDocs is the default theme. ReadTheDocs, MkDocs and other installed themes also work.
The [theme gallery](../user-manual-examples.md) shows real builds.

## How it runs

![User Manual sequence: user-manual.init interviews you and proposes a module map you approve; user-manual.analyze runs before implementation; user-manual.update writes and audits pages after implementation; after a verified application release, user-manual.release builds the outputs for each audience and language.](../diagrams/extension-user-manual.animated.svg)

Analysis runs before implementation. Update writes the affected pages, audits them, and builds a
preview afterwards. Release uses verified application release evidence.
[Editable source](../diagrams/extension-user-manual.html).

## Limits

- Previews are private CI artifacts. A public repository needs the encrypted-preview setup in the
  [docs pack](../start/install-by-host.md#docs-pack).
- Hosted previews need a provider your project approved. Administrator and Technical editions need
  real access control.
- Newly discovered modules stay proposed until you approve them.

Package details: [User Manual README](../../extensions/user-manual/README.md).
