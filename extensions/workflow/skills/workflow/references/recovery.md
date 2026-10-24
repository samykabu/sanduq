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

## Accepted Scope after an attribute change

For the booking application's refund issue, preview without taking locks or writing files:

```bash
python .specify/extensions/workflow/scripts/workflow.py revalidate-upstream --feature specs/412-refund-approval --through scope --plan
```

Keep the output outside the consumer when checking a live project. The plan binds the exact
checkpoint, Git history, index, attributes, policy, provider, decisions and proof bytes. It
separates identical bytes with a changed fingerprint interpretation from real context edits.
It also reports later receipt drift. It never runs product checks or refreshes those receipts.

Read every proposed path and compare its historical and current evidence. An unchanged-byte
transition needs the original accepted checkpoint in reachable Git history and exact old
bytes from Git or an already accepted, validated evidence snapshot. The original approval
must be in the accepted binding or an accepted gate proof. Missing history blocks recovery.
Equal parsed JSON or a matching normalized hash alone cannot establish unchanged bytes.
Recorded `parent_children` lists must still match exactly. Older native leaf approvals that
omitted the list retain their original parent, complete approval, live leaf membership and exact
approved child count; they cannot prove every historical sibling ID. Recovery validates recorded
gate proofs and never fills the missing list from an unbound publication or today's provider.

Write an assessment using `schemas/scope-revalidation-v1.schema.json`. For example, after
reviewing the empty decision ledger and both Scope proofs for the refund feature:

```json
{
  "schema": "sanduq.scope-revalidation.v1",
  "plan_id": "<exact plan_id from this preview>",
  "actor": "<person who assessed the evidence>",
  "reason": "The byte guard changed interpretation; refund approval remains unchanged.",
  "schema_transition": {"from": 1, "to": 2, "drops_repo_path": true},
  "stages": {
    "scope": {
      "summary": "The approved refund requirements and decisions remain unchanged.",
      "evidence": ["specs/412-refund-approval/evidence/scope/recovery.json"],
      "assessments": [
        {
          "path": "specs/412-refund-approval/workflow/decisions.json",
          "classification": "unchanged-bytes-context-transition",
          "conclusion": "scope-unchanged",
          "rationale": "The historical and current raw ledger bytes are identical; no decisions were added."
        }
      ]
    }
  }
}
```

Use the preview's actual `schema_transition`, and add one finding for **every** proposed path,
including both proofs in this example. Do not submit hashes. In the new `recovery.json` evidence,
record exactly `schema`, `plan_id`, `scope_unchanged: true` and `findings`; `findings` contains
the same assessed entries. The evidence must describe your actual comparison. For a real
project-memory or deviation edit, use `context-edit` and explain how its exact before/after
evidence preserves the approved Scope. All other substantive edits block this route.

```bash
python .specify/extensions/workflow/scripts/workflow.py revalidate-upstream --feature specs/412-refund-approval --through scope --receipt assessment.json --apply
```

Apply rereads provider and local state under writer, delegation and decision locks. A changed
plan or evidence is refused. It retains the complete previous Scope receipt and assessment
in `scope_revalidations`; every other receipt and original proof stays unchanged. A version-1
checkpoint becomes version 2 only through the explicitly assessed canonical save. Resolve
package or policy migrations separately. A lifecycle append failure reports committed recovery
with a pending outbox; it does not undo the checkpoint.

Later Verify, Review, Ready, QA, manual and PR gates still require their own current evidence.
Changed approval, prompt, requirements, effort, prerequisites, parent/child membership or live
decisions cannot be waived. Ordinary amendment eligibility and claim ownership are unchanged.

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
