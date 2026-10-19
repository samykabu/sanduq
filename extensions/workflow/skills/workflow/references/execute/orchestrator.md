# Execute: dedicated orchestration agent

This part applies when lean execution is off.

## Execution ownership

The dispatcher owns the stage claim and lifecycle transitions. A dedicated orchestration agent
owns task assignments, integration and phase commits and pushes; it has no reporting duty.
Workers implement the assigned tasks and return evidence. Never silently replace the required
agents with work in the parent. Continue all authorized phases automatically; post-merge
verification is in `references/stage-pr.md`.

## Start and resume

Create a dedicated orchestration agent for scheduling and integration before
implementation starts. It is not a reporting agent. Give it the
bound feature, repository, branch, issue, current claim identity, task list,
approved decisions and project instructions. Record its actual host agent ID in
the feature handoff. On resume, inspect that handle and reuse it while it is live.
An observation timeout alone does not prove an agent has stopped. Recover a
terminal or missing agent from the handoff before assigning new work.

Use the host's real agent spawn, message and status tools; do not invent tool names or
assume a child can spawn workers. If nested spawning
is unavailable, the dispatcher creates workers on the orchestration agent's
behalf and forwards results. If the only duty left for that layer would be
reporting, drop it and let the dispatcher assign workers directly. Where this fallback applies, the dispatcher
spawns the batch with blocking calls and forwards each structured result once,
unchanged, the same as the orchestration agent would; it does not relay,
re-summarise or add commentary. The orchestration agent still controls assignments.
Reserve capacity for the dispatcher and, while it does real coordination work, the
orchestration agent; never reserve any for reporting. Release idle workers when needed.
If the host has no usable subagent support or cannot fit a worker, record that
specific blocker and request a supported host/configuration. Do not report a
simulated role or serial parent execution as agent delegation.
