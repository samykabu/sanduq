# Managed workflow projects

Applies when `.specify/workflow.yml` exists. These rules take precedence over the standalone
confirmation flow.

- Resolve logical status names through `scope.statuses` before showing instructions.
- Reuse the `inspect` snapshot: pass it as `--snapshot <file>` to `gate`, `approve`, `publish`
  and `bind`; the runtime reuses it (one issue fetch, `snapshot_reused` in the output) while its
  fingerprint matches the live issue and it is within `scope.board_cache_seconds`.
- Read the scope preference before proposing a decomposition. A configured keep-together band
  settles the count: keep a matching issue as one leaf with its full scope, acceptance and
  enriched Specify prompt. The publisher records a project-policy decision instead of a new
  human approval, so never split a matching issue or ask a redundant count or approval question.
- Publish only after every remaining genuine scope decision and prerequisite is resolved.
- The workflow Scope receipt records the approved score as `effort_score` (1, 2, 3, 5, 8, 13 or
  21); the profile tier follows from it.
- Return to the active workflow Scope claim, or without one invoke the workflow continuation for
  the feature after successful binding. The dispatcher, not this skill, starts Specify and may
  render the spec from the approved analysis (`render-spec`).
- Keeping a feature together never removes implementation task sub-issues later.
