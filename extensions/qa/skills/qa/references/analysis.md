# QA analysis contract

Run after `tasks.md` exists and before implementation.

Build a coverage matrix for every acceptance scenario. Check for applicable unit, integration, E2E,
API-contract, screenshot, accessibility, fixture, and diagram work. Add concrete tasks to `tasks.md`
inside marker-delimited sections so reruns replace rather than duplicate generated tasks.

In lifecycle-integrated mode, analysis is a gate: finish with no unexplained critical gaps. Record
freshness with:

```text
python .specify/extensions/qa/scripts/qa_state.py record --kind analyze --feature <feature-path>
```
