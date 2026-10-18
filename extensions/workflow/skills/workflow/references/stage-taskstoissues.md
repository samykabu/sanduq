# Stage reference: taskstoissues

## Required work and evidence

This is the core Tasks-to-Issues invocation with a managed adapter. Keep its prerequisite and
repository validation, but replace its global T001-title deduplication and issue-creation loop:

1. Read tasks.md and its dependencies. Write a JSON object mapping each task ID to its
   prerequisite task IDs (empty list when independent); validate there are no cycles.
2. Run `.specify/extensions/workflow/scripts/task_issues.py --help`, then its dry run with the
   explicit feature and issue, and inspect the exact target changes.
3. Apply within the user's issue-work authorization. The adapter keys issues by repository,
   parent issue, feature and task ID and verifies native GitHub sub-issue links.
4. Never also run the core's old MCP creation loop or Project's task creator. A missing adapter
   is a blocker.

Receipt: exact `parent_issue` and `native_links_verified: true`, with the mapping and the
adapter's result and journal as evidence.

## Phase-lazy

With `issue_sync.taskstoissues: phase-lazy`, publish only the first phase now: add `--phase
"<first phase heading>"` to the dry run and apply. The receipt also needs `lazy: true`. Later
phases are published at each phase start during Execute, and Ready requires every task mapped.

Task deduplication identity and GitHub rules:
`references/dispatcher-operations.md#interruption-and-github-behavior`.
