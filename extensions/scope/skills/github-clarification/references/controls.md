# Creator controls and round limit

The default is **7 question rounds**, shared by Clarify and Brainstorm. Invocations while
waiting do not count. After answers to the last allowed round, another evaluation may resolve
the issue but cannot post a further round unless the creator raises the limit. Reaching the
limit with unresolved questions keeps **Need Clarifications** and posts a short limit report.

Recognized unquoted issue-creator comments:

- `/clarification max-rounds 10` (any positive integer)
- `Maximum clarification iterations: 10`
- `/clarification close`, `Close the clarification process`, or `No more questions`
- `/clarification reopen` to revoke an earlier closure after restoring Feature Specification

Only explicit controls count; a bare number answering a question is not a limit. Closure never
manufactures answers: record the remaining decisions as explicitly waived and explain the
assumptions. The issue must be back in Feature Specification before a closure comment is
processed.
