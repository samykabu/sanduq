# Utilities: status, doctor, reconcile

Read-only or repair entry points, not claimed stages. The stage loop and `continue` are in
[dispatcher-operations.md](dispatcher-operations.md).

## status

Run `status --feature ...` and summarize receipts, active claim, blockers, drift, the profile
and skipped stages. When Progress is installed, `progress_status` carries the progress report's one
line (`progress.py status`); show it as is, without running it again. Those facts are the status;
a model-written narrative on top is optional explanation, never required, and no agent is
started to produce it ([reporting.md](reporting.md)).

## doctor

`doctor` always runs fresh, including the skill inventory and `git ls-files --eol`, and refreshes
`.specify/workflow/runtime/doctor-cache.json`. `claim` reuses the last green project doctor
result while the dependency digest, policy digest and registry and config files are unchanged
and it is under 600 seconds old, so do not run doctor before every claim. Report every missing
command or dependency; a skipped check is not a pass. Settle legacy Bridge ownership before
choosing another executor.

## reconcile

Run `scripts/reconcile.py --root <repo>`, inspect its diff, then `--apply` to materialize
policy. Install the package's managed preset through Spec Kit's public CLI.
