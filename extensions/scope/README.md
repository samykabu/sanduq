# Sanduq Scope

For setup and a worked example, see [Install by host](https://github.com/samykabu/sanduq/blob/main/docs/start/install-by-host.md)
and the [scope page](https://github.com/samykabu/sanduq/blob/main/docs/extensions/scope.md).
Every command and its example is in the [command reference](https://github.com/samykabu/sanduq/blob/main/docs/reference/commands.md#scope).


The [catalog](https://github.com/samykabu/sanduq/blob/main/catalog.json) lists the published version;
the [changelog](CHANGELOG.md) says what each version changed. Scope is MIT licensed; see
[LICENSE](https://github.com/samykabu/sanduq/blob/main/extensions/scope/LICENSE).

In a managed project `scope.py render-spec` writes spec.md from an approved single-leaf analysis so
Specify only binds; `clarification.py publish --answers` records a first round the issue creator
answered in the session as one GitHub comment and moves the issue to Ready;
`clarification.max_questions_per_round` caps a round; Mermaid diagrams are allowed in questions.
The analysis schema and effort rubric are in [references/analysis-contract.md](references/analysis-contract.md).

Build with `python extensions/scripts/package.py scope`; the archive bundles the
scope-gate and scope-brainstorm presets. Install the extracted package through
`specify extension add --dev <scope-package>` and install its presets through the
public Spec Kit preset CLI. Do not edit generated skills. The community catalog
contains an unrelated extension named scope: use explicit Sanduq package sources.

The analyst is `skills/scope-analyst/SKILL.md`; shared GitHub clarification is
`skills/github-clarification/SKILL.md`. Commands retain issue guards, prerequisites,
labels, spec-prompt, source binding and native scope decomposition. Mutations require
`--apply`. PyYAML is required for managed policy; unmanaged runtime retains its
existing behavior and approval contract.

With `.specify/workflow.yml`, an inclusive `scope.keep_together` band can settle
feature decomposition without asking again. Provide `effort_estimate.value` and
`effort_estimate.unit` in analysis JSON; the unit must match project policy. This
never suppresses implementation task sub-issues. Policy approval is recorded as
project-policy, not fabricated human approval.

Managed clarification rereads waiting issue comments, including edits. Unchanged
unanswered threads produce no new comments. Real answers update spec.md before
Plan. Questions are individual comments, mentioning the creator, with stable IDs
and unchecked recommendations. Project `scope.statuses` maps logical names such as
Backlog, Feature Specification, Need Clarifications and Ready to actual board names.

From 1.7.0 each published clarification round also writes `specs/<feature>/workflow/clarifications.json`,
so a report can show the questions without calling GitHub. It lists every question with its options,
answer, state (`pending`, `conflict`, `answered`, `applied`, `waived` or `superseded`), comment URL and the
evidence behind the answer. The file is written only after the specification is replaced and the board
transition succeeds, and before the publication journal is marked complete. Dry runs and failed or stale
publications write nothing. A changed question becomes the next `revision`; earlier revisions stay.
A checkbox answer has no recorded author or time, so `editor` and `answered_at` stay `null`.

Each `evidence` entry is `{kind, url, comment_id, explanation}` with `kind` one of `comment`, `disposition`,
`selection` or `closure`, and `null` for what does not apply. `applied` is `{at, evidence: [string, ...]}`,
always a list. The [shared test vector](tests/fixtures/clarifications-vector.json) shows every state. If an
existing `clarifications.json` cannot be read, it is moved to `clarifications.json.unreadable-<batch>` and a
new one is written, so a rerun after the board transition still finishes.

After a split, `/speckit-scope-plan` redraws the implementation dependency plan as an
Illustrate dependency graph and `scripts/accept_plan.py` accepts it only after issue
coverage, dependency reachability, Illustrate's own checks, SVG/PNG export and a headless
Chromium render check pass. Scope requires Illustrate 2.2.1 or newer; PNG export and the
render check need Playwright with Chromium. Clarification questions embed Illustrate PNGs
through verified commit-pinned GitHub URLs, which work in private repositories, and post
a text version with the reason when an image cannot be hosted. See
[the Illustrate plan reference](https://github.com/samykabu/sanduq/blob/main/extensions/scope/references/illustrate-plan.md).

Managed default artifacts are `.specify/scope/github/` and
`docs/workflow/implementation-plan.html`; `scope.artifact_directory` and
`scope.plan_file` can preserve existing project locations. Unmanaged projects retain
legacy paths. All paths must stay inside the project. Read `references/analysis-contract.md`
for the effort rubric and approval details.

## Snapshots, board cache and spec rendering

`scope.py inspect <issue> --output <file>` saves the snapshot and prints only a summary (issue,
fingerprint, readiness, prerequisites and counts); read the file for the issue, comments and
prerequisite bodies. `gate`, `approve`, `publish` and `bind` accept `--snapshot <file>` and reuse it
when the file is younger than `scope.board_cache_seconds` (default 300; 0 disables) and its
`fingerprint` matches one fresh fetch of the issue; the receipt and labels still come from that
fresh fetch. Otherwise they inspect again (`gate` and `bind` read prerequisites only). Without
`--snapshot`, `gate` and `bind` use `.specify/scope/issue-<number>-snapshot.json` when it exists.
The output says which with `snapshot_reused`.

Project board reads are cached in `.specify/scope/board-cache.json` (`{fetched_at, repo, items}`)
for the same TTL. Every Scope or clarification write to the board or an issue removes the cache,
and a gate that would refuse because of a cached status rereads the live board first.

For an approved single-leaf analysis, `scope.py render-spec <issue> --analysis <file> --feature
specs/<feature>` prints the Spec Kit spec (`text` in the JSON output); `--apply` writes
`specs/<feature>/spec.md` with a `<!-- sanduq-scope:rendered <sha256> -->` first line. It refuses
with `SCOPE_RENDER_UNAPPROVED`, `SCOPE_RENDER_LEAF_REQUIRED` or `SCOPE_RENDER_EXISTS` (replace an
unmarked spec only with `--force`).

`scope.py reconcile <issue> --apply` (the after_implement hook) rolls status up through that issue's
Scope ancestors only; `scope.py reconcile --apply` sweeps every Scope parent.
