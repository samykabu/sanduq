---
description: Review and enable the current automatic archive policy
---

# Enable automatic archival

First run `python .specify/extensions/memory/scripts/archive.py policy`. Present
the concrete policy, named verification commands, scope restrictions and its
`policy_hash`. Explain that work queues after implementation, is processed in the
next local session after merge into the configured target branch, uses independent synthesis review,
relocates required fixtures and deletes the complete feature folders through two
scoped commits. Other assets remain in Git. No per-operation human approval follows.

Review the policy once with the owner before enabling it. This confirmation is
required by the owner's archive policy, not by a speculative safety rule. Changes
to the policy/implementation invalidate approval and need renewed review.

Once this exact policy is approved and the extension is committed, run
`python .specify/extensions/memory/scripts/archive.py enable --approve-hash <hash>`.
It records local approval; it does not archive existing specs or push changes.
To disable, run `... archive.py disable`. Do not enable as part of installation.
