# Workflow state files

This page explains where Workflow keeps policy and feature state, how a checkpoint identifies its repository, how to relocate a repository legitimately, and the receipt contract each completed stage records. The JSON shapes are summarised in [Workflow schemas](schemas.md); daily recovery steps are in the [operations guide](operations.md).

Back to the [Workflow guide](../../extensions/workflow/README.md).

## State and recovery

Policy lives in `.specify/workflow.yml`. Feature state lives under
`specs/<feature>/workflow/`. Claims prevent concurrent stage ownership. Only an
explicit Specify claim can bind a new branch after verifying scope-source.json.
Use `recover` with the recorded token after inspecting possible remote writes;
use `migrate` after reviewing a dependency upgrade. Both preserve an audit trail.
A migration backs up the checkpoint, preserves still-current historical evidence and invalidates changed command selections. Use `--invalidate-from <stage>` when an upgrade changes a stage contract.
`migrate --preview` writes nothing and returns the exact `invalidated` and
`preserved_as_historical` lists the migration would record, with any blockers;
the applying `migrate` returns the saved `migrations[]` entry. Both load the
checkpoint through the bound-branch check, so run them on the feature's branch.

## Checkpoint identity and relocating a repository (1.8.0)

A checkpoint no longer identifies its repository by the absolute path it was
started from (that path was the checkpoint-identity design bug: every clone,
worktree, second machine, delegated worker or CI runner other than the one
that ran `start` failed `CHECKPOINT_IDENTITY_MISMATCH`, with no supported
fix). It now records a portable `repo_identity`: the normalised `origin`
remote URL when one is configured, and/or the repository's root commit SHA
(`git rev-list --max-parents=0 HEAD`) when it is not. The remote is
authoritative whenever both the checkpoint and the current repository have
one, so a shallow CI checkout of the same origin (whose visible root-commit
history is truncated at the shallow boundary, not the true root) still
matches — unless neither clone is shallow, in which case the root commit
must also match even though the remote does, catching a remote that was
copied into an unrelated clone. The root commit is used on its own
only when neither side has a remote.

`Run.load()` also requires the checkpoint's bound issue to name this
repository's own GitHub remote — the same binding `start` and the scope
extension's `bound_claim` already require, resolved from the remote
(any scheme, an embedded token, with or without `.git`) the same way the
portable identity is, and compared case-insensitively (GitHub repository
names are not case sensitive). Without a GitHub remote to check that
against at all, the checkpoint is refused and pointed at `relocate` rather
than trusted: a repository with no remote configured cannot load an
existing checkpoint, though `workflow.py`'s lower-level identity primitives
still support one for other purposes.

A checkpoint from before 1.8.0 recorded only `repo_path` (never read or
compared by 1.8.0+, but still written by `start`, the legacy-upgrade path
and `relocate` so a pre-1.8.0 reader does not `KeyError`; it will be removed
once no supported release still needs it) and is accepted once both checks
above pass *and* it records a full-hex commit id (its `head`, or a receipt's
`head`) that is reachable from this repository's HEAD — the one verifiable
history signal such a checkpoint carries, since origin is only local Git
config. Without one (recreated or rewritten history) it is refused, naming
`relocate --allow-history-change`. It is then upgraded to `repo_identity` on
its next write. A checkpoint
copied from a genuinely different repository is still refused, whether
legacy or new: this is the security property the design protects.

Moving a repository legitimately — a renamed remote or a migrated GitHub
org (both keep the same issue numbers), or a fork (which does not: its
issue numbering is independent of what it forked from) — changes that
identity and is refused the same way, since it is indistinguishable from a
checkpoint that does not belong here without a human saying so. Run:

```
workflow.py relocate --feature specs/<feature> --preview --reason "<why>"
workflow.py relocate --feature specs/<feature> --reason "<why>"
```

The preview reports the old and new identity, the old and new GitHub
repository, and the current branch binding, without changing anything; the
applying call rebinds the checkpoint and appends a `relocations[]` entry
(`actor`, `at`, `reason`, `old_identity`, `new_identity`, and — only when the
GitHub repository itself changed — `repository_renamed`, `old_repository`,
`new_repository`, `new_issue`). No receipt is touched and no stage is
invalidated — relocate never revisits what evidence means. A branch
mismatch is refused unless `--allow-branch-rebind` is also passed; a
checkpoint whose bound issue names a different GitHub repository than this
one now resolves to is refused unless `--allow-repository-rename` is also
passed — this is the check that stops `relocate` itself from being used to
launder a foreign checkpoint into an unrelated repository, and either
flag's effect is logged in the same entry regardless. A checkpoint whose
recorded root history is not this repository's (the root commit is neither
equal nor reachable on a non-shallow clone, or a legacy checkpoint records
no reachable commit) is also blocked unless `--allow-history-change` is
passed, and `history_changed` is recorded in the entry. Relocate also needs
a resolved GitHub remote to apply (otherwise `load` would refuse the result),
and `--issue`/`--keep-issue-number` are refused with
`RELOCATE_ISSUE_NOT_APPLICABLE` when the repository did not change.

A repository change never rebinds the issue automatically: pass
`--keep-issue-number` to assume the number carries over (a GitHub rename or
transfer only — never a fork) or `--issue <owner/repo#n>` (which must name
the repository this one now resolves to) to bind the exact new issue
instead; passing neither leaves the repository change blocked, and passing
both is refused. `scope-source.json` is rebound together with
the checkpoint (restored to its original bytes if the checkpoint write fails), so a later `start` for the same issue does not fail
`FEATURE_BINDING_MISMATCH` against a source file still naming the old
repository. Relocate is refused inside any delegated worker or
orchestrator context (`DELEGATION_WORKER_CONTEXT`) and while a claim is
active; it reaches the checkpoint directly, bypassing the identity and
branch checks `load` enforces everywhere else, because that gate is exactly
what it exists to get past, and every decision it makes is recomputed from a
fresh read taken under the per-feature lock rather than trusted from before
it.

**Threat model.** This identity check defends against an *accidental*
cross-repository mix-up: the same feature directory name reused in an
unrelated project, a checkpoint file copied by habit instead of by intent, a
CI runner that resolved the wrong checkout. It is not a defence against an
*adversarial* process running inside this repository's own working tree: a
remote URL, a root commit, and the branch a checkpoint claims to be on are
all read from local Git state that a delegated worker (or anything else with
filesystem access here) could edit before this runtime ever reads it, the
same way it could edit `.git/config` directly. Nothing in this design is
meant to resist that; a process already trusted to run commands in this
working tree is already trusted with everything in it. What actually
protects the integrity of recorded work is the receipt contract itself: each
stage's evidence is bound by byte-exact SHA-256 fingerprints
(`fingerprints`, `source_fingerprints`), checked again on every later load,
independent of which repository or machine is asking.
Likewise, merging a foreign history into HEAD in a clone whose `origin` was
copied from the recorded one is accepted (the recorded root commit is then
still an ancestor of HEAD); that is by design, since the merge is a
deliberate act inside the working tree, not an accidental mix-up.

## Receipt contract (1.6.0)

Receipts stay backward-compatible: `inputs` is still a list of paths, and every
new field is optional (`input_roles`, `amendments`, `head`, `source_key`,
`ci_evidence`, `diff_reviewed`; see `schemas/receipt-v1.schema.json`). Reading a
1.3.0-1.5.x checkpoint needs no migration; continuing it after the upgrade needs
the reviewed `migrate` above, which invalidates nothing when no semantic policy
changed.

- **Input roles.** `input_roles: {"<path>": {"role": "dependency" | "consulted",
  "because": "<text>"}}` declares why each input is listed. Only dependencies
  decide whether a receipt is current and whether a later stage fails with
  `UPSTREAM_INPUT_CHANGED_DURING_STAGE`. A consulted input needs a `because`,
  keeps its recorded hash (it is never re-stamped) and, when it changes, is
  reported by `next` as `advisory_drift`. Evidence and a stage's required
  artifacts cannot be consulted. A receipt without roles is read as
  all-dependency, exactly as before. The policy key
  `receipts.require_input_roles` (default `false`) makes `complete` refuse an
  undeclared role for any input outside `specs/<feature>/` and
  `.specify/memory/`. Changing it is a policy change that invalidates no
  completed receipt; run `migrate` once to record the new policy digest.
- **Assessed amendments.** `workflow.py amend --feature specs/<feature> --stage
  <stage> --evidence <path> --reason "<why>" --assessment unchanged|changed`
  re-hashes that one evidence entry of that receipt and appends
  `{path, old_hash, new_hash, reason, assessment, actor, at}` to its
  `amendments[]`; every other hash is kept and the checkpoint is backed up.
  `unchanged` keeps the receipt current; `changed` marks Verify, Review and
  Ready (from the amended stage on) stale so they are re-recorded. A path that
  is not listed as that receipt's evidence is refused, as is an active claim.
  `ci_gate.py` accepts amended receipts and lists each amendment in its result.
