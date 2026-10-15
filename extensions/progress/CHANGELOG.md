# Changelog

## [1.0.1] - 2026-10-15

- Hooks run `scripts/hook.py`, a standard-library entry that exits before importing Progress for an unbound session
  (about 30 ms instead of about 105 ms; a bound debounced event about 60 ms instead of about 120 ms).
- Hooks write nothing in a project where Progress was never initialised; an unbound session is logged once per id.
  `diagnostics.log*` and `*.lock` under `.specify/progress/` join the git exclude list.
- A debounce window publishes the clean-to-dirty transition once instead of rewriting `report.json` and `data.js` on every event.
- Codex `spawn_agent` and other asynchronous launches no longer finish on the launch response. A finished child that runs
  again starts a new generation. Child lane ids (`C<n>`) are kept in `state.json` and never renumber. Host snapshots moved from `.view/host` to the git-ignored `.host/` (moved on first access), so deleting
  `.view/` keeps every child id; blockers follow a child into the lane it merges into; linking and splitting a child keeps its newest lifecycle.
- Writes refuse a symlink or junction at `facts.jsonl`, the view files and copied assets (`PROGRESS_UNSAFE_TARGET`).
- The UI poller abandons a data.js load that never settles after 10 s and tries again (Chromium under heavy load sometimes
  fires neither load nor error, which froze the page).
- `os.replace` retries a Windows sharing violation. The projection reads only the runs the ledger names.
- Flaky test fixes on Windows and under load; regression tests and docs for the review fixes.

## [1.0.0] - 2026-10-15

- First release. A live report for one Spec Kit feature, built as a deterministic projection of `tasks.md`,
  the Workflow ledger, a small tracked fact file and the host's native hook payloads.
- Verbs: `init`, `bind`, `refresh`, `status`, `lane`, `block`, `unblock`, `decide`, `note`, `theme`, `export`.
- Native hooks for session start, tool use, stop and session end. A successful automatic refresh prints nothing.
- Integration verbs for Workflow: `attempt record` stores a legacy attempt fact (origin `legacy`, never overriding producer state) and `runs --json` returns the `progress.runs.v1` run projection.
- Four themes, light and dark, importable from the Illustrate theme.
- Token benchmark against a hand-maintained Markdown report and the legacy Workflow report protocol.
