# Stage reference: taskstoissues

Loaded when `claim` returns `stage: taskstoissues`.

## Required work and evidence

Invoke the actual core skill with the Sanduq managed preset. Derive an explicit
task dependency mapping and run `task_issues.py`. Dry-run, inspect, then apply
authorized issue writes. Receipt needs exact `parent_issue` and
`native_links_verified: true`, with the generated mapping/result files.

## Managed overlay (`speckit.taskstoissues`)

This is the actual core Tasks-to-Issues invocation with a managed adapter.
Keep prerequisite and repository validation, but replace the upstream global
T001-title deduplication and issue-creation loop with:
1. Read tasks.md and its dependencies. Write a JSON object mapping each task ID to
   prerequisite task IDs (empty list for independent tasks); validate no cycles.
2. Run `.specify/extensions/workflow/scripts/task_issues.py --help`, then its
   dry run with the explicit feature and issue. Inspect the exact target changes.
3. Apply within the user's issue-work authorization. The adapter uses repository,
   parent issue, feature and task ID, and verifies native GitHub sub-issue links.
4. Include its result and journal as evidence. Never also execute the core's old
   MCP creation loop or Project's task creator. A missing adapter is a blocker.
