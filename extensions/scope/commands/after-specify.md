---
description: "Automatically choose and execute the mandatory post-Specify clarification skill."
---

# Mandatory post-Specify clarification

Use the issue number bound by Scope in this same Specify invocation. Run:

```text
python .specify/extensions/scope/scripts/clarification.py dispatch <issue-number>
```

On failure STOP. On success read and actually execute the returned skill for the
returned issue: `$speckit-superspec-brainstorm` when the Superspec extension is
installed, enabled and its skill is available; otherwise `$speckit-clarify`.
Do not merely print the selected command, offer it as a next step, ask permission,
or execute both skills. The customization on that skill invokes the shared unattended
GitHub clarification workflow. Pass the explicit issue number through.

The live issue must already be Feature Specification. Do not report successful
Specify completion before this mandatory skill finishes its current round (posting
questions and entering Need Clarifications, or completing and entering Ready).
This does not wait in chat for answers or loop while the issue is waiting.
