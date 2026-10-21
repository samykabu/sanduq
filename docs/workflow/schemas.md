# Workflow schemas

This page lists the JSON schemas that ship in
[`extensions/workflow/schemas/`](../../extensions/workflow/schemas/policy-v1.schema.json),
what each one describes, and the fields you are most likely to read or edit. The schemas use
JSON Schema draft 2020-12. The runtime writes most of these files itself, so treat this page as a
reading aid, not an invitation to hand-edit state.

Back to the [Workflow guide](../../extensions/workflow/README.md).

## Overview

| File | Describes | Lives at |
| --- | --- | --- |
| [`policy-v1.schema.json`](../../extensions/workflow/schemas/policy-v1.schema.json) | Project policy chosen at init and edited later | `.specify/workflow.yml` |
| [`checkpoint-v1.schema.json`](../../extensions/workflow/schemas/checkpoint-v1.schema.json) | One feature's resumable run state | `specs/<feature>/workflow/` |
| [`receipt-v1.schema.json`](../../extensions/workflow/schemas/receipt-v1.schema.json) | One completed stage, stored inside the checkpoint's `receipts` | inside the checkpoint |

The checkpoint schema references the other two: its `policy` field is a policy document and each
entry in `receipts` is a receipt.

## Policy (`policy-v1.schema.json`)

Title: "Sanduq workflow project policy v1". Required top-level keys: `schema_version` (always `1`),
`processes`, `execution`, `providers`, `issue_sync`, `clarification`, `context`, `finalize` and
`updates`. The schema requires `clarification` and `updates` to be present but does not
describe their shape.

| Key | What it controls |
| --- | --- |
| `processes.qa`, `processes.user_manual` | Booleans for the independently selected QA Assure and User Manual processes. |
| `execution.engine` | `auto`, `speckit` or `superspec`. |
| `execution.checkpoints` | `required-only` or `every-phase`. |
| `providers.clarification`, `providers.tasks` | `prefer-superspec`, `core` or `superspec`. |
| `issue_sync` | `taskstoissues` is `required` (every task mapped at Tasks-to-Issues) or `phase-lazy` (each phase mapped when it starts; Ready still needs every task mapped); `parent_link` is fixed to `native-subissue`. |
| `profiles` | Optional. `enabled`, `lite.max_score` (default 3), `standard.max_score` (default 8). Absent means every feature runs the full stage list. |
| `clarification.max_questions_per_round`, `clarification.in_session_first_round` | Optional question cap per round (absent: no cap) and in-session first round (default false). |
| `artifacts` | Optional. `budgets` (`spec_kb`, `plan_kb`, `research_kb`, `tasks_detail_lines`) checked by `workflow:lint`, and `enforce` (`lite-standard`, `all` or `warn`). |
| `project_sync.points` | Optional list of stages at which Project Sync runs: `specify`, `plan`, `analyze`, `taskstoissues`, `execute`, `pr`. Absent means all six. |
| `scope.board_cache_seconds` | Optional Scope board cache TTL in seconds (default 300, 0 disables). |
| `decisions` | Optional. Stage-neutral GitHub issue decisions: `transport` (`github-issue`), `authorized_users`, `project_field`, and optional `lifecycle_status` (boolean, default true). Omitted in older policies. |
| `context` | `mode` (`strict`, `measured-only` or `measured-with-estimated-fallback`), `max_fraction`, `checkpoint_fraction`, `reserve_fraction`. See [Context](stages.md#context). |
| `finalize` | Fixed: `{"create_pr": true, "merge": false}`. The dispatcher opens a PR and never merges. |
| `delegation` | Optional. See below and [delegation](delegation.md). Absent legacy policies default to disabled. |
| `receipts.require_input_roles` | Optional boolean. See [Receipt contract](state-files.md#receipt-contract-160). |
| `skills.inventory_thresholds` | Optional `skill_count` and `description_bytes` overrides. See [Skill inventory](utilities.md#skill-inventory-doctor). |
| `ci` | Where and how the project runs the CI workflow files Sanduq renders. See below. |

### `delegation`

Required keys when present: `enabled`, `install_scope` (`project` or `global`), `stronger_retry`
(`0` or `1`), `models`, `routes`, `overrides` and `fixed_collection_commands`.

- `models.codex` and `models.claude` each map the five tiers `high`, `standard`, `light`,
  `documentation` and `review` to a model name.
- `routes` holds one route per work type: `discovery`, `implementation`, `qa_author`, `qa_collect`,
  `documentation`, `review` and `coordination`. The deprecated pre-1.7 `qa` key is still accepted.
  Each route has `preferred` and `fallbacks`.
- A route candidate has a `harness` (`selected`, `codex` or `claude`) and exactly one of `tier` or
  `model`. `discovery` routes reject the `light` tier.
- `fixed_collection_commands` may name only `verify`, with the exact resolved command string.

### `ci`

Required keys: `provider` (`github-actions` or `none`), `policy` (`hosted-allowed` or
`self-hosted-required`), `runners` (`linux` required, `windows` and `macos` optional) and
`capabilities` (`system_packages`, `python`, `python_version`).

- `ci.gate` (absent on legacy installs): `mode` (`disabled`, `advisory` or `required`), `scope`
  (`managed-only` or `all-prs`), and `rules`, a set of booleans: `receipts`, `decisions`, `tasks`,
  `task_links`, `documentation`, `portability`, `candidate_merge` and `live_answers`.
- `ci.gate.affected_command`, `ci.gate.verification_check` and `ci.gate.verify_command` are the
  optional hooks described in [CI evidence and runner policy](runner-policy.md).
- `ci.exceptions` entries (`workflow`, `platform`, `reason`, `removed_by`, `decided` as
  `YYYY-MM-DD`) record each GitHub-hosted runner set allowed under `self-hosted-required`.

## Checkpoint (`checkpoint-v1.schema.json`)

Title: "Sanduq feature checkpoint v1". Required keys: `schema_version`, `run_id`, `branch`,
`feature`, `issue`, `policy_digest`, `dependency_digest`, `policy`, `commands`, `receipts`,
`generation`, `active` and `status`.

`schema_version` is the checkpoint's own version, separate from the policy's. Version 2 drops `repo_path`.
Workflow reads versions 1 and 2 and writes version 2, so the first write after an upgrade migrates a version-1
checkpoint. Scope reads both.

| Field | Meaning |
| --- | --- |
| `repo_identity` | Portable repository identity (1.8.0+): `remote`, `root_commit` and `shallow`. See [Checkpoint identity](state-files.md#checkpoint-identity-and-relocating-a-repository-180). |
| `repo_path` | Version 1 only: the legacy absolute root. Never compared by 1.8.0+; `relocate` records a pre-1.8.0 value as `old_identity.legacy_repo_path`. |
| `branch`, `target_branch` | The bound feature branch and its target. |
| `issue` | The bound GitHub issue. |
| `policy_digest`, `dependency_digest` | Fingerprints compared on load. A changed dependency digest makes `claim` refuse with `DEPENDENCY_CHANGED` until you run `migrate`. |
| `commands` | Map of stage to the resolved command selected for it. |
| `receipts` | Map of stage to receipt (see below). |
| `generation` | Write counter. |
| `active` | `null`, or the active claim: `stage`, `token`, `claimed_at`, `session_id`, `context`, `baseline`, `mode` (`initial`, `revalidate` or `bind-only`). |
| `profile` | `{tier, score, fixed_at}`: the effort tier (`lite`, `standard` or `full`) frozen at the first Plan claim when profiles are enabled. |
| `skipped` | Map of stage to reason for the stages the tier does not run (`tasks` is merged into `plan` on lite and standard). |
| `status` | `in-progress`, `paused`, `ready_to_finalize`, `pr_open`, `blocked` or `failed`. |
| `migrations[]` | Reviewed migrations: `reason`, `from`, `to`, `at`, `invalidated`, `preserved_as_historical`. |
| `relocations[]` | Reviewed `relocate` entries: `actor`, `at`, `reason`, `old_identity`, `new_identity`, and flags such as `branch_rebound` and `history_changed`. |
| `stage_plan` | 1.12.0+: `{v, generation, stages}`, the selected stage order after policy filtering, as of the last write. |
| `next_action` | 1.12.0+: Workflow's own `next` evaluation as of the last write: `{text, stage, kind, evaluated_at, generation}`. `kind` is `active-claim` while a stage is claimed and `next-stage` otherwise. `null` when it could not be evaluated. |
| `lifecycle_outbox` | 1.12.0+: lifecycle events queued with a state change and not yet appended to `lifecycle.jsonl`. Normally absent. See [lifecycle events](state-files.md#lifecycle-events-stage-plan-and-next-action-1120). |
| `head`, `updated_at` | Last recorded commit and write time. |

## Receipt (`receipt-v1.schema.json`)

Title: "Sanduq completed stage receipt v1". Required keys: `stage`, `outcome` (always `passed`),
`summary`, `inputs`, `evidence`, `command`, `dependency_digest`, `fingerprints` and
`completed_at`. Hashes are 64-character lowercase hex SHA-256 values.

`stage` is one of `scope`, `specify`, `clarify`, `plan`, `tasks`, `qa_analyze`, `manual_analyze`,
`analyze`, `taskstoissues`, `execute`, `verify`, `review`, `qa_document`, `manual_update`, `ready`
or `pr`.

Stage-specific fields include `unresolved`, `answers_applied`, `blocking_findings`,
`native_links_verified`, `parent_issue`, `images_verified`, `pr_url`, `effort_score` (Scope; one of
1, 2, 3, 5, 8, 13, 21, required when profiles are enabled), `lint` (`{ok, findings}`, Analyze
recorded as `workflow:lint`) and `lazy` (Tasks-to-Issues under `phase-lazy`).

Optional fields added in 1.6.0 and later (all backward-compatible):

| Field | Meaning |
| --- | --- |
| `input_roles` | Per-input `role` (`dependency` or `consulted`); `consulted` requires `because`. |
| `amendments[]` | Written by `workflow.py amend`: `path`, `old_hash`, `new_hash`, `reason`, `assessment`, `actor`, `at`, `staled`. |
| `stale` | Runtime only. `evidence-amended` (`stage`, `path`, `at`) or `ci-lane-gap` (`stage: verify`, `lanes`, `run_id`, `at`). |
| `source_inventory` | Runtime only. `{path, sha256}` of the side file `workflow/inventory/<stage>-<claim_id>.json` (relative to the feature) holding the Verify, Review or Ready source inventory. |
| `source_fingerprints` | Legacy inline inventory of the source tree; still read. |
| `text_fingerprints` | Runtime only. Whitespace-normalised hashes of Markdown fingerprints, used by `revalidate-upstream` to treat CRLF and trailing-space edits as unchanged. |
| `revalidated_upstream` | Runtime only. `{episode_id, at, actor, via, paths}` from the `revalidate-upstream` operation that re-recorded (`receipt`) or re-stamped (`whitespace-only`) the receipt. |
| `head`, `source_key` | Commit the receipt was recorded at, and the canonical source key at that commit. |
| `ci_evidence` | Written only by `revalidate --stage verify --check-run`: `run_id`, `attempt`, `head`, `source_key`, `tier`, `lanes`, `required_lanes`, `lane_gap`, `conclusion` (`success`), and run metadata. |
| `diff_reviewed` | Written only by `revalidate --stage review --diff-reviewed`: `evidence`, `base`, `head`, `hash`, `diff_sha256`, `reviewer`, `at`. |
| `revalidations[]` | Checked revalidations after source drift. |
| `delegation_ledger_trust` | `trusted` or `unverified-local`, recorded when a delegated stage completes. |

The rules behind these fields are in [Receipt contract](state-files.md#receipt-contract-160) and
[Source drift and CI evidence](runner-policy.md#source-drift-and-ci-evidence-160).

## Related pages

- [State files](state-files.md)
- [CI evidence and runner policy](runner-policy.md)
- [Delegation](delegation.md)
- [Glossary](../reference/glossary.md)

Decision lifecycle parks mapped Backlog or Feature Specification while questions wait,
then returns an owned park to mapped Feature Specification under `reread-answers`.
Advanced statuses remain protected. `lifecycle_status` defaults to true for new and legacy policies.
