# Receipt rules and recovery recipes

The stage loop's step 5 in full: how to record an honest receipt, declare input
roles, amend evidence, and recover a stale receipt after source drift (G6).

## Recording the receipt

Record an honest receipt JSON: `stage`, `outcome: passed`, `summary`, `inputs` (project-relative
consulted input paths), and `evidence` (existing project-relative proof files). Do not include
checkpoint files in input manifests. Pin test/review outputs; do not call a generated report
actual test execution. The runtime additionally fingerprints required spec/plan/task
artifacts and inventories source files for Verify, Review and Ready, including new
and deleted files. This cannot establish that a claimed test actually ran; preserve
command output and reviewer evidence. Add the stage-specific fields in this stage's
own reference. Failed/skipped/pending work
cannot receive a passed receipt. Include all relevant inputs, not just the evidence file.
A pending or conflicted issue decision blocks a passed receipt. Reread the
issue decision ledger before completion and include it in the stage inputs.
Declare input roles in the optional `input_roles` map, keyed by a path listed in
`inputs`: `{"role": "dependency"}` when the stage's conclusion rests on the file's
content, or `{"role": "consulted", "because": "<one line>"}` when it was read for
context only (for example, "implementation target of T012; the plan does not
depend on its current content"). A file Scope or Plan reads is consulted only
when the conclusion does not depend on its current content; when in doubt it
is a dependency. Evidence and the stage's required spec/plan/task artifacts are
always dependencies. Every input keeps its hash either way. A changed dependency
stales the receipt and fails a later stage with
`UPSTREAM_INPUT_CHANGED_DURING_STAGE`; a changed consulted input is reported by
`next` as `advisory_drift` and must be read before relying on it. A receipt
without `input_roles` is read as all-dependency. When the policy sets
`receipts.require_input_roles: true`, every input outside `specs/<feature>/`
and `.specify/memory/` needs a declared role or `complete` refuses the receipt.
If only a completed stage's evidence file changed afterwards (a typo, a
clarification), do not re-record the stage and do not copy hashes forward: run
`workflow.py amend --feature ... --stage <stage> --evidence <path> --reason
"<why>" --assessment unchanged|changed` once per receipt that lists the file as
evidence. `unchanged` asserts the stage's conclusion and claimed checks still
hold; `changed` marks Verify, Review and Ready (from the amended stage on) stale
so they are re-recorded. Only a path listed as that receipt's evidence can be
amended; the gate lists every amendment for the reviewer.

## Recovery after source drift (G6)

When `next` returns `inputs-or-evidence-changed`
or the gate fails with `STALE_RECEIPT`, run the `recovery` commands it prints, in order;
never copy hashes forward and never revalidate on a note. The recipes are:
- Changed evidence of a completed stage: the `amend` command above.
- Verify stale after source drift (`ci.gate.verification_check` set): push HEAD, wait
  for that check to pass on it, then `workflow.py revalidate --feature ... --stage verify
  --check-run <run id>`. It needs the affected-lane hook, a clean source tree and
  current earlier stages. If it reports a `lane_gap`, Verify stays stale: run the check
  on a commit with the same source key covering those lanes (or re-record Verify), then
  revalidate again. A rejected run (other source key, failed or cancelled check, missing
  or mismatched plan artifact) changes nothing. Never edit `ci_evidence` by hand: an
  incomplete record is not current, and the gate re-reads every run it accepts Verify
  through (`CI_EVIDENCE_UNREADABLE` / `CI_EVIDENCE_REJECTED`: re-run the check and
  revalidate, or re-record Verify).
- Review stale after source drift: review the source diff `<review head>..HEAD` for real,
  record it in `specs/<feature>/evidence/<file>.md` with the lines
  `Diff reviewed: <review head>..<HEAD>`, `Diff sha256: <hash>` (the SHA-256 of the exact
  bytes of the `git -c core.quotePath=true diff-tree -r -p --binary --no-renames ...` command
  the recovery prints, piped to `sha256sum` in a POSIX shell), `Reviewer: <name>`, the
  findings, and `Blocking findings: 0`, then
  `workflow.py revalidate --feature ... --stage review --diff-reviewed <file>`. A stale or
  wrong hash, or a missing reviewer, is refused; never reuse a note for another range. A
  review receipt without `head` (pre-1.6.0) is re-recorded.
- Ready, once Verify and Review are current: `workflow.py revalidate --feature ...
  --stage ready` (it re-runs task, mapping and documentation checks).
- Then commit the checkpoint and evidence together; the source key does not move.
- Otherwise (an input changed, a `changed` amendment, a legacy receipt, no configured
  route): re-record with `claim`, the stage, and `complete` (after `recover` if a
  claim is active).

With `ci.gate.affected_command` set, drift the hook maps to no lane (Markdown,
committed artifacts) keeps Verify, Review and Ready current; a failing hook fails closed.
