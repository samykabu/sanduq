# Recovery, rollback and abandon

The single recovery text for `run`, `session` and `status`. Read when a run is blocked or
interrupted. `A` means `python .specify/extensions/memory/scripts/archive.py`.

- **Interrupted or blocked.** Run `A status`: `data.next` names the command to run and why.
  Inspect the journal, resolve the reported condition, then rerun `A finalize --run <id>`; it
  resumes an unchanged transaction from its recorded phase. Preserve user edits and the checkpoint.
  Never delete the active journal to make a failure disappear, and never discard an active
  transaction.
- **Stale unpublished proposal.** `A abandon --run <id>` retires that proposal without changing
  files or deleting its checkpoint. Then prepare and independently review a fresh candidate.
- **Permanent failure after publication.** Explicitly, never automatically: `A rollback --run <id>`
  restores the recorded original bytes and the scoped index while the outputs still match their
  recorded original or final hashes, deletes the files the run created (format 2: new entries and its ledger), preserves the
  checkpoint and removes that run's queue entry. An interrupted rollback resumes with the same
  command. The helper refuses a rollback after the final commit or over unexpected user edits:
  preserve those edits and inspect before trying again.
- **Writer locks.** A read-only state check works while a writer is busy. When `pending` reports a
  stale lock, confirm the recorded process has exited before removing that single lock; never
  remove a busy or unknown lock.
- **Guard hook.** With `guard_hooks` on, `git push|stash|reset|clean` and writes under `specs/memory/`
  are refused while a run is active; finish, abandon or roll back the run instead of working
  around it.
- **While a run is active**, `pending --gate` must pass before any new specification, branch or
  broad staging or commit workflow (the feature and auto-commit scripts run that gate themselves).
- **Report** the exact checkpoint and final commit and the archived or skipped features. Assets
  remain recoverable with `git show <checkpoint>:<original-path>`.
