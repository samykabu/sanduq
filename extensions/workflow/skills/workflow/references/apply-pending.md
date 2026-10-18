# apply-pending

A utility entry point, not a claimed stage. Workers propose contract, data-model or research
wording in `workflow/pending-artifact-updates.md` instead of editing the shared file mid-Execute
(which would stale Plan and Analyze each time); this step applies every still-`pending`
proposal once at the end of Execute and again at the end of Review.

Entry format, appended by workers, one block per proposal:

```text
## <repo-relative target path>#<exact heading text>
Source: T012 (why)
Status: pending
```markdown
<the new body of that heading, verbatim>
```
```

Dry run first, then apply:

```text
python .specify/extensions/workflow/scripts/apply_pending.py --root <repo> --feature specs/<feature>
python .specify/extensions/workflow/scripts/apply_pending.py --root <repo> --feature specs/<feature> --apply
```

Before `--apply`, check each pending entry's wording against the shipped code yourself; the
script does only the mechanical half. It replaces the named heading's body up to the next heading
of the same or shallower level and marks the entry `applied` or `rejected` (`ANCHOR_NOT_FOUND`,
`TARGET_FILE_MISSING`, `PENDING_TARGET_ABSOLUTE_REFUSED`, `PENDING_TARGET_NOT_ALLOWED`, with a
`Reason:`). Decided entries are left alone, so reruns are safe. Targets are confined to
`<feature>/contracts/**`, `<feature>/data-model.md` and `<feature>/research.md`; absolute
paths, `..` and links are rejected per entry. `--apply` refuses inside a delegated worker or
orchestrator and while a claim is active (`APPLY_PENDING_ACTIVE_CLAIM_MUST_BE_RESOLVED`).

When `--apply` touches a dependency of a passed receipt, the result's `stale` list names each
stage with its `recovery_recipe`; run it (usually a re-record through `claim` and `complete`).
`stale: null` with `stale_error` means the staleness check itself failed, not that nothing is
stale. Do not run `--apply` while something else rewrites the feature directory; a write that
lands elsewhere is restored and reported as `PENDING_WRITE_LANDED_ELSEWHERE`.
