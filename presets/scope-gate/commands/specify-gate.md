---
description: "Create or update feature specifications from natural language descriptions, only for one explicitly identified GitHub issue with a fresh approved Scope receipt, keeping every open decision as a clarification marker. Use to write the spec for a scoped issue. (Sanduq managed)"
---

## Mandatory Scope entry contract

Before executing ANY core Specify step or other hook, require exactly one explicit
GitHub issue number from this invocation. If missing, STOP with:
`SCOPE_REQUIRED: supply a GitHub issue number and run /speckit-scope-run <issue> first.`

Read `.specify/extensions/scope/commands/speckit.scope.guard.md` and execute its guard. If the
extension is absent, hook configuration is malformed, a read fails, or the guard
returns nonzero, STOP. Do not create directories, branches, specs or issues.
Use the returned scoped prompt as the feature description for the core flow below.
Do not accept a score merely typed by the user; verify the live issue receipt and
effort label. A repeated guard in the same invocation may reuse the successful result
before any requirement change. Do not reinterpret another number in the prompt as an
issue ID. Any out-of-scope expansion returns to Scope first.

Override the core Specify inline clarification loop: retain ALL material unresolved
decisions as `[NEEDS CLARIFICATION: ...]` markers, with no three-marker cap. Do not
guess away decisions to meet that cap, present questions in chat, or wait for answers.
Write the specification and quality checklist honestly, leaving unresolved-clarification
checks unchecked. Do not set Ready from Specify.

Inside a managed workflow claim (`.specify/workflow.yml` exists), the claim's stage
reference owns binding and hand-off; gate and bind flags are in
`.specify/extensions/workflow/skills/workflow/references/scope-binding.md`. Without
`.specify/workflow.yml`, also follow `.specify/extensions/scope/references/specify-standalone.md`.

The instructions below are composed from the installed upstream Spec Kit command.
Where the upstream text below conflicts with the claim's `reference_text`, the `reference_text` wins;
upstream hook prompts are skipped inside a claim.
