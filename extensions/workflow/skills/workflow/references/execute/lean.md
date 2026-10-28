# Execute: lean coordinator

This part applies when lean execution is on (`lean_execution.enabled: true`). Native or external
work follows the [routing rule](../delegation.md#routing-rule).

The existing lifecycle coordinator owns Execute and the following verification, documentation
and publication work: all assignments, integration, reporting calls and authorized Git
operations. Do not create the additional orchestration agent; wherever this protocol names the
orchestration agent, the coordinator does that work. Assign bounded workers directly, each with
a concrete artifact and acceptance result; the coordinator keeps claims, integration and
receipts. Dispatch only concrete deliverables with acceptance criteria (with delegation:
`--deliverable`, `--correction-plan`, then `--diagnosis`, as in
[delegation.md](../delegation.md#lean-execution-default-for-lite-and-standard)). Finish all coding and testing before
the independent coding review; `[artifact-analysis]` marks artifact analysis, which may run
earlier.
