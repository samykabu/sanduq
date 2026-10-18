# Legacy execution guard

Shared body for the `speckit-superpowers-bridge` `execute`, `guard` and `handoff` overlays.

If `.specify/workflow.yml` exists, the workflow dispatcher owns lifecycle transitions. Run
workflow doctor first. Inspect an executing or blocked legacy handoff and reconcile it from
actual evidence; never mark it complete to pass a guard. Do not start a second executor or
write another legacy handoff. For execute, invoke `speckit.workflow.continue` for the
explicitly bound feature and return. For guard and handoff, report the managed owner and return
without changing legacy state. Each overlay carries its own STOP before the upstream legacy
instructions; unmanaged projects keep those instructions unchanged.
