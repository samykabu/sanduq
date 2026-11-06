# Selected verification plan

Select the repository-relative manifest with `lean_execution.verification_plan`.
The project owns its relevance: include every exact source, build input and
fixture that can affect each check, including the check's own script. Commands
are argv arrays executed from the repository root. `environment` lists variable
names to bind; Python, platform, working directory, PATH and the resolved
executable's path/bytes are always recorded. List concrete
files, including untracked inputs; directories, globs and missing files fail.

```json
{
  "schema_version": 1,
  "checks": [{
    "id": "refund-unit",
    "sources": ["src/refund.py", "tests/test_refund.py"],
    "fixtures": ["tests/fixtures/refund.json"],
    "command": ["python", "-m", "unittest", "tests.test_refund", "-q"],
    "environment": ["REFUND_TEST_MODE"],
    "evidence": "specs/42-booking-refund/evidence/refund-unit.json"
  }]
}
```

Use bounded commands:

```text
python .specify/extensions/workflow/scripts/verification_plan.py --root <repo> --plan specs/42-booking-refund/verification-plan.json --timeout 180 run
python .specify/extensions/workflow/scripts/verification_plan.py --root <repo> --plan specs/42-booking-refund/verification-plan.json snapshot
python .specify/extensions/workflow/scripts/verification_plan.py --root <repo> --plan specs/42-booking-refund/verification-plan.json --prior <saved-snapshot-or-verify-receipt.json> select
python .specify/extensions/workflow/scripts/verification_plan.py --root <repo> --plan specs/42-booking-refund/verification-plan.json --check refund-unit --timeout 180 run
```

`run` writes exact-input records with local provenance, exit code, timeout,
bounded output and whether inputs remained unchanged during the command. It
returns failure if any selected check failed. `snapshot` refuses absent, stale,
failed or timed-out evidence. `select` returns affected/reusable check IDs and
reasons against a saved snapshot, including exact evidence bytes. No snapshot
means every check is affected. Changed definitions, sources, fixtures, commands,
environment or evidence require the affected check to run again; deleting a
check also invalidates the prior Verify conclusion.

Verify completion captures `verification_snapshot` itself; a submitted receipt
cannot supply that reserved field. Receipt input/evidence checks still apply.
Never copy receipt hashes to fresh inputs. Revalidation through an actual CI
check still requires passing selected local records before capturing a fresh
snapshot. These records do not certify CI or replace live acceptance. Without
lean selection, existing source-key and affected-lane behavior remains intact.
