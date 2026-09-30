# Stage reference: analyze

Loaded when `claim` returns `stage: analyze`.

## Required work and evidence

Resolve blocking cross-artifact findings, rerunning affected stages when inputs change.

## Managed overlay (`speckit.analyze`)

When analysis finds a material ambiguity, post a stable decision question on the
bound GitHub issue through `decisions.py` and pause for team input. An accepted
answer must be applied by the owning Specify, Plan, or Tasks stage; Analysis
records the finding and revalidates the resulting artifacts. Do not resolve a
team decision through a local VS Code question or silently edit upstream work.
