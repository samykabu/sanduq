# Delegation and lean execution

Read when a claim carries a `delegation` route or an `environment` (lean execution). Invoking the
command and decisions stay in [delegation-and-decisions.md](delegation-and-decisions.md).

## Routing rule

The claim's route decides: each candidate's `route_kind` says who runs the work. Run it natively
when the claim lists the native candidate (`route_kind: native`, `route_reason: native-first`);
the host pins the exact model through the tier's role file. Use an external candidate only for
the reason it records: `native-unsupported:<capability>`, `native-failed:<category>`, or
`external:cross-vendor`, the named exception for debate and consultation routes that need the
other vendor's model. A native attempt the host cannot support selects the external candidate
once; a temporary native failure retries natively within `lean_execution.max_attempts` before
falling back. Never substitute a model silently: a rejected model stops at
`FALLBACK_CONFIRMATION_REQUIRED` ([Confirmed fallback](#confirmed-fallback)).

## Delegation

`delegate_dispatch.py start --feature specs/<feature> --id stage:<stage> --claim-token <token>`
launches the external candidates only; then `delegate_dispatch.py collect --feature
specs/<feature> --run-id <id>` until terminal, following any `replacement` run ID. A
`successful` delegate result means the driver saw no failure or abandonment signal; it does not
verify the objective. It is candidate evidence, not a passed stage: inspect outputs and checks
before the receipt. Failed, abandoned or unresolved work keeps the claim active. An unreported
actual model stays unverified. Disabled mode ignores routing tags and uses the user's selected
model.

A rejected model falls back to the next candidate automatically, as does a start that provably
created no run (or whose driver exited 5 with proof no agent launched). On
`DELEGATION_START_UNCERTAIN`, never start again: run `delegate_dispatch.py recover --feature
specs/<feature> --intent-id <id>`; collect a bound run, or on `found: false` close the intent
with `delegate_dispatch.py abandon --feature specs/<feature> --intent-id <id> --reason
"<why>"` and start again. On `DELEGATION_LEDGER_BUSY` or `DELEGATE_SKILL_INSTALL_BUSY`, retry;
a dead owner's lock on this host is recovered automatically, so never delete a lock whose named
process is running. An observation timeout is not a failed run.

To choose a candidate, add `--harness <codex|claude> --model <id>` to `start`, always together.
The pair must already be in the stage's resolved route; it selects, never adds, and each stage
keeps its own allowlist. An invalid or unavailable pair fails before any launch. After an
explicit choice there is no fallback, automatic retry or `reassign`. `--type` on a stage start
must equal the stage's own type.

## Security

Every external run starts the agent CLI with `--clean-env`: it sees only the driver's runtime
basics, `PATH`, `HOME`/`USERPROFILE`, `SystemRoot`, `TEMP`/`TMP`, `APPDATA`/`LOCALAPPDATA`,
`ComSpec`, the chosen harness's own provider credentials (`ANTHROPIC_*` and
`CLAUDE_CODE_OAUTH_TOKEN` for Claude, `OPENAI_*` and `CODEX_HOME` for Codex) and every
`SANDUQ_*` name. `GH_TOKEN`/`GITHUB_TOKEN` reach only routes that use the GitHub adapter: the
Execute orchestrator and the discovery and coordination stages. Review and analysis routes (the
`review` work type or model profile) start with the driver's read-only `--sandbox`. The ledger
attempt records `clean_env`, `kept_env_names` (names only), `github_access` and `permission`.

Review work stays refused through the external driver for now (the PH-01 interim): a route whose work type is `review` (the Analyze and Review stages,
`[Review]` tasks) or that names the `review` model profile fails with
`DELEGATION_REVIEW_ROUTE_UNSAFE` at claim and start, `doctor` lists the refused routes as a
warning, and tasks.md marks such a task `refused:DELEGATION_REVIEW_ROUTE_UNSAFE`. Run reviews
natively in the selected host. Every other route is unchanged.

Native work: the top-level session records a native task or stage with `delegate_dispatch.py
record-native --feature specs/<feature> --id <stage:name|T###> --token <claim token>
--host-agent-id <id> --requested-model <m> --command "<check>" --expect counts|files`; the check
decides the status, and a review or QA by the authoring lineage is refused
(`SAME_LINEAGE_REVIEW`). `attest-native ... --id stage:<stage> --claim-token <token>
--requested-model <m> [--reported-model <m>]` remains for a stage: self-asserted, labelled
`kind: native`, never a dispatched run. Both are top-level only (`NATIVE_ATTESTATION_FORBIDDEN`
in a worker, subagent or delegated orchestrator). A claim with no route completes without them
(`NATIVE_ATTESTATION_NOT_NEEDED`).

## Confirmed fallback

When the CLI rejects the requested model, `collect` starts nothing and stops with
`FALLBACK_CONFIRMATION_REQUIRED`. The message names the stage or task, the harness and model,
the rejection line from stderr, the configured substitute (on Codex the CLI default reads "CLI
default, model unknown: Codex does not report it") and three exact commands: confirm, pick an
allowed model, or run natively (a stage: `attest-native` after doing it; a task: `adopt`). Show
it to the user and wait. Only the user may confirm, in the
conversation; then the top-level session runs `delegate_dispatch.py collect --feature
specs/<feature> --run-id <id> --confirm-fallback <requested>=<substitute>`, which starts the
substitute for one run. The guard and the dispatcher refuse that flag from a worker, subagent or
delegated orchestrator. The substitute must be pre-listed: an explicit model in the route's
`fallbacks`, or the CLI default only when the route sets `allow_default_model: true`. Collect,
the ledger and status carry `requested_model`, `substitute_model`, `actual_model` (harness
telemetry, else `unreported`), `confirmed_by` and `fallback_used`; with no reported model the
summary reads "fallback confirmed; model unverified".

## Lean execution (default for lite and standard)

Lean execution is on for a lite or standard feature unless the policy sets
`lean_execution.enabled: false`, and on for every tier when it sets `true`. Claim and status print
`lean_execution: on (tier default)`, `on (policy)`, `off (policy)` or `off (default)`; trust that
line and the claim's `execution_owner` over any prose default. When it is on, one lifecycle
coordinator keeps claims, scheduling, integration, receipts and publication; never create or
dispatch another coordinator. Execute, Tasks-to-Issues, Ready and PR claims return
`execution_owner: coordinator` without a model route, as does an exact
`delegation.fixed_collection_commands.verify` match. Semantic stages keep their routes and
successful attempt checks. When it is off the legacy protocol applies.

```yaml
lean_execution:
  enabled: true
  timeout_min_seconds: 300
  timeout_max_seconds: 7200
  finalization_seconds: 120
  max_attempts: 3
  verification_plan: specs/42-booking-refund/verification-plan.json
  preflight_manifest: specs/42-booking-refund/preflight.json
  scope_analysis: specs/42-booking-refund/scope-analysis.json
```

Only `enabled` is required; bounds satisfy finalization < minimum <= maximum <= 28800 seconds.
`verification_plan`: see [verification-plan.md](verification-plan.md). `preflight_manifest`
selects deterministic checks for doctor and before Execute or later claims; findings block
execution. `scope_analysis` is the initial analysis path; without it the Scope claim prints
`<analysis.json>`, which must be replaced with the actual new analysis. `claim.environment`
carries the token and session for native commands and worker launches.

Every lean launch needs `--deliverable "<artifact and acceptance result>"`; a second attempt for
the same identity also `--correction-plan "<specific correction and check>"`; further attempts
`--diagnosis <project-relative JSON>` with concrete `cause`, `evidence` (an existing file) and
`change`. Admission is checked under the ledger lock, so another model or run ID cannot reset
the history. Lean launches try the selected candidate only and never escalate failed work
automatically; `reassign --reason "<specific correction>" [--diagnosis <JSON>] --nonce <dispatcher_nonce>` keeps the prior
candidate, so it is refused with `LEAN_PROVIDER_REJECTED` after a model rejection (start with
another eligible `--harness`/`--model` pair instead). `max_attempts` (default 3) caps attempts
per identity, blocked and abandoned intents not counted; the next one fails with
`LEAN_ATTEMPT_LIMIT_REACHED`: stop and ask the owner. Failure categories (provider rejection, harness failure, timeout, task failure,
missing evidence, abandonment, unknown) stay distinct; a timeout while collecting is not a
failed task. Reserve `finalization_seconds` for an honest partial handoff listing changed
files, executed checks and remaining work; the worker writes it before the watchdog fires.

`workflow.py status --feature specs/<feature> --runs <run-root>` (repeat for worktrees) shows
elapsed time, latest event, next action and per-harness usage; a successful harness is never
silently task acceptance. `delegate_dispatch.py classify --feature specs/<feature> --run-id
<id> --attribution <JSON>` records the failure `domain` (product, test, environment, workflow,
owner-interruption or unknown), `actor`, `reason` and existing `evidence`.
