# Managed workflow guide

The coordinated workflow packages are still unreleased. The following development
setup has been exercised through Spec Kit's public CLI; published installation
becomes available only after release asset verification and catalog promotion.

## One-time setup

Install the workflow archive from an explicit Sanduq release URL when published,
then invoke `speckit.workflow.init`. The setup asks for neither, QA only, User Manual
only, or both. It saves that choice in `.specify/workflow.yml`, installs only required
and selected dependencies from versioned Sanduq sources, composes presets, and adds
the policy-aware CI gate. Existing project board IDs, audience maps, languages and
publication settings remain project data. A newly selected manual requires its
module-map interview; recommendations are never treated as answers.

For local development, build with `python extensions/scripts/package.py workflow`,
extract the ZIP outside the consumer's `.specify/extensions` directory, and install
with `specify extension add --dev <extracted/workflow>`. Build/extract its selected
dependencies similarly, then pass `--packages <extracted-packages>` to the installer.
This bundles the canonical presets and helpers; installing the raw extension source
folder bypasses those build inputs and is not the supported workflow package test.

The CLI equivalent after selecting the processes is:

```text
python .specify/extensions/workflow/scripts/workflow.py init --qa on --manual off
python .specify/extensions/workflow/scripts/install.py
python .specify/extensions/workflow/scripts/install.py --apply
```

The first installer command previews changes. The second saves a local backup,
installs dependencies and presets, reconciles hooks, checks registrations, and rolls
back on failure. An unrelated community package also uses the ID `scope`; never
install it by a bare name when Sanduq Scope is intended.

## Daily entry points

| Entry | What happens automatically |
| --- | --- |
| Scope, with an explicit issue | Inspect prerequisites and project preferences, publish managed issue/labels/spec-prompt, Specify, then Clarify or SuperSpec Brainstorm |
| Clarify, after GitHub answers | Reread paginated comments and edits, apply resolved answers, Plan, generate tasks, selected QA/manual analysis, final Analyze, native task sub-issues, then implementation |
| Continue | Validate checkpoint identity, current inputs and package versions; resume the earliest unfinished or stale stage |
| Finalize | Finish required verification/documentation and create or update one PR with inline visuals |

These are entry points, not four obligatory pauses. A question-free issue can run
from Scope through implementation in one bounded session. Implementation completion
stops at ready-to-finalize; PR creation requires the Finalize entry. Merge and deploy
are separate actions.

## Scope preferences and GitHub answers

A project can configure this existing preference without asking on every issue:

```yaml
scope:
  keep_together:
    target: 20
    tolerance: 3
    unit: points
    inclusive: true
```

Estimates 17, 20 and 23 keep the feature together. Values 16 and 24 need ordinary
assessment. Units must match the project's actual estimation system. This decision
settles feature decomposition; implementation tasks still become native sub-issues.
Scope records project-policy provenance rather than a fabricated human approval.

Clarification posts one question per GitHub comment, mentions the issue creator and
shows an unchecked recommendation. Reply with a question ID, such as `C1Q1: A`, or
edit its checkbox. Reinvoke Clarify while the card is still waiting: the workflow
rereads answers without requiring a manual board move. An unchanged unanswered
thread causes no new round. Ambiguous replies, conflicting choices and unresolved
questions stop planning. Asking every question is not the same as answering them.

Use `scope.statuses` to map logical names to actual board columns, for example
`Feature Specification: Discovery`. Managed artifact paths default to
`.specify/scope/github` and `docs/workflow/implementation-plan.html`; existing Bunyan
locations can be preserved explicitly through scope policy.

## Provider and task ownership

The dispatcher independently prefers compatible, enabled SuperSpec Brainstorm,
Tasks and Execute where their commands exist, falling back to the core commands.
An explicitly required unavailable provider blocks execution. Exactly one generator
and executor run. All selected analysis happens before final Analyze and the actual
core Tasks-to-Issues command. Its Sanduq preset calls the native sub-issue adapter,
which identifies tasks by repository, parent, feature and task ID. It handles repeated
T001 IDs across features and T1000; an unmapped existing child blocks duplication.

Project sync updates the bound parent and board status. The workflow adapter alone
creates task issues and synchronizes their completion. Active legacy Bridge handoffs
block a competing executor; settle their actual state first, never mark them complete
merely to bypass the guard. Managed overlays prevent direct legacy native commands
from starting another pipeline. Routine phase checkpoints follow project policy;
explicit human-review tasks remain real gates.

## Fresh-session continuation

Target a 60% maximum occupancy, checkpoint at 50%, and reserve 10% for handoff.
Reliable usage and enforced per-call bounds are required to claim strict protection.
Otherwise, use the user-approved labelled estimate with smaller work batches. A
prompt cannot guarantee host context occupancy or create a fresh host session.

The runtime saves `checkpoint.json`, `handoff.md` and `resume-prompt.md` under the
feature's workflow directory. The handoff identifies the issue, feature, branch,
completed stages, pending task IDs, evidence and active claim. Add actual test results,
background process handles and unresolved approvals. Start a fresh session with the
saved prompt. Inspect possible remote writes before clearing an interrupted claim;
missing HTTP responses are not proof that an issue or PR was not created.

## Updates and releases

Reusable source lives in Sanduq. Consumer policy, issue bindings, feature progress,
manual content and evidence stay in their project. Do not edit installed upstream
commands. Use the current workflow package's `scripts/upgrade.py --version X.Y.Z`
to preview a reviewed update, then add `--apply`. The outer transaction backs up the
old workflow and integrations, upgrades through the public CLI, and invokes the new
package's installer. A failure restores the previous managed state. Dependency-only
reconciliation uses `scripts/install.py` preview and apply. The bundled dependency
lock selects exact versions and source URLs.
Installed process choices do not silently change on update. Newer compatible dependencies are retained and reported rather than silently downgraded to an older lock baseline; active runs still need reviewed migration.

The installer preserves configuration/state and stores a backup ZIP and operation
log under `.specify/workflow/backups/installs/`. A failed attempt restores exact managed
file bytes. Unknown customized CI workflows or a locally edited Scope alias block
replacement and leave a backup for explicit reconciliation. After success, current
runs detect package drift and require a reviewed migration:

```text
python .specify/extensions/workflow/scripts/workflow.py migrate --feature specs/001-example --reason "Reviewed adapter compatibility and upgrade evidence"
```

Migration preserves still-current historical evidence with its original package
digest. It invalidates stages whose selected commands changed. Use
`--invalidate-from <stage>` for a changed stage contract. Changed inputs or deleted
evidence invalidate affected work independently. Historical receipts are never
rewritten to claim that a new package executed old work.

Maintainers review versions in `extensions/pending-releases.json`. Main-branch CI
must succeed before immutable release assets are published. Every archive is downloaded
and checked before both catalogs are promoted. An existing tag with different bytes
fails; it is never overwritten. Development previews cannot be published.

## Evidence and private PRs

QA Assure supplies tester readiness and walkthrough evidence. User Manual supplies
audience-facing documentation. Generated documents do not prove tests or human QA
ran. CI requires current inputs, outputs, completed required tasks and parent mapping.
Source-only changes need explicit feature identity: include a changed
`.specify/workflow/pr-features.json` with `{"features": ["specs/001-example"]}`,
or supply `--feature` to the gate CLI. Multi-feature changes validate all changed
specifications even when an explicit feature is supplied. Verification also inventories
source additions/deletions; omitting a changed code file from an agent receipt cannot
keep old test evidence current. A shallow or unavailable Git base is an error, not permission
to guess freshness.

Finalize inventories every relevant diagram and screenshot, embeds each inline, and
verifies actual image loading in an authenticated private-repository view. A Markdown
link or successful asset upload alone is insufficient. Never publish private assets
to a public host or place credentials in image URLs. Local, CI, remote PR, release and
human acceptance evidence remain distinct.
