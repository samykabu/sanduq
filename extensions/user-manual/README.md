# User Manual Extension

For setup and a worked example, see [Install by host](https://github.com/samykabu/sanduq/blob/main/docs/start/install-by-host.md)
and the [user-manual page](https://github.com/samykabu/sanduq/blob/main/docs/extensions/user-manual.md).
Every command and its example is in the [command reference](https://github.com/samykabu/sanduq/blob/main/docs/reference/commands.md#user-manual).


Create a complete application manual from scratch, then update only the affected modules as each
Spec Kit feature is implemented.

## Commands

| Command | Invocation | Purpose |
|---|---|---|
| `speckit.user-manual.init` | `/speckit-user-manual-init` | Interview, discover modules, approve the map, and scaffold the manual |
| `speckit.user-manual.analyze` | `/speckit-user-manual-analyze` | Add feature-specific documentation and asset tasks |
| `speckit.user-manual.update` | `/speckit-user-manual-update` | Update affected modules, then `build_manual.py --all` (`--archive` only when an approved provider publishes the preview) |
| `speckit.user-manual.release` | `/speckit-user-manual-release` | `build_manual.py --all --version <v> --archive --pdf` for versioned HTML archives and PDFs |

The committed source of truth lives under `User-Manual/`. English is required. Arabic is optional
per project, but the theme, navigation, diagrams, and PDFs support RTL from the first build.

Every feature PR receives a CI artifact link. Private repositories rely on repository read access;
public repositories upload an age-encrypted bundle and require the
`USER_MANUAL_PREVIEW_AGE_RECIPIENT` Actions variable, keeping the corresponding private key outside
the repository and CI.

The same source produces three navigable editions:

- End User: approved public or customer-facing content.
- Administrator/Operator: authenticated operational content.
- Technical Reference: private architecture, infrastructure, API, entity, column, enumeration,
  constraint, relationship, and sensitive-data classification content.

All prose must use plain English or plain Arabic and match the audience. End-user pages explain
goals and actions, administrator pages explain operations and consequences, and technical pages add
precise implementation detail without leaking secrets or production data.

The extension loads focused sub-skills only when needed: API documentation, release and migration
documentation, deterministic UI screenshots, and approved-provider preview publishing. Tutorials
and general manual structure remain in the core User Manual skill. HTML/PDF rendering remains a
deterministic build step, including module-specific PDFs through
`build_manual.py --module <id> --pdf`.

Diagrams depend on `illustrate >=2.0.0,<3.0.0`: `analyze` and `update` run
`python .specify/extensions/user-manual/scripts/deps.py ensure illustrate` first, which prints one
line and fails closed, and load the Illustrate type reference only after it passes.

## Reruns

`manual_state.py status --feature <path>` compares the feature's inputs and the manual with the
state the last `record` saved; when stale, its JSON carries `changed_inputs` and `changed_outputs`
(sorted repository-relative paths: new, changed or deleted) and `--summary` appends
`changed_inputs=N changed_outputs=M`. The `current` key and exit codes are unchanged.
`manual_impact.py --feature <path>` joins those changed inputs with the `evidence` paths of each
module in `manual.yml` and each page's `source_evidence`, prints the affected modules, pages and
audiences plus the unmatched changed paths, and records the list under `impact` in
`User-Manual/.state/coverage.json`. Set `lifecycle.impact_scope: evidence` in `manual.yml` to make
`analyze` and `update` start from that list; the default `all` keeps today's full read.

## Builds

Material for MkDocs is the default theme and is pinned for reproducible HTML builds. Set
`renderer.theme` in `User-Manual/manual.yml` to `readthedocs`, `mkdocs` or any other installed MkDocs
theme, with optional `renderer.theme_options` passed to the theme. Right-to-left editions
(`languages.rtl`) get `rtl-<theme>.css`, or `rtl-generic.css` when no theme-specific file exists, and
`theme-<theme>.css` applies to every language of that theme; a file of the same name in
`User-Manual/theme/` overrides the shipped copy. Navigation follows the `manual.yml` module order and
names each module in the edition's language. The content contract remains portable and a Zensical
compatibility build is supported for the Material theme because Material is in maintenance mode. Generated
HTML, ZIP, and PDF files are CI/release artifacts; Markdown, configuration, approved screenshots,
and diagrams are committed.
