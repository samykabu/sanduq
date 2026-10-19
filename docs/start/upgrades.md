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

## Adopt Workflow 1.13.0 profiles

Workflow 1.13.0 (with Scope 1.8.0) adds effort-tiered profiles, a deterministic `workflow:lint`
stage, merged plan and tasks on the lower tiers, batch upstream revalidation, a guard hook and role
agents for Claude Code and Codex. Nothing changes until you opt in. After the transactional upgrade
and the per-feature migration above:

1. Add the policy keys you want to `.specify/workflow.yml`. The minimum that changes the front half:

   ```yaml
   profiles:
     enabled: true
   clarification:
     in_session_first_round: true
     max_questions_per_round: 6
   ```

   Optional keys: `artifacts.budgets` and `artifacts.enforce`, `issue_sync.taskstoissues:
   phase-lazy`, `project_sync.points`, `scope.board_cache_seconds`. The
   [workflow changelog](../../extensions/workflow/CHANGELOG.md) lists each key and its default.
2. Run `workflow.py doctor --project`. It confirms the installed packages, reports
   `INSTRUCTION_FILES_DUPLICATED` when both CLAUDE.md and AGENTS.md exist without an import, and
   prints the Codex hook approval instruction when Codex is installed. Approve the guard hook once in
   Codex with `/hooks`.
3. Start the next real issue with `$speckit-workflow-scope <issue>`. Scope records the effort score,
   the first Plan claim fixes the tier (`lite`, `standard` or `full`), and `workflow.py status
   --feature specs/<feature>` lists the stages that tier skips. Features already past Plan keep
   their full stage list.
4. Compare the run with the previous one: `status` shows the profile and the skipped stages, the
   receipts record `command: workflow:lint` where the lint replaced a model Analyze, and the host's
   own usage view gives the token spend. The repository benchmark
   (`docs/internal/benchmarks/` in the sanduq repository) measured runtime cost and
   instruction load, not generated tokens, so a live run is the confirmation.

Codex can now install the portable plugin bundles from the same marketplace
(`codex plugin marketplace add samykabu/sanduq`, then `codex plugin add <bundle>@sanduq`); that path
is published but has not been exercised yet, so report what you see.

## Adopt the round-2 releases

Workflow 1.14.0 pins Scope 1.8.1, Project 2.3.0, PR 4.3.0 and Illustrate 2.5.0, and selects Assure
2.4.0, User Manual 1.6.0 and Progress 1.3.0; the transactional upgrade installs them together. What
changes without any policy key:

- **Project.** Sync is one Python script (`project_sync.py`); Python is now required. The claim
  prints the exact sync command, so the agent no longer rereads the sync command file.
- **PR.** `pr_publish.py` writes the body, runs pr-lint and publishes; the receipt fields come from its
  output. The guard hook refuses a `gh pr create|edit --body-file` whose lint receipt does not match
  and a `gh pr create` on the default branch. Approve the changed hook once in Codex with `/hooks`.
- **Assure.** `documentation-gates.yml` is re-rendered: the gate reads the config through
  `assure_state.py status --gate`, and a reformatted config can no longer skip it. A project that kept
  its own copy with `--preserve-ci` should compare it with the shipped one.
- **Illustrate and its consumers.** Diagram steps read the type index plus one type reference; the
  skill's entry file is 11.7 KB instead of 34.7 KB.
- **Memory.** `run.md` reads its references by step; `status` returns the next command.

Opt-in keys, each off or unchanged until set:

```yaml
# .specify/workflow.yml
progress:
  hook_wiring: native            # default speckit; the installer writes hooks that run hook.py directly
  post_tool_matcher: "Bash|Task|Agent|spawn_agent"   # default "" (every tool); fewer activity updates
illustrate:
  hooks:
    self_check: true             # default false; checks every written diagram HTML
```

`User-Manual/manual.yml` takes `lifecycle.impact_scope: evidence` (default `all`) to update only the
modules the changed inputs touch; `assure-config.yml` takes `scan.exclude`; Memory's
`archive-policy.json` takes `guard_hooks: true` (default false). After setting a Progress key, rerun
`install.py` so the host hooks are rewritten; with `native` wiring, run it again after any later
`specify extension` command, which restores Spec Kit's own entries. Each package changelog lists the
details.

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
