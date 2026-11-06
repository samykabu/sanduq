# gate-explain

A diagnostic entry point, not a claimed stage, over the same check `ci_gate.py` runs.

```text
python .specify/extensions/workflow/scripts/gate_explain.py --root <repo> \
  --feature specs/<feature> --base-ref origin/<target>
```

A passing gate reports `{"ok": true, "status": "passed"}`. A `STALE_RECEIPT` failure reports
the stage, the exact `recovery_recipe`, and `evidence_only_eligible`: true only when every
drifted path of that stage is listed as that receipt's own `evidence` and is neither a declared
input nor a required core artifact.

Only when `evidence_only_eligible` is true, add `--auto-fix --reason "<why>" --assessment
unchanged|changed` (both required). It runs `amend` for every eligible path, all or nothing,
recomputing each file's hash. State the reason in your own words; `changed` stales Verify,
Review and Ready from that stage on and is never chosen automatically. `--auto-fix` refuses
inside a delegated worker or orchestrator, and for any other failure (`RECEIPT_MISSING`,
`CLARIFICATION_UNRESOLVED`, `DECISION_LIVE_UNRESOLVED`, drift on a real dependency, a lane gap,
a changed amendment) with `GATE_EXPLAIN_NOT_EVIDENCE_ONLY`: follow the printed `recovery` list
([recovery.md](recovery.md)) instead.
