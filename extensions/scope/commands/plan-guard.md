---
description: "Require clarification readiness before technical planning."
---

# Clarification readiness gate

Run `python .specify/extensions/scope/scripts/clarification.py plan-gate` using the
active bound feature, or pass the explicit source issue number. Any nonzero exit
stops Plan and its remaining hooks. Ready issues can enter planning. An existing open
feature in progress/review can be revalidated only under the matching managed Plan
claim with a passed, resolved clarification receipt. This does not waive questions.
If answers
are pending, direct the user to the question comments and the required Feature
Specification handoff. Do not advance status or make up answers to pass this gate.
