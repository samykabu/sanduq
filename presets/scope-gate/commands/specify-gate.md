---
description: "Create a specification only for an explicitly identified, scored GitHub issue."
---

## Managed workflow precedence

When `.specify/workflow.yml` exists, first read the Sanduq workflow policy and
`.specify/extensions/workflow/skills/workflow/SKILL.md`. During an active stage,
return to that dispatcher after the domain work; never independently chain Plan
or stop the entire lifecycle. With `resume_on_reinvoke: reread-answers`, Need
Clarifications allows reading and applying new answers without a manual status
move. If no new human answers or material input changes exist, report waiting
without publishing another round. These managed rules override conflicting
legacy status/stop instructions below. Unmanaged projects retain the old flow.

## Mandatory Scope entry contract

Before executing ANY core Specify step or other hook, require exactly one explicit
GitHub issue number from this invocation. If missing, STOP with:
`SCOPE_REQUIRED: supply a GitHub issue number and run /speckit-scope <issue> first.`

Read `.specify/extensions/scope/commands/guard.md` and execute its guard. If the
extension is absent, hook configuration is malformed, a read fails, or the guard
returns nonzero, STOP. Do not create directories, branches, specs or issues.
Retain the verified issue identity for `after_specify` binding. Use the returned
scoped prompt as the feature description for the core flow below. Do not accept
a score merely typed by the user; verify the live issue receipt and effort label.
If the mandatory `before_specify` scope hook invokes the same guard again, reuse
the successful result only within this invocation and before any requirement change.
The Scope hook does not create branch metadata. Core Specify still owns the feature
directory and specification. Do not reinterpret another number in the prompt as
an issue ID. Any out-of-scope expansion returns to Scope first.

The instructions below are composed from the installed upstream Spec Kit command.

Specify may run only against **Backlog** issues. After the spec exists, its mandatory
Scope bind hook sets **Feature Specification**. Complete ALL mandatory after_specify
hooks, including `speckit.scope.after-specify`, which automatically invokes Superspec
Brainstorm if installed/enabled/available, otherwise Clarify. No question or review
confirmation is requested in chat; the clarification workflow posts on GitHub.
Do not set Ready from Specify itself. Brainstorm/Clarify decide readiness afterward.

Override the core Specify inline clarification loop: retain ALL material unresolved
decisions as `[NEEDS CLARIFICATION: ...]` markers, with no three-marker cap. Do not
guess away additional decisions to meet that cap, present questions in chat, or wait
for answers before post-execution hooks. Write the specification and quality checklist
honestly, leaving unresolved-clarification checks unchecked. Then run bind, Project
sync, and the mandatory clarification dispatcher in priority order. Clarify/Brainstorm
owns posting questions, integrating answers and reevaluating those checklist items.
Skip optional hooks that would interrupt this unattended handoff with a chat prompt.
