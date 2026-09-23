# Changelog

## 1.2.1

- A reviewed migration now rebinds a checkpoint to the current policy. A release
  that only adds a policy section (1.2.0 added `ci:`) left every finished feature
  reading `POLICY_CHANGED` in the CI gate even though no work had changed.
  `migrate` records the policy change, invalidates exactly the stages the policy
  cutoff says a semantic change reached, and preserves the rest as historical.

## 1.2.0

- Where CI runs is a project decision recorded under `ci:` in `.specify/workflow.yml`;
  shipped workflow assets are rendered from it instead of carrying a fixed runner.

## 1.0.0 (unreleased)

- Review Home pilot hardening: shared portable UTF-8 hashes across Workflow,
  QA and manuals, respecting `-text`, binary data, SQL bytes and lone CR.
- Publication index preflight and path-level stale-receipt diagnostics; no
  automatic staging and no relaxation of source freshness after target merges.
- Exclude derived graph output from implicit documentation inputs, retain
  explicit graph output integrity, and document exact-head/post-merge verification.
- Upgrading existing pilot state can invalidate receipts where hash semantics
  or implicit inputs changed. Review drift and migrate/revalidate affected stages;
  never rewrite historical receipts as new test execution.

- Live-pilot correction: only reliable measured context can pause the default workflow.
  Unknown/estimated/stale telemetry continues automatically; explicit strict mode remains opt-in.

- Initial managed workflow runtime, presets, issue adapters and local verification. Release and live acceptance pending.
- Exact-source dependency and preset installer, host registration checks, local backups,
  symlink-preserving rollback and an outer transaction for workflow package updates.
- Required artifact/source freshness, parent-scoped task mappings, reviewed migrations,
  versioned state contracts and policy-aware CI gates.
- Explicit clarification refresh, existing-feature revalidation, owned legacy alias
  upgrades and project readiness checks before dispatch.
- Resolve PR features from the target/head common ancestor, excluding unrelated
  target-branch changes; missing shallow history blocks with a fetch instruction.
