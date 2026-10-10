# Workflow CI evidence and runner policy

This page describes how Verify, Review and Ready receipts survive later source commits, how a CI run becomes Verify evidence, how the evidence gate checks a feature before publication, and which runner settings it reads. For choosing a gate mode, see [delivery policy](delivery-policy.md); the gate script is [`ci_gate.py`](../../extensions/workflow/scripts/ci_gate.py).

Back to the [Workflow guide](../../extensions/workflow/README.md).

## Source drift and CI evidence (1.6.0)

Verify, Review and Ready receipts inventory the source tree
(`source_fingerprints`), so before 1.6.0 any later commit to a source path
staled all three, even a README edit. They now also record `head` and
`source_key`: the canonical key `sanduq-source-key/1` of HEAD's tree (keys recorded under
the previous key version are still accepted), computed
by `scripts/source_key.py` from `git ls-tree -r -z --full-tree` on raw bytes
(paths under `.specify/`, `.agents/`, `.claude/`, `.codex/`, `specs/`,
`User-Manual/`, `docs/`, `graphify-out/`, `artifacts/` and every `*.md` are
left out). The key is recorded only when no source path differs from HEAD.
The shared fixture file `tests/fixtures/source-key.fixtures.json` is
byte-identical to the consumer's copy and pinned by SHA-256 in the tests.

Explicit fingerprints (inputs and evidence) keep their byte-hash check in every
case. When the source inventory drifted:

- **Affected-lane hook** (`ci.gate.affected_command`, optional). A command
  string or argv list that reads a JSON list of repository paths on stdin and
  prints `{"paths": {"<path>": ["<lane>", ...]}}`. A receipt with a
  `source_key` stays current when every drifted path maps to no lane and none of
  them is one of the receipt's explicit fingerprints. Markdown or committed
  artifacts therefore keep Review current; a test, workflow or product-source
  change stales it. A hook that fails, prints anything else or leaves a path out
  fails closed (the receipt is stale). Without the hook, and for a legacy
  receipt without `source_key`, the identity rule applies as before.
  A second, separate optional key, `ci.gate.verify_command` (1.7.x, B13), is
  never read by the gate itself: it is the project-local runner
  `speckit-workflow-verify-affected` invokes to actually run the lanes
  `affected_command` classifies, into a results.json.
- **A CI run as Verify evidence** (`ci.gate.verification_check`, optional: the
  job name, or `{name, workflow, artifact_prefix}`; for example
  `"Bootstrap required lanes"`). `workflow.py revalidate --feature
  specs/<feature> --stage verify --check-run <run id> [--attempt <n>]` reads the
  run, its jobs and its plan artifact `<prefix>-<run>-<attempt>`
  (`verification-plan.json`, the consumer's verification-plan contract) through
  the GitHub REST API (`gh api`). It requires the run completed, not cancelled,
  with the named job concluding `success`; every plan field matching the run;
  the plan's tree equal to the head commit's tree through the API and locally;
  the plan's source key equal to the key recomputed locally and to the key of
  the current clean HEAD; the run's head a commit of this branch; the receipt's
  explicit fingerprints still byte-matching; and the run's lanes a superset of
  the lanes the hook assigns to the drifted source paths (so the hook is
  required when source drifted). It then writes `ci_evidence {run_id, head,
  source_key, tier, lanes, conclusion, ...}`, re-inventories
  `source_fingerprints` at HEAD and records a `revalidations[]` entry. Evidence,
  summary and `blocking_findings` are untouched. A run whose lanes miss a
  required lane records the gap, marks Verify `stale` (`ci-lane-gap`) and
  exits 1; a later run covering the lanes closes it. The gate accepts a Verify
  receipt whose inventory drifted while its CI run still covers the current
  source key, and only when its `ci_evidence` is the complete record
  `revalidate` writes: `run_id` and `attempt` positive integers, `head` 40-hex
  and the receipt's `head` (or a commit of it), `source_key` 64-hex, a
  non-empty `tier`, `lanes` and `required_lanes` lists of strings with
  `required_lanes` inside `lanes`, `conclusion: success` and an empty
  `lane_gap`. A missing or malformed field is not current (fail closed). The
  checkpoint is a committed file, so `ci_gate.py` never trusts the record
  alone: it always re-reads every run a Verify receipt is accepted through
  (the check job, the plan artifact, the tree and the source key) through the
  REST API, and fails closed when it cannot (`CI_EVIDENCE_UNREADABLE`: an API
  error, no token or no `gh`; `CI_VERIFICATION_CHECK_UNSET`: no
  `ci.gate.verification_check` to read it by) or when the run no longer
  matches (`CI_EVIDENCE_REJECTED`). The shipped gate job has
  `permissions: actions: read` and passes `GH_TOKEN` for this;
  `--verify-ci-evidence` (1.6.0) is still accepted and changes nothing.
- **Review** is revalidated only after an incremental review of the source
  diff `<review head>..HEAD` is recorded under `specs/<feature>/` with four
  lines: `Diff reviewed: <review head>..<HEAD>`, `Diff sha256: <hash>`,
  `Reviewer: <name>` (non-empty) and `Blocking findings: 0`. The hash binds the
  note to the exact diff, so a note written without the diff, or kept from an
  earlier range, is refused (`DIFF_REVIEW_HASH_MISSING`,
  `DIFF_REVIEW_HASH_MISMATCH`, `DIFF_REVIEW_REVIEWER_MISSING`, each printing
  the command below). It is the SHA-256 of the exact bytes this command
  prints, run in a POSIX shell (Git Bash on Windows):

  ```sh
  git -c core.quotePath=true diff-tree -r -p --binary --no-renames <review head> <HEAD> -- . \
    ':(exclude).specify/' ':(exclude).agents/' ':(exclude).claude/' ':(exclude).codex/' \
    ':(exclude)specs/' ':(exclude)User-Manual/' ':(exclude)docs/' ':(exclude)graphify-out/' \
    ':(exclude)artifacts/' ':(exclude,glob,icase)**/*.md' | sha256sum
  ```

  `diff-tree` is plumbing, so personal diff settings (prefixes, colour,
  renames, algorithm, external or textconv drivers) cannot change the bytes,
  and the pathspec keeps exactly the paths the source key counts (the
  source-key exclusions, and `*.md` in any case). `revalidate --stage review
  --diff-reviewed <file>` recomputes it, adds the file to the receipt's
  evidence (with its hash) and records `diff_reviewed` with `diff_sha256` and
  `reviewer`. A review receipt without `head` (written before 1.6.0) is
  re-recorded instead.
- **Ready**: `revalidate --stage ready` re-runs task completion, the
  task-issue mapping and the selected documentation freshness checks
  (`--base-ref` defaults to the bound target branch).

Revalidation needs every earlier stage current, no active claim and no
uncommitted source change; it never re-hashes an input or evidence path and is
never accepted on a `--reason` alone. A receipt a `changed` amendment staled is
re-recorded. Both `next` (`recovery`) and a failing gate (`STALE_RECEIPT: ...;
recovery: ...`) print the exact commands: `amend` for changed evidence,
`revalidate` where a checked route applies, otherwise the `claim`/`complete`
re-record. A typical sequence after a test change: push, wait for the check,
`revalidate --stage verify --check-run <run>`, review the diff and record it,
`revalidate --stage review --diff-reviewed <file>`, `revalidate --stage ready`,
then commit the checkpoint (an operational path, so the source key is unchanged).

## Upgrades

Use `upgrade.py --version X.Y.Z` preview, then `--apply`, to update the workflow
package and its integrations with outer rollback. Local staged testing supports
`--packages <extracted-packages>`. See the [operating guide](operating-guide.md)
and [compatibility contract](../reference/compatibility.md) for tested limits.

## Task issue sync

`task_issues.py` is dry-run by default. The core Tasks-to-Issues preset invokes it
with `--apply` within authorized issue work. Native sub-issues are identified by
repository, parent, feature and task ID; retries recover lost responses. Existing
Project mappings are adopted only after verifying native parent links. Unmapped
children block duplicate creation. `--sync-states` updates task issue completion
without changing the publication evidence; it walks every task in `tasks.md` on
each call, so it is safe to invoke once per phase for a whole batch of newly
completed tasks rather than once per task. A task title (`T### : description`)
over GitHub's 256-character issue title limit is shortened to the headline
instead of rejected; the full description is always kept in the issue body.
Shortening is deterministic, so re-syncing an unchanged task recomputes the
same title and body and neither creates a duplicate issue nor rewrites it.
`--summary` prints one line (`ok created=<n> reused=<n> total=<n> dry_run=0|1` for a
sync, `ok opened=<n> closed=<n> changed=<n> dry_run=0|1` for `--sync-states`, or
`error <message>`) instead of the full JSON result; `--json` prints exactly what
the default (no-flag) output already prints today, byte for byte — it is a way
to request that output explicitly, not a new format. `--summary` and `--json`
together is rejected. Exit codes are unchanged either way, including for an
exception outside the normal `WorkflowError`/`ValueError`/`KeyError` set, which
`--summary` also reports as one `error <Type>: <message>` line instead of a
raw traceback.

## CI evidence gating modes

The project selects Disabled, Advisory, or Required CI evidence gating and
individual rules at initialization or later. Managed-only scope lets ordinary
source-only bug-fix PRs pass with an explicit `not_applicable` result. Enabled
rules distinguish committed receipts and decision evidence from live GitHub
checks and human acceptance. Disabling the job checks active branch rules so a
required check is not stranded. Finalize also verifies that each inline PR visual
loads in an authenticated private-repository view.

## Publication check

Before publication, run `ci_gate.py --feature specs/<feature> --base-ref <target-sha>
--check-index` after staging reviewed evidence, then repeat the gate in a clean
checkout of the candidate commit. Missing/unstaged dependencies are reported by
path; the command never stages files. When a missing path is one Git itself
ignores (e.g. a `*.log` match), the report names the exact `git add -f <path>`
recipe to recover it. It also warns, without failing the check, when a
receipt's recorded evidence references a path under another feature's
`specs/` directory (surfaced as `index_warnings` on that feature's gate
result) -- a likely copy/paste or fixture mistake worth reviewing before
publication. Target-branch source changes invalidate old verification even
when Git merges cleanly. Configure `workflow-evidence` as a required branch
check only when this project has deliberately selected Required mode;
otherwise leave its branch rule optional.

## Text fingerprints

UTF-8 text fingerprints normalize CRLF across checkout platforms. Explicit Git
`-text`, SQL, NUL-bearing and non-UTF-8 files remain byte exact; lone CR is not
normalized. Shared QA/manual hashing follows the same contract. Generated graph
files are excluded from implicit documentation input discovery but remain checked
when explicitly declared as outputs. Revalidate affected historical receipts after
adopting this changed contract; do not relabel old evidence.

## End of the dispatcher

The dispatcher ends at PR publication. Its `pr_open` state is not post-merge
certification. Follow the skill's post-merge protocol and retain an external-state
report of exact SHAs, checks and rollout observations.
