# gate-explain

Not a claimed stage; a diagnostic entry point (B13, G6) over the same check
`ci_gate.py` runs, for a human or dispatcher who hit a gate failure and needs
the exact recovery recipe instead of re-deriving it from `receipt-rules.md`.

Run:

```text
python .specify/extensions/workflow/scripts/gate_explain.py --root <repo> \
  --feature specs/<feature> --base-ref origin/<target>
```

On a passing gate it reports `{"ok": true, "status": "passed"}`. On a
`STALE_RECEIPT` failure it reports the failing stage, the exact
`recovery_recipe` the gate itself would print, and
`evidence_only_eligible`: true only when every drifted path of that stage is
already listed as that receipt's own `evidence` *and* is not also a declared
input or one of the stage's required core artifacts (review round 1, finding
1: a path can be listed as both `evidence` and a real dependency the stage's
conclusion rests on -- amending it under `unchanged` would silently launder a
semantic change, not just fix a typo in a proof-of-work write-up). This
mirrors, not re-derives, the gate's own `explicit-drift` classification
(`workflow.receipt_status`); it invents no new category of "safe" drift.

## Evidence-only auto-fix

Add `--auto-fix --reason "<why>" --assessment unchanged|changed` (both
required, no default -- finding 2) only when `evidence_only_eligible` is
true. It runs `Run.amend` -- the same checked re-hash `receipt-rules.md` has
a human run by hand -- for each eligible path, after re-validating every one
of them against one loaded state snapshot first, so a mid-list failure never
leaves a partial fix applied (finding 11: all or nothing). Nothing is
re-stamped without a check (standing rule 4): `amend` recomputes the evidence
file's real byte hash before recording it, and `--reason` is never fabricated
by this script; the caller states, in their own words, why the assessment
holds. `--assessment changed` is honest too (it marks Verify/Review/Ready
stale from that stage on rather than pretending nothing moved); it is never
chosen automatically. `--auto-fix` refuses outright inside a delegated
worker or orchestrator process (`SANDUQ_DELEGATED_RUN`/`SANDUQ_DELEGATED_ROLE`,
finding 3, matching `Run.amend`'s own guard): this is a dispatcher-level
decision, never a worker's.

For any other failure code (`RECEIPT_MISSING`, `CLARIFICATION_UNRESOLVED`,
`DECISION_LIVE_UNRESOLVED`, an `explicit-drift` on a real dependency, a lane
gap, a changed amendment, ...) `--auto-fix` refuses with
`GATE_EXPLAIN_NOT_EVIDENCE_ONLY`; read the printed `recovery` list and follow
`receipt-rules.md`'s recipe by hand instead.
