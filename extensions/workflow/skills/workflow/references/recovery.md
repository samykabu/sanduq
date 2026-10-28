# Recovery after source drift

When `next` returns `inputs-or-evidence-changed` or the gate fails with `STALE_RECEIPT`, run
the `recovery` commands it prints, in order. Never copy hashes forward and never revalidate on
a note alone. A `claim` that would remove the receipts of later stages returns
`status: confirm_invalidation` instead of claiming: `invalidates` lists those receipts,
`invalidation` gives each one's cause (`stale: <reason>` with its changed `paths`, or `current;
removed only because it follows <stage>`), `recovery` and `explain` give the amend route for a
cosmetic change. Stop and show the user the list; re-run `claim` with `--confirm-invalidation` only
when they want that rework. A claim you then `recover` before any work ran gets every removed
receipt back (`retained.restored`); a stale one stays stale.

- Changed evidence of a completed stage: `amend`, below.
- Upstream documents edited after their stages passed (for example a spec fix during Execute):
  with no active claim, `workflow.py revalidate-upstream --feature specs/<f> --through <stage>
  --plan` prints the changed input paths per stale stage. Review each change, write
  `{"stages": {"<stage>": {"summary", "evidence": [], "inputs": []}}}` for every listed stage,
  then run it with `--receipt <file>`: one locked operation re-records them in order with the
  same validation as `complete`. Whitespace-only Markdown changes count as unchanged.
- Verify stale after source drift (`ci.gate.verification_check` set): push HEAD, wait for that
  check to pass on it, then `workflow.py revalidate --feature ... --stage verify --check-run
  <run id>`. It needs the affected-lane hook, a clean source tree and current earlier stages. A
  `lane_gap` keeps Verify stale: run the check on a commit with the same source key covering
  those lanes, or re-record Verify. A rejected run changes nothing. Never edit `ci_evidence` by
  hand; on `CI_EVIDENCE_UNREADABLE` or `CI_EVIDENCE_REJECTED` re-run the check and revalidate,
  or re-record Verify.
- Review stale after source drift: review `<review head>..HEAD` for real and record it in
  `specs/<feature>/evidence/<file>.md` with `Diff reviewed: <review head>..<HEAD>`,
  `Diff sha256: <hash>` (SHA-256 of the exact output of the `git -c core.quotePath=true
  diff-tree -r -p --binary --no-renames ...` command the recovery prints), `Reviewer: <name>`,
  the findings and `Blocking findings: 0`, then `workflow.py revalidate --feature ... --stage
  review --diff-reviewed <file>`. A wrong hash or missing reviewer is refused. A review receipt
  without `head` is re-recorded.
- Ready, once Verify and Review are current: `workflow.py revalidate --feature ... --stage
  ready` (it re-runs task, mapping and documentation checks).
- Then commit the checkpoint and evidence together; the source key does not move.
- Otherwise (a changed input, a `changed` amendment, a legacy receipt, no configured route):
  re-record with `claim`, the stage and `complete` (after `recover` if a claim is active).

With `ci.gate.affected_command` set, drift the hook maps to no lane (Markdown, committed
artifacts) keeps Verify, Review and Ready current; a failing hook fails closed.

## Project Sync state

Receipts fingerprint the configured state file (`stateFile`) as the bound feature's entry
without `status` and timestamps (`sync-binding:v1:<sha256>`). A status-only sync therefore never
stales a receipt or refuses a completion, before or after `complete`. A changed issue, node ID,
item ID or sub-issue mapping, or a missing entry, still does; other features' entries do not
count. This holds for a state file under `.specify/` (the default). A state file elsewhere is
also source for Verify, Review and Ready, so a status write there is source drift.

A receipt recorded before 1.16.0 holds a raw hash of the state file and stays byte-exact, so a
status write stales it. `migrate` converts it; so does `workflow.py sync-amend --feature <f>
--reason <text>`, with no active claim. Both first check the entry's issue against
`scope-source.json` and its sub-issues against `workflow/task-issues.json`, then find the
recorded bytes (working tree, HEAD, or the last 50 commits that touched the file). They refuse
when the binding differs, when the recorded bytes are not found, or when a field other than
`status` or a timestamp changed since; re-record the stage then. The old and new value and the
changed fields go to an `administrative-amendment` lineage entry. No other hash moves. A
Clarify change to the state file keeps such a receipt's hash raw. The recovery a stale receipt prints names
`sync-amend` first when this is the drift.

## Amending evidence

If only a completed stage's evidence file changed (a typo, a clarification), do not re-record
the stage or copy hashes forward: run `workflow.py amend --feature ... --stage <stage>
--evidence <path> --reason "<why>" --assessment unchanged|changed` once per receipt listing the
file as evidence. `unchanged` asserts the conclusion and claimed checks still hold; `changed`
stales Verify, Review and Ready from that stage on. The gate lists every amendment.
