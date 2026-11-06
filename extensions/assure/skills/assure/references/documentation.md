# QA documentation contract

Generate tester-facing instructions for the implemented feature, following `qa/assertions.json`. Include
prerequisites, deterministic test data, role and permission context, numbered actions, expected results,
and the alternate states an assertion names. Add a UI screenshot only where an assertion, a reference or a
manual step needs one, and reuse an existing capture first. Add API examples when applicable and links to
useful diagrams.

Validate every image, link, request, response, and expected result with
`.specify/extensions/assure/scripts/audit_qa.py`. Mark unavailable evidence as a follow-up; never
substitute an invented example. Record every generated output relative to the repository root with
the `assure_state.py record` call in the command's last step.

## Report shape

Feature path; the inventory summary the scan printed; impacted projects; manual paths written; then
the command's own items.
