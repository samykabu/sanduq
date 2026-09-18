---
name: speckit-superpowers-bridge
description: Route the legacy short Bridge entry through its current execution owner.
---

<!-- sanduq-workflow-alias:v1 -->
This is a Sanduq-owned compatibility entry, not a fork of the upstream Bridge.

When `.specify/workflow.yml` exists, read the installed Sanduq workflow skill and
run workflow doctor. Resolve the explicit feature/issue and invoke
`speckit.workflow.continue`. An active legacy handoff must be reconciled from actual
evidence before another executor starts. Never create or mark a legacy handoff
executing from this alias. Stop this invocation when the dispatcher returns.

Without managed policy, invoke the installed native
`speckit.speckit-superpowers-bridge.execute` command and return. Read its current
generated instructions; do not retain a copied, potentially outdated executor here.
If that native command is unavailable, report the missing Bridge installation.
