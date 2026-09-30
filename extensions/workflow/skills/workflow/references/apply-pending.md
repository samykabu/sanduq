# apply-pending

Not a claimed stage; a utility entry point (B13, F15) that formalises the
`workflow/pending-artifact-updates.md` convention the retrospective found
working ad hoc: a worker proposes contract/data-model/research wording
instead of editing the shared file mid-Execute (which would cascade a
Plan/Analyze receipt every time), and this step applies every still-`pending`
proposal once, at the end of Execute and again at the end of Review.

Entry format, appended by workers, one block per proposal:

```text
## <repo-relative target path>#<exact heading text>
Source: T012 (why)
Status: pending
```markdown
<the new body of that heading, verbatim>
```
```

Run a dry run first, then apply:

```text
python .specify/extensions/workflow/scripts/apply_pending.py --root <repo> --feature specs/<feature>
python .specify/extensions/workflow/scripts/apply_pending.py --root <repo> --feature specs/<feature> --apply
```

Before running `--apply`, the calling agent -- never this script -- checks
each pending entry's proposed wording against the actual shipped code (F15's
"verifying each item against code"); the script only performs the mechanical
half. It locates the named heading in the target file, replaces its body up
to the next heading of the same or shallower level, and marks the entry
`applied` (with `Applied:`/`Actor:`) or `rejected` (`ANCHOR_NOT_FOUND` or
`TARGET_FILE_MISSING`, with a `Reason:`); an already-decided entry is left
untouched, so re-running is safe.

When `--apply` touches a path that is a dependency of an already-passed
receipt (Plan and Analyze commonly fingerprint contracts, data-model and
research explicitly), the result's `stale` list names each stage that is no
longer current, with the exact `recovery_recipe` -- the same structured
recipe `gate-explain` prints. Run it (typically a re-record through
`claim`/`complete`, since a dependency, not evidence, changed); this script
never re-validates a stage itself.
