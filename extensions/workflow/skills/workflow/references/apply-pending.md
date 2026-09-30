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
`applied` (with `Applied:`/`Actor:`) or `rejected` (`ANCHOR_NOT_FOUND`,
`TARGET_FILE_MISSING`, `PENDING_TARGET_ABSOLUTE_REFUSED` or
`PENDING_TARGET_NOT_ALLOWED`, with a `Reason:`); an already-decided entry is
left untouched, so re-running is safe.

Every target is confined to `<feature>/contracts/**`, `<feature>/data-model.md`
or `<feature>/research.md` (review round 1, finding 4): an absolute path,
`..`, or a symlink anywhere on the way that would resolve outside those
locations is rejected per-entry, exactly like the checks above, never
silently normalised or followed. The pending file itself is contained the
same way, as a hard failure rather than a per-entry rejection.

`--apply` refuses outright inside a delegated worker or orchestrator process
(`SANDUQ_DELEGATED_RUN`/`SANDUQ_DELEGATED_ROLE`, finding 3, matching
`Run.amend`'s own guard) and while a claim is active for the feature
(`APPLY_PENDING_ACTIVE_CLAIM_MUST_BE_RESOLVED`) -- this is a dispatcher-level
decision, never a worker's, made on a stable checkpoint.

When `--apply` touches a path that is a dependency of an already-passed
receipt (Plan and Analyze commonly fingerprint contracts, data-model and
research explicitly), the result's `stale` list names each stage that is no
longer current, with the exact `recovery_recipe` -- the same structured
recipe `gate-explain` prints. Run it (typically a re-record through
`claim`/`complete`, since a dependency, not evidence, changed); this script
never re-validates a stage itself. When a touched path is fingerprinted but
the staleness check itself fails, the result reports `stale: null` with a
`stale_error` message, never silently folding that failure into an empty
`[]` that would look identical to "confirmed nothing is stale" (finding 5).

## Residual race (time of check to time of use)

The threat model is accident prevention in a local tool, not a hostile local
user, and full directory-handle protection is not practical across
platforms. Within that: every target is validated lexically with no symlink
or junction (`delegation.is_link`, so a Windows junction is caught on Python
before 3.12 too) anywhere on its path; that whole chain is re-validated
immediately before the temp file is created and again immediately before
`os.replace`; the old file is moved aside, and after the replace the written
file's real path must still be the one validated. If it is not, the moved
aside content is put back and `PENDING_WRITE_LANDED_ELSEWHERE` is reported.

What remains: a parent swapped for a link in the few instructions between
the last re-validation and the backup move is caught only by that final
check, and one swapped between the backup move and the replace lands the new
text in the wrong file with nothing to restore (recover it from git, since
every allowed target is a tracked repository file). Do not run `--apply`
while something else is rewriting the feature directory.
