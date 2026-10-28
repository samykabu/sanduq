# Specify without a managed workflow

Read this only when `.specify/workflow.yml` does not exist.

Specify may run only against **Backlog** issues. Keep the verified issue identity for the
`after_specify` binding; the Scope hook does not create branch metadata, and core Specify still
owns the feature directory and specification.

After the spec exists, complete ALL mandatory after_specify hooks in priority order: the Scope
bind hook sets **Feature Specification**, then Project sync, then
`speckit.workflow.scope-after-specify`, which invokes Superspec Brainstorm when it is installed, enabled
and available, otherwise Clarify. Clarify or Brainstorm posts the questions on GitHub,
integrates answers, reevaluates the checklist items and decides readiness. Ask no question and
request no review confirmation in chat. Skip optional hooks that would interrupt this
unattended handoff with a chat prompt.
