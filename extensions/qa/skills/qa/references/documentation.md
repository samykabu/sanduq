# QA documentation contract

Generate tester-facing instructions for the implemented feature. Include prerequisites, deterministic
test data, role and permission context, numbered actions, expected results, important alternate
states, UI screenshots, API examples when applicable, and links to useful diagrams.

Validate every image, link, request, response, and expected result. Mark unavailable evidence as a
follow-up; never substitute an invented example. Record every generated output relative to the
repository root:

```text
python .specify/extensions/qa/scripts/qa_state.py record --kind document --feature <feature-path> --output <path>
```
