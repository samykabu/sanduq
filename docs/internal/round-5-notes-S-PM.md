# Round 5 notes: S-PM (PR and Project)

No git command changed the tree or index.

## PM5: `project_init.py`

### Compatibility table (written before the code)

`extensions/project/scripts/project_init.py` takes both spellings (PowerShell's case-insensitively). The
one-release stubs `bash/project-init.sh` and `powershell/project-init.ps1` print one deprecation line naming
the Python command and pass every argument through unchanged.

| Bash flag | PowerShell flag | Behaviour (both before and after) |
| --- | --- | --- |
| `--owner <login>` | `-Owner <login>` | Project owner. Default: the authenticated user (`gh api user`). |
| `--number <n>` | `-Number <n>` | Project number. Absent or 0: list the owner's projects; one is taken; several is a missing choice. |
| `--owner-type user\|org` | `-OwnerType user\|org` | Absent: `gh api users/<owner> --jq .type` (`Organization` gives `org`). |
| `--hooks-mode optional\|required` | `-HooksMode optional\|required` | Absent: the existing `config.json` `hookMode`, else `optional`. A Workflow project always uses `required` and leaves `extensions.yml` alone. |
| `--auto-create-columns` | `-AutoCreateColumns` | Create (or, managed, rename a case or spacing variant of) each missing column, once per name. |
| `--non-interactive` | `-NonInteractive` | Accepted and ignored: the script never prompts. |
| `--allow-status-reset` | `-AllowStatusReset` | Change columns even when the board's items cannot be read; their Status is then cleared. |
| `--dry-run` | `-DryRun` | No GitHub mutation, no `extensions.yml` or `config.json` write; prints what it would do. |
| `--json` | `-Json` | The written config as one compact JSON line, last. |

Kept behaviour: rerun preservation of `parentIssue`, `subIssues`, `stateFile` (and `hookMode` when no flag);
B3 (one create per name, every option id from the update's answer, managed exact matching plus the doctor's
`statuses`, case variant renamed); the board-status guard (read every item, archived included, by paged
GraphQL before the option update; set each Status again by name afterwards; unarchive, edit, archive for an
archived item; each failure named and exit 1 after `config.json` is written; unreadable items refuse before any
change unless `--allow-status-reset`); owner type from the account type; unmanaged exact, case-insensitive and
fuzzy matching; a phase without a column is a warning and stays unmapped.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Config written (or printed under `--dry-run`). |
| 1 | An error (no git repository, no `config.default.json`, invalid `config.json`, gh missing, not logged in, no `project` scope, a failed `gh project` read, no Status field, no projects, unreadable items without `--allow-status-reset`, no project hooks in `extensions.yml`, unreadable Workflow defaults), or an item whose Status could not be set again (after `config.json` is written). |
| 2 | Usage error: a bad `--owner-type`, `--hooks-mode` or `--number` value (argparse). Before: bash exit 1 for a bad hooks mode; PowerShell parameter validation. |
| 4 | A missing choice: stdout's last line is `{"ok": false, "needs": [...]}`, each entry with `flag`, `why` and `options`. Nothing is written. Cases: several projects (`--number`, options are `{number, title}`); an owner whose account type cannot be read (`--owner-type`). Before: exit 1 with a message. |

Deliberate changes: messages name the Python spelling (`--number`) on every shell; the managed Workflow
defaults are read with the running interpreter instead of `python` from `PATH`; `jq` is no longer needed;
phases are mapped to a created column only after the update succeeded (the PowerShell rule; bash mapped them
before, so a failed or dry-run creation wrote a column that did not exist).

### What was done

- New `extensions/project/scripts/project_init.py` (stdlib). It reaches `gh` through `project_sync.gh_raw` (so
  through `sanduq_gh`, below) and `sanduq_gh.token_scopes`.
- `bash/project-init.sh` (6 lines) and `powershell/project-init.ps1` (9 lines, no param block, so `$args` holds every
  argument) are one-release stubs: one deprecation line naming `project_init.py`, then `python` (else `python3`)
  runs it with every argument, and the exit code passes through.
- `commands/speckit.project.init.md` is one invocation: 2,676 B before, 1,771 B after (0.34 less). It keeps the
  hook-mode question (the script defaults it, as before) and says what exit 4 means.
- README (the unattended example, the stub note, the files list, "exact → fuzzy → optional auto-create", the exit-4
  sentence) and the `config.default.json` `$comment` name `project_init.py`.
- Tests (`extensions/project/tests/test_project_sync.py`, `ProjectInitTests`): the PowerShell function intercept and
  the bash-only PATH fake are replaced by one fake `gh` first on `PATH`: a shebang script on POSIX, and on Windows
  (where a subprocess finds only `.exe` files) pip's console-script launcher (`pip/_vendor/distlib/t64.exe`) with
  the fake appended as a zip, the format pip itself uses; the test skips when pip is absent. Every earlier init test
  is kept and now runs the Python script: scope refusal, org owner, rerun preservation, B3 managed auto-create,
  status restore by name with archived items over two pages, unreadable items refused unless allowed, a failed
  item edit reported with exit 1. One deliberate change: "several projects" asserts exit 4 and the `needs` JSON
  (it asserted any non-zero exit, and the spelling `-Number` for pwsh). New: an unreadable owner type gives exit 4,
  then works with the flag; the hook mode is written to every project hook keeping CRLF, and exit 1 when no project
  hook exists; a dry run with column changes mutates and writes nothing; both spellings directly and through each
  stub (bash and pwsh, where installed), including exit 4 passing through the stubs.
- `extensions/scripts/smoke_project_init.py`: installs the built `project` and `workflow` archives (it copied the
  source tree before, which lacks the injected helpers), puts the same kind of fake `gh` on `PATH`, and runs
  `project_init.py` by default; `--shell pwsh|bash` still runs a stub. The fake now prints gh's real
  `Token scopes:` line (`token_scopes` reads only that line; the old twins grepped any word "project").

### Tests run (PM5)

- `python -m unittest discover -s extensions/project/tests -q`: 34 OK (final run, after SC8).
- `smoke_project_init.py` (default python) and `--shell pwsh`: ok on Windows. `--shell bash` on Windows picks
  `System32\bash.exe` (WSL) through the `CreateProcess` search order and fails before init runs; the old smoke ran
  bash only on Linux CI, unchanged.

## PM2b: review-feedback reply and resolve from an approved plan

- `pr_feedback.py plan|reply|resolve --plan <file> [--approved <digest>]`. Plan schema
  `sanduq.pr.review-plan.v1`: `repo`, `pr`, `replies` `[{thread, comment, body}]`, `resolves` `[thread id]`, `head`
  (null until the push). `digest` = sha256 of the canonical JSON of everything but `head` (the head is known only
  after the approved fixes are pushed, so it cannot be inside the approved digest).
- `plan` (read-only) validates the file, reads every review thread of that PR (paged, resolved ones too), refuses
  any thread or comment not on it, and prints the digest.
- `reply` and `resolve` refuse (exit 1, before any GitHub call) a plan whose digest is not `--approved`, and refuse
  (exit 1, before any write) threads or comments of another PR. `resolve` refuses until `head` is set and the PR head
  on GitHub equals it or contains it (`compare` status `ahead` or `identical`; an unknown commit counts as not
  pushed), and until each resolved thread's approved reply is on GitHub. Idempotent: a reply by the viewer with the
  same text, or a resolved thread, is skipped. A failed write exits 3 naming what was already done; a rerun
  finishes the rest. Writes are never retried.
- `speckit.pr.review-feedback.md`: sections 2 (untrusted content), 4 (approval gate) and 6 (commit and push) are
  unchanged; step 3 ends with writing the plan file outside the working tree and running `plan`; step 5 posts with
  `reply`; step 7.2 sets `head` and runs `resolve`. 5,369 B before, 6,326 B after (the plan schema is inline).
- Tests: `test_pr_feedback.PlanTests` (digest leaves out only `head`; changed plan refused with no gh call; foreign
  thread, foreign comment and foreign resolve refused in all three actions; replies posted once, then skipped; a
  reply run failing halfway finishes on rerun; resolve refused for no head, unpushed head, behind and diverged, then
  done for equal and ahead; resolve waits for the reply; a resolve run failing halfway finishes on rerun; eight
  malformed plans and a missing plan exit 2; `--approved` required). `test_pr_command.ReviewFeedbackTextTests` pins
  the three trust sections verbatim and the three script calls.

## SC8 PR/Project side

- Project: `project_sync.gh_raw` runs `sanduq_gh.run_gh(args, payload=stdin, timeout=120)` and keeps its
  `(rc, output)` contract (stderr joined on failure, 127 for a missing gh, a timeout raises `RuntimeError` with the
  same text). Its own `token_scopes` is gone (`sanduq_gh.token_scopes`); the budget probe's failure test is
  `sanduq_gh.rate_limited` (now also GraphQL's `RATE_LIMITED`). Every `gh_raw` path (budget probe, labels, parent
  lookup, auth, the GraphQL-to-REST switch, dry-run) is unchanged above the runner. `project_init.py` uses the same
  runner. No retries anywhere (Amendment 1 makes them opt-in; none opted in, so behaviour stays).
- PR: `pr_publish.run` stays the seam (tests replace it); a `gh` call inside it goes through
  `pr_publish.gh_process` → `sanduq_gh.run_gh(timeout=120)` and still returns a CompletedProcess, so `:101` (contents
  check) and `:159` (PR view) share the transport. `pr_changelog.run` uses `gh_process` with 60 s and still returns
  None for a missing or hung tool. `pr_feedback.run` uses `run_gh(timeout=120)` and keeps `Failure(3)` with the old
  message text.
- Tests: `test_project_sync.test_gh_calls_go_through_the_shared_transport_never_retried` (fails before: it checks the
  module identity, the dropped local `token_scopes` and the `RATE_LIMITED` switch); `test_pr_publish.TransportTests`
  and `test_pr_feedback.TransportTests` (timeouts 120/120/60, no retry, error shapes). The existing hung-gh test
  passes unchanged (`subprocess.run` is patched module-wide, so it reaches `sanduq_gh`).

## Test results (end of stream, uv Python 3.11)

- `python -m unittest discover -s extensions/project/tests -q`: 34 OK.
- `python -m unittest discover -s extensions/pr/tests -q`: 42 OK.
- `smoke_project_init.py` and `--shell pwsh`: ok (Windows).
- Dependents: workflow modules `test_sync_binding test_guard_hook test_front_half_runtime`: 84 OK;
  `extensions/scripts/tests` modules `test_sanduq_remote test_ci_matrix test_sanduq_gh`: 78 OK.
- `check_docs.py`: fails only with "docs/reference/hooks.md is stale"; the diff is the scope-gate and
  scope-brainstorm preset strategy (`prepend` to `replace`), S-SC's SC17, not this stream.

## Requests

- **S-CI** (`.github/workflows/ci.yml`, job `project-init`): drive the Python script on both OSes. Replace the
  matrix, `runs-on`, the smoke step and the artifact name; checkout, setup-python and the pip install stay:

  ```yaml
    project-init:
      needs: changes
      if: needs.changes.outputs.install_smoke == 'true'
      strategy:
        fail-fast: false
        matrix:
          os: [ubuntu-latest, windows-latest]
      runs-on: ${{ matrix.os != 'ubuntu-latest' && matrix.os || (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name != github.repository) && 'ubuntu-latest' || 'homek8-general' }}
      steps:
        # checkout, setup-python and the pip install step unchanged
        - run: python extensions/scripts/smoke_project_init.py
        - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
          if: always()
          with:
            name: project-init-${{ matrix.os }}
            path: |
              dist/project-init-tests/*/result.json
              dist/project-init-tests/*/execution.log
            if-no-files-found: ignore
  ```

  On Windows the smoke builds its fake `gh.exe` from pip's launcher, which setup-python's interpreter has. The
  stubs are covered by the project suite on both OSes. Until this lands the current job still works (`--shell
  pwsh` and `--shell bash` run the stubs on Linux).
- **Orchestrator / S-SH**: `token_scopes` is no longer defined in `project_sync.py`; it can join
  `OneDefinition.MOVED['sanduq_gh.py']` in `extensions/scripts/tests/test_sanduq_remote.py`.
- **S-WF** (optional): the comment at `extensions/workflow/tests/test_ci_policy.py:421` says "project-init.sh runs
  workflow.py"; it is now `project_init.py`, with the running interpreter.

## Not done

- `--shell bash` of the smoke on Windows (WSL bash is found first); not a CI case.
- No live run against GitHub: `project_init.py`, `reply` and `resolve` were tested with fakes only.

## Codex review fixes (after df0baf6; `round-5-codex-review.md` findings 3, 5, 8, 9)

Each regression test was run before its fix and failed (3: `FileNotFoundError`, no `config.json`; 5, 8, 9: one
failure and seven errors in `PlanTests`, the new `--approved-head` flag unknown), then passes.

- **3 (high), `project_init.py` restore.** A timeout (`RuntimeError` from `gh_raw`) on an item's unarchive or edit
  aborted the run: no re-archive, the remaining items skipped, the new option ids never written. Every call in the
  restore loop now goes through a per-item `attempt` that turns a timeout into that item's failure; an item whose
  unarchive succeeded or timed out is archived again whatever the edit did; the loop continues; `config.json` is
  written with the new ids; exit 1 names each failed item. Test:
  `test_a_timed_out_item_edit_rearchives_continues_and_still_writes_the_config` (runs init in process with
  `gh_raw` wrapped so the edits of I1 and archived I4 time out; I2 is still restored, I4 is unarchived then
  archived, the config holds the new ids, both failures are named). Not changed: a timeout on the
  `updateProjectV2Field` call itself still stops init with exit 1 before `config.json` (the new ids are unknown
  then).
- **5 (medium), `head` outside approval.** `head` now gets its own approval: once it is set, `plan` also prints
  `head` and `head_digest` (sha256 of the plan digest, `:` and the head); `resolve` requires `--approved-head` (exit
  2 without it) and refuses, before any gh call, a head whose digest is not the approved one (exit 1). Command step
  7.2: set `head`, run `plan` again, show `head` and `head_digest`, ask for explicit approval, then `resolve ...
  --approved-head <head_digest>`. Sections 2, 4 and 6 unchanged (pinned by `test_pr_command`). Test:
  `test_resolve_needs_a_second_approval_covering_the_pushed_head` (head edited to the PR's current head after
  approval is refused with no gh call; no second approval exits 2; the approved head resolves).
- **8 (medium), GraphQL errors on exit 0.** `resolve` checks the mutation's answer: any `errors`, or a
  `resolveReviewThread.thread.isResolved` that is not true, is a failure (exit 3 with what was already resolved).
  The check sits on the `run` seam rather than `sanduq_gh.graphql`, so the fake runner stays the test seam. Test:
  `test_a_graphql_error_on_a_successful_exit_is_not_a_resolution`.
- **9 (medium), threads over 100 comments.** `bind` refuses, before any write, a thread to reply in whose comments
  GitHub cut at 100 (`hasNextPage`), since an earlier reply could be unseen; a thread only resolved is unaffected.
  Refusal chosen over paging the comments (one rule, no second query shape). Test:
  `test_a_thread_with_unread_comments_is_refused_before_any_reply`.
- Docs: `pr_feedback.py` docstring, `speckit.pr.review-feedback.md` step 7.2 (6,486 B), PR and Project
  `## Unreleased` entries and the PR Migration line.

Tests after the fixes (uv Python 3.11): pr 45 OK; project 35 OK; `smoke_project_init.py` and `--shell pwsh` ok
(Windows).
