# Contract 3b — git fields

Version `delegate-task.result.v2`. Normative.

## What is captured

**Before the child starts** and **after it exits**, in the run's `--cwd`:

| Capture | Command | Purpose |
| --- | --- | --- |
| `root` | `git rev-parse --show-toplevel` | normalise a subdirectory cwd to the repo root |
| `head` | `git rev-parse HEAD` | detect a commit |
| `index` | `git diff --cached --raw -z` digest | detect staging |
| `porcelain` | `git -c status.relativePaths=false status --porcelain=v1 -z` | the dirty set |
| `prints` | content hash + index entry per already-dirty path | catch edits to a file that was *already* dirty, which never changes its porcelain line |

Both captures use `-z` and are parsed NUL-safely. A rename or copy record (`R`/`C` in the first
status column) is followed by an extra NUL-separated origin path; the parser consumes it.
Paths are root-relative, so a subdirectory `--cwd` and a repo-root `--cwd` produce comparable
records. Conflicted entries (`UU`, `AA`, `DD`, …) are dirty like any other.

`prints` covers only the baseline-dirty set. A path the run newly dirties already shows up as a
new porcelain record, so fingerprinting the whole repository would cost far more than the case it
covers.

## The fields

| Field | Type | Meaning |
| --- | --- | --- |
| `git_visible_after` | `string[]` \| `null` | The **whole** dirty tree after the run. Contains baseline dirt. Not a delta, not attribution. `null` means git could not answer; `[]` means git ran and the tree is clean. |
| `dirty_paths_changed` | `string[]` \| `null` | **The delta.** Paths whose porcelain record appeared, disappeared or changed, plus baseline-dirty paths whose content or index entry moved. |
| `head_changed` | `bool` \| `null` | HEAD moved during the run window. |
| `index_changed` | `bool` \| `null` | The staged set moved during the run window. |
| `coverage_complete` | `bool` | False when any fingerprint was unreadable or a probe failed. Gates the tri-state below. |
| `read_only_violation` | `true` \| `false` \| `null` | See below. |
| `files_claimed` | `string` \| `null` | What the delegate said it changed, verbatim from the envelope. |
| `files_mismatch` | `bool` \| `null` | Whether the claim disagrees with `dirty_paths_changed`. |

## `read_only_violation` — the tri-state

Only meaningful when the run requested `--sandbox`.

- **`true`** — *a violation signal occurred during the run window.* `dirty_paths_changed` is
  non-empty, or `head_changed`, or `index_changed`.
- **`false`** — *no covered final-state delta was detected.* Never "no writes occurred".
- **`null`** — genuinely unknown: git was unavailable, the cwd is not a repository, a probe timed
  out, or `coverage_complete` is false.

**Collapsing `null` to `false` is forbidden.** That is the false assurance a tripwire must never
give.

### What `false` cannot see

- A write followed by a revert inside the run window.
- Anything matched by `.gitignore`.
- Any write outside the repository.
- A change made by a *different* process during the window.

### What `true` does not mean

It does not mean *the delegate did it*. A concurrent human edit in the same worktree produces the
same signal. `true` is a reason to look, not a verdict of guilt.

## `files_mismatch`

Compares `files_claimed` against **`dirty_paths_changed` only** — never against
`git_visible_after`, which contains baseline dirt and would turn a pre-existing dirty file, or a
concurrent human edit, into an accusation that the delegate lied.

`null` when `coverage_complete` is false or `files_claimed` is absent. Unknown coverage is
reported as unknown, not as agreement.

## `head_changed` — an unattributed integrity signal

A commit inside the run window is treated as **review-required**: a run that would otherwise be
`successful` is forced to `failed` with `status_provenance.primary: "head_moved"`, unless
`--allow-commit` was passed. `index_changed` gates the same way, as `index_moved`.

These gates sit last in the status ladder (rules 10–11 of
[status-precedence.md](status-precedence.md)), so they never mask a real failure — a run that
already failed keeps its own reason. **The movement is recorded in `status_provenance.evidence`
either way**, so it is never lost just because something else went wrong first.

The driver **never** resets, checks out, or cleans anything. It preserves the evidence — before
and after HEAD, the porcelain records, the fingerprint delta — and says so. The commit may have
been the operator's own.

## Non-repository and git-less cases

| Situation | Result |
| --- | --- |
| `git` not on PATH | all git fields `null`, `coverage_complete: false` |
| cwd is not inside a repository | all git fields `null`, `coverage_complete: false` |
| probe exceeded its bound | all git fields `null`, `coverage_complete: false` |
| repository present, tree clean | `git_visible_after: []`, `dirty_paths_changed: []`, `coverage_complete: true` |

In every `null` case `read_only_violation` is `null`, and the printed summary says
*"git could not report — inspect the working tree directly"* rather than implying safety.
