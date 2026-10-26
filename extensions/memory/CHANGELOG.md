# Changelog

## [2.5.1] - 2026-10-23

- Preflight accepts tracked feature evidence that matches an ignore rule. The scoped checkpoint preserves its current edits and deletions. Untracked ignored evidence still blocks archival unless its owner's declared runtime rule makes it disposable.
- License: this package is MIT; versions before this one were PolyForm Noncommercial 1.0.0. The archive now ships its LICENSE.


## [2.5.0] - 2026-10-21

Optimization round 4. No renames.

Round 4 (D3, Memory side: Sanduq Workflow owns the session and prepare hooks).

- The approval hash reads each Memory hook entry with its event heading, so moving an entry to another event voids the approval (the old reader hashed the block alone). Command, condition, priority and every other field stay bound. The `enabled:` line is left out only for `speckit.memory.session` and `speckit.memory.prepare`, so Workflow's reconcile can disable them without stopping automatic archiving.
- A Memory hook entry in a layout the approval cannot read (another key first, indented lists, no `command:`) now refuses with a message instead of being left out of the hash.
- `install.py` keeps an existing `enabled: false` hook entry byte for byte, so a Memory re-init no longer re-enables a hook Workflow disabled (Workflow's next install then failed `HOOK_CHANGED_SINCE_RECONCILE`).
- `install.py` edits only the `hooks:` mapping of `.specify/extensions.yml`. Before, a top-level key after `hooks:` (Spec Kit can write `settings:` there) was deleted or had Memory's hook entries appended under it.
- `archive.py pending` also returns `policy_hash` and `policy: {target_branch, default_checks}` when automatic mode is on, so Workflow's handoff skips the separate `policy` call (one helper process, about 0.6 s, per transition).
- A queue entry from before the current approval stays as it is and is reported blocked with the fix (archive it manually or re-queue it), never re-stamped.
- `session.md` honours the handoff's `--run <id>` and `--spec <dir>`. `prepare.md` has a managed branch: choose the checks, run the read-only preflight, then return them through `workflow.py memory-handoff --transition execute`.
- The SESSION block says that in a Workflow project the claim runs the session check and covers the `pending --gate` check, so neither is run separately.
- `queue`, `prepare` and the other feature commands accept Workflow's unpadded issue-numbered feature directories (`specs/2-add-a-flag`), as well as Spec Kit's `001-name` and `20260101-120000-name`. Before, every Workflow feature for issues 1 to 99 failed "Select a full feature directory directly under specs/.", so the Execute handoff queued nothing. Folders without a leading number, such as `specs/memory`, are still refused.
- README: install the catalog with `--priority 1` (the lowest number wins in Spec Kit).
- `queue` and the archive no longer refuse a feature that holds Workflow's or Progress's runtime files (checkpoint backups, the progress report, Progress's `.view` and `.host`). A file counts as runtime only when the exclude rule that ignores it is a line of `.git/info/exclude` that its owner declared in `.git/info/sanduq-runtime.json`. Runtime files are left out of the queued and archived feature hashes and deleted with the folder. Any other ignored file in a feature folder still refuses. Before, every managed feature whose Execute wrote a progress report failed `Ignored artifacts are not recoverable from the checkpoint`, so the Execute handoff queued nothing.
- The approval hash reads text files with CRLF folded to LF (binary and non-UTF-8 files stay byte exact). Before, a checkout under `core.autocrlf=true` rewrote the approved files with CRLF, automatic mode turned off on every branch switch on Windows, and re-approving blocked the entries queued under the earlier approval.

### Migration

- Workflow writes its declaration at every Memory handoff, so a managed project needs no step. Progress writes its own at `progress init` or the next report; until then a feature holding Progress's `.view` or `.host` files still refuses.
- Re-approve once after the update: run `speckit.memory.enable` (every Memory release changes the hash; this one also changes the hook format and the line-ending rule, and the one renewal covers both). Approve on any branch: the hash no longer changes with checkout line endings. Entries queued before the renewal are reported blocked: archive each manually with `speckit.memory.run --spec <dir>`, or re-queue it from its implementation branch.
- Finish or recover an active archive (`archive.py status`) before updating; a prepared run refuses a changed implementation hash.
- With Sanduq Workflow: install this release before the Workflow release that disables the two hooks.
- If an earlier `speckit.memory.init` ran on an `extensions.yml` with `settings:` after `hooks:`, check that file: restore a lost `settings:` block from git (for example `auto_execute_hooks`), then rerun init.

## [2.4.0] - 2026-10-20

Optimization round 3.

- The run procedure drops the duplicate preflight step (verify and prepare run it) and the always-true `ok` check.
- The seven descriptions total 724 characters (983 before).

## [2.3.0] - 2026-10-19

Optimization round 2.

- `run.md` is a 4.7 KB procedure (21.2 KB before) with references read by step from `.specify/extensions/memory/references/`: candidate format, verification override, large runs, format 1, review and publish, recovery. A small archive's common path reads about 14 KB.
- `memory show` and `memory query --format json` print `expected_hash`; `status`, `inspect --view status`, `validate` and `finalize` return `next: {command, reason}`.
- Descriptions come from the command frontmatter only. `prepare` and `session` are hidden from the Claude menu (`user-invocable: false`). The registry records the manifest version.
- Opt-in guard hook: with `guard_hooks: true` in `archive-policy.json`, an active archive refuses `git push|stash|reset|clean` and writes under `specs/memory/`. It is off by default.
- The standing SESSION block is four lines.

## [2.2.1] - 2026-10-18

- Archive prepare and finalize no longer fail when a scope names files that are tracked under an ignored parent such as `artifacts/`. The expected tree stages tracked edits and deletions with `git add -u` and adds new unignored files by name. Untracked ignored files stay out of the commit, and one named exactly as a scope is still refused.
- Direct `archive.py` commands now write UTF-8 JSON to stdout and stderr, so `status` no longer fails with a charmap error on a Windows cp1252 console when a journal holds text such as an arrow or Arabic.

## [2.2.0] - 2026-10-17

- Native early preflight, bounded archive inspection and batched Git inventory.
- Opt-in complete check-input manifests permit hash-validated receipt reuse; legacy checks keep conservative freshness.
- Preserve exact critique/publication guards and both memory formats.

## [2.1.2] - 2026-10-10

- README links point to the new extension page, install-by-host page and command reference.

## [2.1.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

## 2.1.0

- Typed links: entries may list `constrains` (live entries whose behavior this entry limits) and `supersedes`
  (entries describing an older state) beside the untyped `relations` (see also). Both are optional, so existing
  entry files are unchanged.
- `memory query` ranks a constraining entry just below the entry it constrains (reason `constrains`), even outside
  a `--domain` filter. A superseded hit drops below its replacement, which joins the results (reasons
  `superseded-by` and `supersedes`). Rendered entries list `Constrains`, `Constrained by`, `Supersedes` and
  `Superseded by`, and linked entries not returned include incoming typed links.
- `memory check`, delta validation, `fragment-check` and `merge` resolve typed links. A link may not point to its
  own entry or repeat an id across the three lists, and `constrains` targets must be live.

## 2.0.0

Breaking: project memory moves from the single `specs/project-memory.md` to an atomic store under `specs/memory/`.
Finish any 1.x run, add the new policy keys and run `archive.py migrate` once; migration is lossless and proves a
byte-exact export.

- One entry per file, a governed taxonomy, append-only per-run provenance ledgers, and generated INDEX and catalog
  pages within token budgets (`memory_budgets`, `tokenizer`).
- `memory query/show/provenance/catalog/check/index/export`: budgeted, ranked retrieval with match reasons and a
  continuation cursor; `impact` is query-first.
- Delta candidates validated as one materialized result; review binds the base and result memory roots and the
  exact outputs; finalize and rollback cover entry files and ledgers.
- Parallel drafting (`packets`, `fragment-check`, `merge`) with entry ownership, proposals and conflict classes, and
  partitioned review (`review-packets`) in parts of at most 40k tokens plus an integration packet.
- Reviewed corrections may carry a `reason` instead of a source unit in the run.
- Pathspecs go to Git on stdin, so large archives no longer exceed the Windows command-line limit.

## 1.1.0

- Allow explicit manual archives to skip verification with a recorded reason.
- Keep automatic verification required and preserve review, fixture/reference validation and recoverable scoped commits.
- Bind the override to the checkpoint and reviewer acknowledgment; record skipped status in the archive index and CLI results.

## 1.0.1

- Remove project-specific references from documentation, examples and installer messages.
- Detect conflicting archive tooling by its capabilities rather than a project-specific ID.

## 1.0.0

- Introduce Sanduq Memory as a project-configurable specification archive extension.
- Provide seven commands for Codex, Claude Code and Copilot, lifecycle hooks, independent review and source coverage.
- Preserve scoped checkpoints, current-memory reconciliation, fixture/consumer repair, number reservations, final commits and journaled resume/explicit rollback.
- Configure merge branch, implementation inputs and actual named verification checks per project.
- Install guards with context checks; preserve custom scripts and require approval before replacing existing archive tooling.
