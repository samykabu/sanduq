---
description: "Runs as the after_implement hook: refreshes Scope parent progress. Use when asked to update stale parent progress."
---

# Reconcile scope parents

Run `python .specify/extensions/scope/scripts/scope.py reconcile --apply`.
Report actual changes or a read/authentication error. Parent progress tables include
all native children. Only all-Done descendants permit a parent to become Done and
close as completed. A reopened child reopens its scope ancestors. Do not apply this
policy to arbitrary epics without a Scope parent receipt.
