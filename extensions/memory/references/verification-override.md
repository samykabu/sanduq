# Explicit manual verification override

Read only when the owner explicitly asks for `--skip-verification "<reason>"` on exact, manually
selected feature folders. Never infer the override from a failed check or unavailable
infrastructure. The reason is recorded permanently in Git, so write a concise factual reason
suitable for the repository's audience (`prepare` rejects an empty, multi-line or over-long one, and
rejects the override in automatic or `--all-completed` mode).

Skip the verify step and its `--check` options; run
`A prepare --spec <path> --skip-verification "<reason>"` (repeat `--spec` for the selection).
Enumerated `--related` files remain explicit unverified checkpoint inputs; never describe them as
verified. The helper still requires the configured target branch and a completed tasks/completion
boundary unless the owner separately retires unfinished work with `--retire-reason`; do not mark
unfinished tasks complete to use this override.

What changes: fresh verification evidence and the external post-deletion checks are skipped.
Checkpointing, source and provenance validation, independent critique, exact-byte fixture
migrations, consumer and reference repairs, the scoped final commit and recovery stay required.
Inspect the skipped status and reason in the journal. Review runtime consumer repairs line by line,
because no check will execute them. Keep meaningful unresolved limits and follow-ups in memory; do
not add an archive log or claim unrun verification passed.

The reviewer adds `"verification_override": "<exact journal reason>"` to `review.json`. `passed`
means the critique passed; verification remains `skipped`. The checkpoint and final commit
messages, the committed archive index and the new ledger header carry the same reason.

An existing transaction keeps its verification mode: abandon an unpublished proposal or roll back a
published one (see `.specify/extensions/memory/references/recovery.md`), then prepare and review a new override transaction.
