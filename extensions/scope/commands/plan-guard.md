---
description: "Require clarification readiness before technical planning."
---

# Clarification readiness gate

Run `python .specify/extensions/scope/scripts/clarification.py plan-gate` using the
active bound feature, or pass the explicit source issue number. Any nonzero exit
stops Plan and its remaining hooks. Only Ready issues can enter planning. If answers
are pending, direct the user to the question comments and the required Feature
Specification handoff. Do not advance status or make up answers to pass this gate.
