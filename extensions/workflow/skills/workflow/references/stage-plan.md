# Stage reference: plan

Loaded when `claim` returns `stage: plan`.

## Required work and evidence

Produce current plan/research/contracts from the resolved spec, then automatically
choose one task generator.

## Managed overlay (`speckit.plan`)

For a `mode: revalidate` claim with an existing plan, update only what changed.
Preserve established decisions and task history, and do not blindly copy a new plan
template over reviewed content. Keep the clarification gate: a managed claim can
recheck an open feature already in progress only with resolved clarification evidence.

For a new material choice during planning, use the bound issue decision adapter
and pause for an authorized GitHub answer. Apply the answer to the plan and
record its evidence before returning a passed Plan receipt.
