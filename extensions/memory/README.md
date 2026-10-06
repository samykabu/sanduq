# Sanduq Memory

For setup and a consistent worked example, see [Getting started](https://github.com/samykabu/sanduq/blob/main/docs/getting-started.md)
and [memory usage](https://github.com/samykabu/sanduq/blob/main/docs/extensions.md#memory).


Spec Kit extension `memory`, part of Sanduq Spec Kit Extensions. It reconciles verified completed features into project memory under `specs/memory/`: one file per entry, organized by capability, that agents read through a budgeted query. Keep current behavior, decisions, constraints, lessons and useful open follow-ups; replace obsolete rules and remove resolved concerns. Git holds archive history and recoverable artifacts. Read relevant memory during specification and impact analysis; ordinary implementation tasks only check the small pending queue.

## Install and configure

Requires Python 3.11+, Git and Spec Kit 1.x. Install from the Sanduq catalog:

```bash
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
specify extension add memory
```

For development, install from an external clone with `specify extension add --dev /path/to/sanduq/extensions/memory`. Initialize in the target project:

```bash
python .specify/extensions/memory/scripts/install.py --target-branch main
```

Choose the actual merge branch (`main`, `develop`, or another valid branch). Initialization creates `.specify/memory-policy.json` when absent, preserves existing settings, records the installed script guards, generates seven commands for Codex/Claude Code/Copilot, and installs ordered hooks and local session instructions. It does not enable automatic archiving. Run initialization per clone to regenerate ignored agent wrappers.

Configure `product_prefixes` (directories ending in `/`), `product_files`, named `checks`, and `default_checks`. No verification commands are assumed. For example, merge these fields into the generated policy for a Python project:

```json
{
  "checks": {
    "tests": {
      "argv": ["{python}", "-m", "unittest", "discover", "-s", "tests"],
      "covers": ["src/*", "tests/*"],
      "timeout_seconds": 900
    }
  },
  "default_checks": ["tests"]
}
```

Use commands that actually verify implementation and repaired consumers. `covers` declares their scope. Commands execute as argument arrays without a shell. Failed checks or missing infrastructure block archival. Commit the policy, extension and integrations before enabling automatic mode.

Feature-number and transaction guards use context-checked patches to core feature scripts and, when installed, Git-extension feature/auto-commit scripts. Unknown versions or local edits stop initialization before guard writes. Preserve custom scripts and adapt guards explicitly. Reinitialize after Spec Kit/Git-extension upgrades; state checks detect lost guards once an archive registry exists, including disappearance of a recorded script.

## Commands

| Purpose | Codex | Claude Code | Copilot |
| --- | --- | --- | --- |
| Initialize | `$speckit-memory-init` | `/speckit-memory-init` | `/speckit.memory.init` |
| Queue implementation | `$speckit-memory-prepare` | `/speckit-memory-prepare` | `/speckit.memory.prepare` |
| Archive selection | `$speckit-memory-run` | `/speckit-memory-run` | `/speckit.memory.run` |
| Process pending session | `$speckit-memory-session` | `/speckit-memory-session` | `/speckit.memory.session` |
| Review/enable policy | `$speckit-memory-enable` | `/speckit-memory-enable` | `/speckit.memory.enable` |
| Consult memory | `$speckit-memory-impact` | `/speckit-memory-impact` | `/speckit.memory.impact` |
| Inspect recovery | `$speckit-memory-status` | `/speckit-memory-status` | `/speckit.memory.status` |

### Manual use

For example, ask Codex: `$speckit-memory-run specs/412-refund-approval`. The agent verifies actual completion, including downstream QA/review/documentation, executes approved checks, then makes a real scoped checkpoint. It inventories every committed source unit and reconciles a local candidate with current memory. A separate reviewer critiques the exact candidate, source dispositions and fixture repairs before deterministic validation, publication, complete folder deletion, repeated checks and the final scoped commit.

Select several exact folders or `--all-completed` for freshly verified features. Unfinished work requires separate explicit `--retire-reason`; automatic mode never retires it. Unrelated staged/unstaged work is preserved. Enumerate related uncommitted implementation files explicitly for manual checkpointing.

### Automatic use

Run `enable` for the owner's one-time review of the concrete policy and hash. Approval binds project policy, implementation, generated commands, session instructions, archive hooks and script guards. Changes invalidate it. No additional human prompt occurs per archive; independent candidate review still applies.

The implementation hook queues new work on its feature branch. The next local session after merge into the configured target branch verifies actual completion and processes eligible entries. No daemon or remote merge execution is installed. Legacy unqueued features never archive automatically. Re-queue after review fixes. Squash/rebase merges require identical recorded feature inputs and fresh verification; changed/unidentified inputs use explicit manual archival.

## Project memory (format 2)

Memory lives in `specs/memory/` so agents can read it within a token budget:

| Path | Role |
| --- | --- |
| `INDEX.md` | Generated map of domains and catalog pages (≤ 3k tokens) |
| `catalogs/<domain>/NN.md` | Generated `id · kind · title` pages (≤ 1.5k tokens each) |
| `entries/PM-*.md` | Canonical: one entry per file, with a TOML header (id, domain, kind, title, relations, optional `constrains` and `supersedes` links, selectors) and the prose (≤ 1k tokens) |
| `taxonomy.json` | Canonical: governed domain ids and labels |
| `provenance/*.jsonl` | Canonical: append-only ledgers of archived sources and code evidence, one per run |

`specs/project-memory.md` becomes a navigation stub. Budgets come from the policy's `memory_budgets`, counted
with `tokenizer` (`chars/4`).

```bash
python .specify/extensions/memory/scripts/archive.py memory query --path src/orders --route "POST /api/v1/orders"  # ranked, budgeted
python .specify/extensions/memory/scripts/archive.py memory show --id PM-order-totals                            # exact entries
python .specify/extensions/memory/scripts/archive.py memory catalog --domain billing                              # browse a domain
python .specify/extensions/memory/scripts/archive.py memory check                                                 # budgets, references, freshness
python .specify/extensions/memory/scripts/archive.py memory export                                                # legacy single document
```

An archive run writes a **delta candidate**: additions, full-entry updates and removals guarded by the sha256 of
the current entry file, compact provenance grouped by path, tombstones, taxonomy changes and coverage grouped by
path. An update that no unit of the run supports needs a written `reason` (a reviewed correction). `validate`
rejects a changed base memory (no automatic rebase), materializes the whole result on a temporary copy and checks
it; the reviewer binds the base and result memory roots. `finalize` writes the changed entries, one new ledger and
the regenerated views. Rollback deletes the files the run created.

### Large runs: parallel drafting and partitioned review

```bash
python .specify/extensions/memory/scripts/archive.py packets --run <id>          # split units; one owner per domain
python .specify/extensions/memory/scripts/archive.py fragment-check --run <id> --fragment <path>  # per drafter
python .specify/extensions/memory/scripts/archive.py merge --run <id>            # compose, or report conflicts
python .specify/extensions/memory/scripts/archive.py review-packets --run <id>   # review parts of at most 40k tokens
```

Each drafter writes one fragment for its packet and may change only entries its packet owns; it proposes changes
to other entries. `merge` rejects colliding ids, double or conflicting edits, coverage gaps or overlaps, conflicting
repairs, fixtures, taxonomy changes or tombstones, broken references and ownership violations. `review-packets`
cuts each fragment into review parts of at most 40k tokens and adds one integration packet (shared selectors and
relations, near-duplicate titles, taxonomy changes, every update with its reason, removals and proposals). Once a
run has packets, `review.json` needs a passed approval for every part and for the integration packet.

### Upgrading from 1.x

2.0.0 changes the memory format. Finish or roll back any active 1.x run first; a 2.0 `prepare` refuses while one
exists. Add `memory_root`, `memory_budgets` and `tokenizer` to `.specify/memory-policy.json` (see the shipped
`archive-policy.json`), then run `python .specify/extensions/memory/scripts/archive.py migrate` once. It writes
`specs/memory/`, proves that `memory export` reproduces the old document byte for byte, records that hash in its
commit, and replaces `specs/project-memory.md` with a navigation stub. The policy hash changes with the extension,
so automatic mode must be approved again.

## Fixtures and recovery

Machine-required artifacts move with exact committed bytes to `tests/Fixtures/spec-memory/<feature>/`, with tested consumer repairs. Other assets remain recoverable through `git show <checkpoint>:<original-path>`. `specs/.archive-index.json` reserves feature numbers and checkpoint provenance. Stable memory IDs retain immutable source references in the provenance ledgers. Entry text uses no level 1 or 2 headings. Unexpected manual content is preserved and requires explicit reconciliation.

Journals, candidates, reviews and check logs live in Git's local `sanduq-memory/` directory. Helpers emit JSON with `success` and fail nonzero:

```bash
python .specify/extensions/memory/scripts/archive.py status
python .specify/extensions/memory/scripts/archive.py pending --gate
```

`finalize --run <id>` resumes unchanged transactions. `abandon --run <id>` retires unpublished stale proposals. Explicit `rollback --run <id>` restores recorded original bytes and scoped index after permanent publication/check failure, preserves the checkpoint and removes the failed queue entry. It refuses unexpected edits or an already-created final commit; interrupted rollback is resumable. Active archives gate new feature/branch/broad auto-commit workflows. Read-only state reports busy/stale writers without taking their lock; confirm the recorded process has exited before removing only a stale lock. No reset, clean, silent rollback or journal discard occurs. Coverage/provenance validation cannot prove semantic synthesis; a separate reviewer is essential.

## Development checks

```bash
python -m unittest discover -s extensions/memory/tests -v
python extensions/scripts/package.py memory
python extensions/scripts/release.py prepare --development
```

Tests run in disposable Git repositories with real PowerShell/Bash entry points, scoped commits, fixture consumers, reconciliation and interrupted recovery.

## Archive when verification is failing

Verification is required by default. For an explicitly selected manual archive,
ask the agent's archive/run command to use `--skip-verification "<reason>"`, for
example `specs/412-refund-approval --skip-verification "Test service unavailable"`.
The underlying preparation command is:

```bash
python .specify/extensions/memory/scripts/archive.py prepare --spec specs/412-refund-approval --skip-verification "Test service unavailable"
```

This skips fresh passing verification evidence and external post-deletion checks.
It records `verification.status: skipped` and the reason in the archive index and
both Git commits; it never reports the checks as passed. Use a nonempty printable single-line
reason of at most 500 characters suitable for permanent repository history.
The normal candidate synthesis, independent review, fixture migration/reference
repair, scoped checkpoint/final commits and recovery still apply. The reviewer must
acknowledge the exact reason via `verification_override` in `review.json`.

Only explicit manual selections support this option. Automatic archiving and
`--all-completed` still require verification. Unfinished tasks still require a
separate explicit retirement decision. Named checks cannot be combined with the
skip; explicit related implementation files may be checkpointed, but remain
unverified. Consumer repairs will not be tested, so review their exact changes and
retain meaningful unresolved limitations in memory. Existing transactions keep
their original verification mode: abandon before publication or explicitly roll
back after publication, then prepare a new override; do not edit a journal.
Updating this extension invalidates any previous automatic-policy approval.
