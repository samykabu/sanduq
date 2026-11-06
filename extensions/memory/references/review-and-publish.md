# Independent review and publication

Read once `A preflight --run <id>` reports `data.candidate_guards: passed`. For format 2 preflight
materializes the result in a temporary copy (entries, new ledger, regenerated views, taxonomy) and
checks it as a whole; its `data` carries `candidate_guards`, `candidate_sha256`,
`base_memory_root`, `result_memory_root`, `outputs_sha256`, `summary`, `review{status, problems}`
and `paths`. It exits 1 only on mechanical problems and 0 even while the review is missing or
mismatched.

## Review

Have an independent local reviewer inspect the candidate, all input units and evidence,
supersessions, removals and fixture or consumer repairs. The reviewer compares content, not only
JSON validity: coverage and provenance checks cannot prove semantic correctness. Use a separate
read-only agent or delegate when available; if independent review is unavailable, stop before
deletion. The archive workflow authorizes this review. The reviewer never changes repository
files, and you do not claim independence for a synthesis you reviewed in the same agent context.

Write `review.json` beside the candidate only after all findings are resolved:

- both formats: `candidate_sha256` (sha256 of the exact candidate bytes), nonempty `reviewer` and
  `summary`, `passed: true`, `findings: []`, and `verification_override` when verification was
  skipped;
- format 2: the reviewer copies `candidate_sha256`, `base_memory_root`, `result_memory_root` and
  `outputs_sha256` exactly as preflight reported them; a packeted run adds the `partitions` and
  `integration` approvals from `.specify/extensions/memory/references/large-runs.md`.

Any candidate edit invalidates the review and needs a new critique.

## Publish

Run `A status` and do what `data.next` says until the run reports `done`; `validate` and
`finalize` return their own `next` as well. `validate` reports mechanical validity and the exact
result bindings even while `data.review.status` is `missing`; `data.valid: true` does not approve
publication, only `review.status: passed` does. `finalize` writes the memory outputs (format 2:
changed and new entry files, deleted removed entries, the new
`provenance/<seq>-<checkpoint8>-<run8>.jsonl`, regenerated views, taxonomy) and fixture repairs,
deletes every selected folder, runs the required checks (or records the explicit manual override)
and makes the scoped final commit. Under approved automatic policy there is no extra human prompt.
An explicit manual `run` authorizes the selected archive only; do not expand its scope. If
`validate` or `finalize` report that memory changed since prepare, there is no automatic rebase:
abandon and prepare again (`.specify/extensions/memory/references/recovery.md`).
