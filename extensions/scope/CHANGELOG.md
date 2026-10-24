# Changelog

## [1.11.1] - 2026-10-24 (pending release)

- Shared approved-leaf and retained-parent validation with Workflow accepted-Scope recovery. Recovery fetches current provider state without cache, publication or claim writes; ordinary claim admission remains unchanged.
- Fresh managed bindings retain the approved parent's exact native child list and prerequisites; a pending dependency plan still blocks admission.
- Requires Workflow 1.18.1 for the read-only decision ledger helper. Implementation and package validation remain in progress.

## [1.11.0] - 2026-10-21

- The prerequisite check stops at a Done prerequisite (status aliases applied) and still walks through In review ones. A full inspect reads pull-request timelines for the direct prerequisites only. A chain of N Done prerequisites now costs 3 API calls instead of 2 + 2N.
- `scope.py cancel <issue>-<hash>` cancels an interrupted publish: with `--apply` it marks the journal `rolled_back` under the mutation lock, so `publish` refuses to resume it. It makes no GitHub write and prints the created issues, issue before-images, dependency before-images and catalog and issue-map backups for manual repair. A bare issue number lists that issue's operations instead. A publish journals each new issue before linking it, so an interrupted link still lists the issue.
- The github-clarification skill holds the Clarify and Brainstorm coverage categories and the rules for placing answers in the spec (`references/analysis-json.md`), once. The Clarify and Brainstorm overlays in the scope-gate, scope-brainstorm and workflow presets are short pointers to it; both scope presets now `replace` instead of `prepend`, so an unmanaged Clarify round no longer loads the 19.5 KB upstream command.
- Scope's GitHub client (`GitHub`, `ProjectRest`, the GraphQL-to-REST switch) moved to `scripts/sanduq_scope_github.py` on the shared `sanduq_gh` runner. `from scope import GitHub` still works, and messages are unchanged. A failed REST GET is retried once after a 5xx or a timeout; writes and `gh project` commands never are. A `gh` timeout or a missing `gh` is a Scope error with a message.
- The workflow policy is parsed once per file text in a process (with the C YAML loader when present), and Workflow's `workflow.py` and `decisions.py` are loaded once per process.

### Migration

- Readiness rule change: a Done prerequisite whose own prerequisite was reopened no longer blocks the issue. A cancelled prerequisite, or one closed without Done, still blocks.
- `accept_plan.py` no longer accepts `--spec` or `--archify` (deprecated since 1.7.0); use `--html`.
- Unmanaged Clarify and Brainstorm no longer compose the upstream command under the overlay. Run `specify preset add` for scope-gate and scope-brainstorm again after the update. Spec Kit now scaffolds `speckit.superspec.brainstorm` even without Superspec; Scope still picks Brainstorm only when Superspec is installed and enabled.

## [1.10.1] - 2026-10-21

Fixes from the review of round 4 (PR #101).

- Scope reads the origin with `git remote get-url origin` again (through `sanduq_remote.origin_url(resolve=True)`), so an origin written with a `url.<base>.insteadOf` alias such as `gh:Acme/App.git` resolves to GitHub. 1.10.0 read the raw config value and refused it.

## [1.10.0] - 2026-10-21

Optimization round 4. No renames.

Round 4.

- Scope reads the repository from `remote.origin.url` through the shared `sanduq_remote` helper, the same rule as Workflow and Project. It accepts every GitHub remote form Workflow accepts, compares `owner/repo` without case on the board, the board cache and native dependencies, refuses a look-alike such as `https://evil.example/github.com/acme/app`, and a missing origin is a message, not a traceback.
- A split publish finds the issues to rewire before its first GitHub write. An unrelated issue whose "Depends on" text names no issue is skipped with one stderr line instead of failing the publish after the children exist. An issue tied to the parent with unparseable text still refuses, before any write.
- A `gh` timeout in `clarification.py` (the `dispatch` and `plan-gate` hooks) exits 2 with a message. `accept_plan.py` stops an Illustrate step after 300 s and records it as failed.
- `inspect --output` prints a summary under 1 KB; the snapshot keeps only the fields Scope reads (58 KB to 26 KB for one issue, three prerequisites and eight comments). Journal before-images use the same fields. Snapshots written by 1.9.0 still load.
- A split publish lists the repository's issues once instead of three times; paginated reads time out after 120 s instead of 30 s.
- `scope.py reconcile <issue> --apply` updates only that issue's Scope ancestors; the after_implement hook uses it. Plain `reconcile --apply` still sweeps every parent and no longer rereads a parent it did not change.
- The scope-gate Specify overlay keeps only the rules for both modes. The Backlog rule and the after_specify chain moved to `references/specify-standalone.md`, read only without `.specify/workflow.yml`, so a managed Specify claim is no longer told to chain Clarify.
- Snapshot reuse, the board cache and `render-spec` moved from the analysis contract to the README.
- A rendered spec can be bound. The Specify claim on it is `bind-only`, and `bind` with the claim's flags refused it (`SCOPE_WORKFLOW_BINDING_MISMATCH`). The fresh gate also took the approved analysis for a revised one, because publish prefixes the prompt with the issue and effort.
- The fresh gate accepts a root issue kept whole: GitHub's 404 for its parent means no parent, so no retained parent approval is needed. An issue whose approval names children still needs its parent.
- `gate` returns the issue's checked prerequisites as `dependencies`, so `bind` writes them to `scope-source.json`. Workflow's PR lint (lean execution) and `pr_publish` read them there; without them the PR stage failed `PR_LINT_SCOPE_PREREQUISITES_REQUIRED`. No earlier Scope release wrote the key.
- When the gate's issue is missing from the Project listing (GitHub can lag a just-published `item-add`), the gate reads the board again after 2 s and 4 s before it refuses with the same `SPECIFY_STATE` message.

### Migration

- The after_implement reconcile hook reads the bound issue from `scope-source.json` by itself; no setting changes.
- Unmanaged projects run `specify preset add` again for scope-gate. The Workflow installer re-adds it when its digest changes.
- A feature bound before this release has no `dependencies` in `scope-source.json`, so a lean PR stage still fails `PR_LINT_SCOPE_PREREQUISITES_REQUIRED`. Add `"dependencies"` with the list from the issue's scope receipt (the `speckit-scope:metadata` block in the issue body; `[]` when it has none), then record the PR stage again.

## [1.9.0] - 2026-10-20

Optimization round 3.

- Far fewer GitHub calls: publishing a three-child split with 200 unrelated issues makes 62 calls instead of 290 (dependents come from the parent's blocking list, with a full-scan fallback when that read is incomplete); `bind --apply` 4 instead of 10; a six-question clarification publish 23 instead of 27.
- `gate` and `bind` reuse a current inspect snapshot within the board cache window.
- `export-plan` writes waves, the critical path and a draft mapping; clarification suggests clean answers for single checked options and logs each Q/A; `inspect --skeleton` writes the analysis skeleton.
- Shorter instruction path (the plan step no longer reads the Illustrate skill); error messages name `/speckit-scope-run`; the seven descriptions total 969 characters.

## [1.8.1] - 2026-10-19

- The clarification diagram reference reads Illustrate's type index plus the chosen type reference instead of the whole Illustrate skill.

## [1.8.0] - 2026-10-18

- `scope.py render-spec <issue> --analysis <file> --feature specs/<f> [--apply] [--force]` writes spec.md from an approved single-leaf analysis, starting with `<!-- sanduq-scope:rendered <sha256> -->`, so Workflow 1.13.0 can bind without a model pass (`SCOPE_RENDER_UNAPPROVED`, `SCOPE_RENDER_LEAF_REQUIRED`, `SCOPE_RENDER_EXISTS`). Analyses may list `uncertainty` items, rendered as `[NEEDS CLARIFICATION: ...]`.
- `clarification.py publish <issue> --analysis <file> --answers <answers.json> [--apply]` records a first round answered in the session by the issue creator (`clarification.in_session_first_round: true`): one managed comment of kind `round-in-session`, spec edits applied, `clarifications.json` items `applied` with evidence kind `in-session`, straight to Ready. `examples/answers.json` shows the shape.
- `clarification.max_questions_per_round` caps a round (`CLARIFICATION_TOO_MANY_QUESTIONS: <n> > <cap>; defer <keys>`); questions may carry `priority` (1 is highest).
- Mermaid `diagram` questions are allowed in managed projects; `ILLUSTRATE_REQUIRED` is gone and `diagram_image` is optional.
- Project board reads are cached in `.specify/scope/board-cache.json` for `scope.board_cache_seconds` (default 300, 0 disables), invalidated by every Scope or clarification write; `gate`, `approve`, `publish` and `bind` accept `--snapshot <inspect output>` and report `snapshot_reused`.
- The scope-analyst and github-clarification skills are short procedures with references (`managed.md`, `standalone.md`, `analysis-json.md`, `controls.md`); the analyst tiers its evidence depth by the first-pass score.
- Requires Workflow 1.13.0.

## [1.7.0] - 2026-10-18

- Clarification publication writes `specs/<feature>/workflow/clarifications.json` (`{v: 1, items}`). Each item has `source_id`, `revision`, `question`, `options`, `answer` (`single`, `multiple` or `text`), `state` (`pending`, `conflict`, `answered`, `applied`, `waived` or `superseded`), `url`, `editor`, `observed_at`, `answered_at`, `applied` and `evidence`, plus the `batch` that wrote it. Pending, answered, superseded and waived questions are included.
- The file is written after the specification is replaced and the board transition succeeds, and before the publication journal is marked complete. Dry runs, stale publications and failed transitions write nothing. The write is atomic, a rerun of the same batch replaces its own records, and a changed question adds the next revision while earlier revisions stay. Building the records makes no GitHub calls.
- `evidence` entries are `{kind, url, comment_id, explanation}` with `kind` one of `comment`, `disposition`, `selection` or `closure`; `applied.evidence` is a list of strings. `tests/fixtures/clarifications-vector.json` is the shared test vector, regenerated by a test.
- A retry of a publication that stopped after the board transition recognises its journal before the new-publication status gate, repairs the records and publishes nothing twice. The repair does not compare the live thread with the baseline, so a human reply after the crash cannot block it; a dry run reports `unfinished: true`. `clarifications.json` is never written through a link (`CLARIFICATIONS_UNSAFE`), and an existing file that is empty, `{}`, `[]` or `""` is set aside like any unreadable one. With `reread-answers`, the repair records the digest of the input it processed, so an answer that arrived after the crash is still new on the next run. A malformed or unreadable `clarifications.json` (bad items, revisions) is moved to `clarifications.json.unreadable-<batch>` with a warning and a fresh file is written.
- A checkbox answer records no author and no time (`editor` and `answered_at` are `null`); a reply comment records its author and creation time.

## [1.6.2] - 2026-10-15

- Document the verified initial and revalidation gate/bind command forms through Workflow's command helper. Revalidation does not use initial-claim flags. Existing binding, status and REST safeguards remain.

## [1.6.1] - 2026-10-10

- Fresh bind is restricted to the owned initial Specify phase, before any write. A changed
  resolved prompt requires the exact supplied analysis artifact in verified, applied Decision
  evidence; otherwise the unchanged published prompt stays authoritative and local analysis is
  consulted evidence only. No new approval is fabricated.
- Fresh issue-bound Workflow Scope/Specify may revalidate a published, approved native leaf in
  the mapped Feature Specification status with explicit `--feature`, `--token`, `--session` and
  `--analysis`. It checks the repository, feature, issue, branch, executor, applied live
  decisions, current scope fingerprint, prerequisites, native parent/child relationship and
  retained parent approval, and returns the analysis and decision hashes and the original
  approval without publishing or creating an approval receipt. Standalone Backlog gates are
  unchanged.
- Project operations fall back to the REST Projects API when the failed `gh project` request
  itself reports a GraphQL rate limit, even if the cheap budget probe still shows points left
  (a costly item listing can be refused first). An isolated `RATE_LIMIT` token counts like the
  spaced wording. The reset backoff, later GraphQL probing and the listing query are unchanged.
- `gh project` can report a blocked GraphQL API as "unknown owner type" while the budget probe
  still shows points. That masked failure switches to REST only when a direct owner query is
  itself rate-limited, or when the REST Projects API resolves the same configured owner,
  `ownerType` and project number. A wrong owner, owner type or project number, a missing or
  inaccessible Project, and every other error are still raised unchanged.
- Before any REST operation the request must name the configured owner, Project number and
  Project ID, carry only supported arguments, and match the live Project's node ID, owner and
  owner type. The reported transport is `rest`.
- REST `item-add` is idempotent like `gh project item-add`. It first looks for the exact issue
  (repository and number, plus issue ID when listed) in a fresh paginated listing of the configured
  Project and returns that item's ID without writing. After a 422 "already exists" from a concurrent
  add, it rereads once and returns the matching item; if none matches, or for any other 422, 403 or
  404, the original error is raised. Nothing is removed, re-added or edited.
- The shared Project REST adapter supports single-select field creation and fresh field
  discovery; GitHub subprocess calls have a 30-second bound.
- This is a material binding change: focused independent review is required before installation.

## [1.6.0] - 2026-10-10

- The implementation dependency plan and clarification diagrams use Sanduq Illustrate
  (replaces Archify). `extension.yml` now requires `illustrate >=2.2.1,<3.0.0`.
- `accept_plan.py` accepts an Illustrate dependency-graph HTML whose wave nodes and edges
  carry `data-plan-node` / `data-plan-from` / `data-plan-to`. It keeps the issue coverage,
  reachability, freshness-hash, pending-marker, failed-render and receipt rules, runs
  Illustrate's `self_check.py`, `verify-geometry.py` and `export_diagram.py` (SVG and PNG),
  and renders the plan in headless Chromium at three desktop viewports, failing on script
  errors and invisible, overlapping or out-of-bounds nodes. Screenshots and hashes go in the
  receipt; managed projects still require `--review` before the marker clears.
- New flags: `--html` (replaces `--spec`), optional `--illustrate <skill-dir>`, and
  `--migrate-only`. `--spec` stays as an alias of `--html` and the previous renderer flag is
  accepted and ignored with a warning until 1.7.0.
- Pending plans from 1.5.x are converted, never dropped: the marker stays pending with the
  original under `migrated_from`, an unreviewed receipt is kept as
  `scope-plan-receipt.legacy.json`, and `PLAN_REGENERATION_REQUIRED` names the issue.
- Clarification questions take `diagram_image` (a pushed Illustrate PNG) with a required
  `diagram_text`. The image is embedded through a commit-pinned GitHub blob URL verified
  with the contents API, so it loads in private repositories; otherwise the text version is
  posted with the reason and listed under `image_fallbacks`. Managed Mermaid diagrams now
  fail with `ILLUSTRATE_REQUIRED`; `raw.githubusercontent.com` images are rejected.
- `references/illustrate-plan.md` replaces the previous plan reference.

**Upgrade note.** Install Illustrate 2.2.1 or newer beside Scope (Workflow 1.9.0 installs
it), and for plan acceptance `pip install playwright && playwright install chromium`. Run
`python .specify/extensions/scope/scripts/accept_plan.py --migrate-only` if a plan was
pending before the upgrade, then regenerate it with `/speckit-scope-plan`. Replace
`--spec <file>` with `--html <file>` in your own scripts before 1.7.0.

## [1.5.2] - 2026-10-10

- Documentation: neutral provenance wording; no behavior change.
- README: version note and links to the new extension page, install-by-host page and command reference.

## [1.5.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

## 1.5.0

- `extension.yml` now declares `requires.extensions: workflow >=1.8.0,<2.0.0`
  (required), because `bound_claim` uses workflow's checkpoint identity gate.
  Spec Kit does not enforce `requires.extensions`; the workflow installer
  does (see workflow 1.8.0).
- `bound_claim` (`workflow_policy.py`) no longer compares a checkpoint's
  absolute `repo_path` (machine- and clone-specific; still written by
  workflow 1.8.0+ so an older reader does not `KeyError`, but never read
  or compared by it) against the current repository root; the `issue`
  field it already checks just above binds the claim to the portable
  GitHub repo string instead. Fixes the same checkpoint-identity design
  bug `workflow.py`'s `Run.load()` fixes. It now also runs workflow's own
  checkpoint identity gate (`repo_identity`, or a legacy checkpoint's
  reachable history, and the issue naming this repository's GitHub remote)
  before accepting the claim, and refuses it on any failure. This needs the
  sibling workflow extension (1.8.0 or newer) installed beside scope; with
  none loadable the claim is refused.
- Serve Project board reads and writes (`item-list`, `field-list`, `item-add`, and
  single-select/text `item-edit`) from the REST Projects API when the GraphQL budget is
  exhausted. The real budget is checked, because `gh project` can report exhaustion as an
  unrelated error such as "unknown owner type". GraphQL is used again after the reported reset.
- Name the transport on stderr when falling back, and add `transport` (`graphql`, `rest` or
  `graphql+rest`) to printed JSON results of Scope and clarification commands that touched the
  Project. Saved `--output` files are unchanged.

## 1.4.0

- Move canonical source into Sanduq; add managed effort policy, automatic clarification reread and configurable board/artifact mappings.
- Revalidate open progressed features under matching workflow claims without resetting
  their board status; retain current approval and unresolved-question guards.

## 1.3.0

- Automatically invoke Plan from either Clarify or Brainstorm after a fully resolved
  review has published successfully and the live issue is Ready.
- Carry the exact source issue and specification through the shared handoff and
  preserve Plan's mandatory guards and Project hooks.
- Do not trigger Plan for previews, pending questions, exhausted rounds, failed
  publication, or closure that waives unresolved decisions.

## 1.2.1

- Present lettered, initially unchecked choices with a bold Recommended suffix.
- Read a single checked option as answer evidence; support normal comments with
  question IDs and optional feedback, including several answers in one comment.
- Collapse supporting context and diagrams while keeping the recommendation visible.
- Detect changed selections during publication and reject ambiguous checkbox evidence.

## 1.2.0

- Present complexity findings and let the user choose the total number of new issues.
- Require explicit approval of the exact proposal before any publication writes.
- Bind local approval receipts to the proposal, source, prerequisites and selected count.
- Keep honest scores for approved larger issues instead of forcing recursive splits.
- Prevent cancelled, rolled-back operations from being resumed.

## 1.1.0

- Require Backlog before Specify and set Feature Specification after binding the spec.
- Automatically dispatch available Superspec Brainstorm, falling back to Clarify.
- Share unattended GitHub question rounds, creator mentions, answer evidence and spec integration.
- Remove question-count caps; enforce a creator-configurable seven-round limit.
- Stop waiting issues immediately; use Need Clarifications and Ready consistently.
- Gate planning on Ready and preserve customization through composable presets.

## 1.0.0

- Added issue inspection, prerequisite reporting, effort validation and publication.
- Added recursive decomposition, native sub-issues and dependency reconciliation.
- Added Specify gating, original-issue binding, parent rollup and Archify plan handoff.
