# User Manual

**Purpose:** create an application manual once, then update only the affected pages as each
feature ships. One Markdown source, written so it reads correctly on GitHub, produces End User,
Administrator/Operator and Technical Reference editions. Each edition renders the way the project
chooses: as Markdown (the default), through the project's own templates and tools (Pandoc, Quarto, a
script), or as an MkDocs HTML site and PDF.

| | |
| --- | --- |
| Lifecycle phase | After `tasks` and after `implement`; at application release |
| Hooks | Two optional hooks ([hooks](../reference/hooks.md)) |
| Commands | `init`, `analyze`, `update`, `release` ([reference](../reference/commands.md#user-manual)) |
| Requires | Illustrate 2.x, enforced by `deps.py ensure`; Python 3.11 or later |
| Standalone | Yes |
| License | MIT |

The `user-manual` skill and its references (API, release, screenshot and preview work) are
[vendored](../../vendor.lock.json) from
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
then writes `User-Manual/manual.yml` with `renderer.kind: markdown`, `theme/brand.yml` and three
install files; install `python -m pip install -r User-Manual/requirements.lock`, plus
`requirements-mkdocs.lock` or `requirements-pdf.lock` for the `mkdocs` renderer. In the managed
Workflow, select the manual through `$speckit-workflow-init`. MkDocs PDF builds need the libraries in
[prerequisites](../start/prerequisites.md#user-manual-renderers-mkdocs-and-pdf-libraries).

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

Analysis runs before implementation. It writes its tasks between `<!-- user-manual-tasks:start -->`
and `<!-- user-manual-tasks:end -->` in `tasks.md` and replaces that block on a rerun. Update writes
the affected pages, audits them, and builds a preview afterwards with `build_manual.py --all`. It adds
`--archive` only when `manual.yml` names an approved provider, so a local Update writes no
`User-Manual/site/<version>/*.zip`; CI builds its own preview archive. Release uses verified
application release evidence. Init never overwrites an existing `docs/<lang>/index.md`.
[Editable source](../diagrams/extension-user-manual.html).

On a rerun, `manual_state.py status` names the inputs and manual files that changed since the last
`record` (`changed_inputs`, `changed_outputs`), so Update reads those instead of every artifact. Set
`lifecycle.impact_scope: evidence` in `User-Manual/manual.yml` and Analyze and Update also start
from `manual_impact.py`, which matches the changed paths against each module's `evidence` and each
page's `source_evidence`. The default, `all`, keeps reading the whole manual.

## Limits

- Previews are private CI artifacts. A public repository needs the encrypted-preview setup in the
  [docs pack](../start/install-by-host.md#docs-pack).
- Hosted previews need a provider your project approved. Administrator and Technical editions need
  real access control.
- Newly discovered modules stay proposed until you approve them.

Package details: [User Manual README](../../extensions/user-manual/README.md).
