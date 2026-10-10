# Upgrades and changelogs

Read the published version in the [catalog](../../catalog.json) before you upgrade. Release notes
are in the root [CHANGELOG](../../CHANGELOG.md) and in each package's `CHANGELOG.md`.

## One extension

```bash
specify extension update <id>
```

Then rerun the extension's init or doctor command if its changelog asks for it.

## Workflow and its dependencies

Resolve active [claims](../reference/glossary.md#claim) first. Then preview and apply the
transactional upgrade, substituting the published version:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version <version>
python .specify/extensions/workflow/scripts/upgrade.py --version <version> --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

The first command previews. The second backs up the managed files, upgrades, and restores the old
state if anything fails. Add `--preserve-ci` to keep a project-owned evidence workflow.

After an upgrade, a feature that was in progress needs a reviewed migration before it continues:

```bash
python .specify/extensions/workflow/scripts/workflow.py migrate --feature specs/412-refund-approval --reason "Reviewed the upgrade notes"
```

The [operating guide](../workflow/operating-guide.md#updates-and-releases) explains what migration
keeps and what it invalidates.

## Moved documentation

Pages moved in this release keep a forwarding stub at the old path for one release cycle:

| Old page | New page |
| --- | --- |
| `docs/getting-started.md` | [Install by host](install-by-host.md) and the [scenarios](../README.md#choose-an-adoption-level) |
| `docs/skills.md` | [Skills only](../scenarios/skills-only.md) |
| `docs/extensions.md` | [Extension pages](../README.md#extensions) and the [command reference](../reference/commands.md) |
| `docs/extension-workflows.md` | [Extension pages](../README.md#extensions) and [managed Workflow](../scenarios/managed-workflow.md) |
| `docs/skill-guide.md` | [Worked lifecycle](../workflow/lifecycle.md) |
| `docs/workflow-guide.md` | [Operating guide](../workflow/operating-guide.md) |
| `docs/workflow-operations.md` | [State, evidence and runners](../workflow/operations.md) |
| `docs/sanduq-delivery-usage.md` | [Delivery policy](../workflow/delivery-policy.md) |
| `docs/workflow-compatibility.md` | [Compatibility](../reference/compatibility.md) |

`install.sh` and `install.ps1` were removed. Use the Spec Kit catalog.

## Limits

- An upgrade does not certify old receipts against the new package. Review the migration.
- A newer compatible dependency is kept, not downgraded to the pinned version.
