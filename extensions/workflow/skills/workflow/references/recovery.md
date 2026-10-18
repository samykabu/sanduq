# Recovery after source drift

When `next` returns `inputs-or-evidence-changed` or the gate fails with `STALE_RECEIPT`, run
the `recovery` commands it prints, in order. Never copy hashes forward and never revalidate on
a note alone.

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

## Amending evidence

If only a completed stage's evidence file changed (a typo, a clarification), do not re-record
the stage or copy hashes forward: run `workflow.py amend --feature ... --stage <stage>
--evidence <path> --reason "<why>" --assessment unchanged|changed` once per receipt listing the
file as evidence. `unchanged` asserts the conclusion and claimed checks still hold; `changed`
stales Verify, Review and Ready from that stage on. The gate lists every amendment.
