---
description: "Runs as the after_implement hook: refreshes Scope parent progress. Use when asked to update stale parent progress."
---

# Reconcile scope parents

As the after_implement hook, take `issue` from the implemented feature's `scope-source.json`
(`.specify/feature.json` names the feature) and run
`python .specify/extensions/workflow/scripts/scope/scope.py reconcile <issue> --apply`: it updates only that
issue's Scope ancestors. With no bound issue, or when asked to refresh every parent, run
`python .specify/extensions/workflow/scripts/scope/scope.py reconcile --apply`.
Report actual changes or a read/authentication error. Parent progress tables include
all native children. Only all-Done descendants permit a parent to become Done and
close as completed. A reopened child reopens its scope ancestors. Do not apply this
policy to arbitrary epics without a Scope parent receipt.
