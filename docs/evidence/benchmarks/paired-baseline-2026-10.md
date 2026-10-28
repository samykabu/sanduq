# Paired baseline: plain host versus Sanduq managed (October 2026)

Content for `docs/evidence/benchmarks/paired-baseline-2026-10.md`. PH-04-T08, run on 2026-10-28.

**Question.** For the same small issue, what does Sanduq's managed lifecycle cost over the plain host doing
the issue and opening a PR, and does it buy fewer defects?

**Answer from this run.** On these four small issues the managed arm cost **18x (lite) to 46x (standard)**
the USD of the plain arm and took **16x to 43x** the host-reported model time. Neither arm had a post-merge
defect on the held-out tests (0 of 68 test runs failed), so this sample shows no quality gain to set against
the cost. The sample is too small and too easy to show one; see Limits.

## Method

- **Host.** Claude Code 2.1.312, model `claude-opus-5-5`, both arms. Only Claude Code was used for T08 to stay
  inside the 100 USD budget; Codex was used only for T06.
- **Repository.** Private sandbox `samykabu/sanduq-sandbox-ph04`: a small Python package (`textkit`) with a
  `slugify` command and three unit tests.
- **Issues.** Two task types, each filed four times with an identical body, so no run could reuse another's
  issue, branch or feature directory:
  - *lite*: "Add a `reverse` command" (one function, one subcommand, tests, README line); issues #3, #5, #7, #9.
  - *standard*: "Add a `title` command" (headline title case with small-word and hyphen rules, `--file`, stdin,
    two error exits, tests, README line); issues #4, #6, #8, #10.
- **Plain arm.** A separate clone checked out at the seed commit, with no Spec Kit or Sanduq files. One
  headless command per issue (prompt in the bundle, `prompts/plain.txt`): implement issue #N on branch
  `issue-N`, add unit tests, run the suite until it passes, commit only changed files, push, open a PR with
  "Closes #N", do not merge.
- **Managed arm.** Two separate clones of `main` with the T06 install: Workflow 1.21.0 train, Spec Kit 1.1.3,
  QA and User Manual on, advisory gate, `profiles.enabled: true`, Progress 1.7.0, Superpowers Bridge with
  Sanduq aliases. Commands: `/speckit-workflow-scope N`, then `/speckit-workflow-continue #N` with owner
  approval at the proposed effort score, through the PR stage. When the run stopped for owner input, I answered
  on GitHub with the recommended option (`C1Qn: A`, `SD1: A`) and ran `continue` again, with standing approval
  for `--confirm-invalidation`. Every session is counted.
- **Order.** Planned alternation per tier (round 1: plain lite, managed lite, managed standard, plain standard;
  round 2: managed lite, plain lite, plain standard, managed standard). Plain runs took about a minute, so they
  were run while managed runs were in progress; the "Order" column gives the actual start order. Runs
  overlapped in time on one machine, which affects wall time a little and USD not at all.
- **Runner.** `claude -p "<cmd>" --output-format stream-json --verbose --permission-mode bypassPermissions
  --setting-sources project,local`, with `CLAUDE*` variables unset (`tools/run-claude.sh`).
- **Measures.**
  - *USD*: sum of Claude Code's reported `total_cost_usd` over the run's sessions.
  - *Model time*: sum of the sessions' `duration_ms`. *Elapsed*: first session start to last session end,
    including the time I took to answer questions.
  - *Tool calls*: count of `tool_use` blocks in the transcripts.
  - *Rejected completions*: `rejected-completion` events in the feature's `lifecycle.jsonl` (managed only;
    the plain arm has no equivalent).
  - *Post-merge defects*: I wrote held-out acceptance tests from the issue text before any run (5 for lite, 12
    for standard; `held-out-tests/`) and checked them against my own reference implementation (17 of 17 pass).
    For each PR, a fresh LF clone merges the PR head with `main` locally and runs the PR's own suite plus the
    held-out file. The PRs were not merged on GitHub, because the four copies of each task conflict with each
    other. Failures are counted per test.
  - One held-out test was corrected during the run: the stdin test first swapped `sys.stdin` for a `StringIO`,
    which errored on a valid implementation that reads `sys.stdin.buffer` (managed #8, which decodes stdin
    strictly as its Clarify answer chose). I changed that test to run the CLI as a subprocess, re-checked it
    against the reference, and re-ran it for all four standard PRs.

## Results

| Order | Arm | Tier | Issue | PR | Sessions | USD | Model time (s) | Elapsed incl. owner waits (s) | Tool calls | Rejected completions | Held-out failures / tests |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | plain | lite | #3 | #11 | 1 | 0.27 | 50 | 56 | 6 | n/a | 0/5 |
| 2 | managed | lite | #7 | #23 | 2 | 4.75 | 685 | 698 | 118 | 1 | 0/5 |
| 3 | managed | standard | #8 | #54 | 4 | 12.53 | 2,362 | 2,427 | 287 | 2 | 0/12 |
| 4 | plain | standard | #4 | #12 | 1 | 0.26 | 53 | 54 | 3 | n/a | 0/12 |
| 5 | plain | lite | #5 | #36 | 1 | 0.23 | 40 | 41 | 5 | n/a | 0/5 |
| 6 | plain | standard | #6 | #37 | 1 | 0.28 | 47 | 48 | 4 | n/a | 0/12 |
| 7 | managed | lite | #9 | #53 | 2 | 4.38 | 800 | 805 | 112 | 0 | 0/5 |
| 8 | managed | standard | #10 | #63 | 4 | 12.53 | 1,936 | 2,615 | 298 | 1 | 0/12 |

The two managed standard runs each cost 12.53 USD by coincidence (0.99 + 1.19 + 4.37 + 5.98 and
0.81 + 1.19 + 3.72 + 6.81).

| Arm | Tier | n | USD, median (range) | Model time s, median (range) | Tool calls, median | Rejected completions | Held-out failures |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| plain | lite | 2 | 0.25 (0.23 to 0.27) | 45 (40 to 50) | 6 | n/a | 0 |
| managed | lite | 2 | 4.57 (4.38 to 4.75) | 742 (685 to 800) | 115 | 1 | 0 |
| plain | standard | 2 | 0.27 (0.26 to 0.28) | 50 (47 to 53) | 4 | n/a | 0 |
| managed | standard | 2 | 12.53 (12.53 to 12.53) | 2,149 (1,936 to 2,362) | 292 | 3 | 0 |

Ratios of medians, managed over plain: lite 18x USD and 16x model time; standard 46x USD and 43x model time.
All eight PRs also pass their own suites after the local merge.

## What the managed arm spent its time on

- **Owner stops.** Lite: 2 sessions (Scope approval, then continue to PR). Standard: 4 sessions, because each
  feature stopped for Clarify questions and then for the User Manual module map (SD1), since no manual existed
  on `main` yet.
- **Rework after decisions.** Recording SD1 rewrote `workflow/decisions.json`, an input of every receipt, so
  Execute's first completion was rejected (`UPSTREAM_INPUT_CHANGED_DURING_STAGE: .../decisions.json`) in both
  standard runs, and stages were re-recorded. Managed #8 also had an Analyze rejection after a `tasks.md` edit.
- **Process artifacts.** Task sub-issues on the board (4 for the lite #7), QA pages, a User Manual tree,
  two manual workflows and evidence files. The plain PRs changed 4 files each.
- Managed lite #7 had one rejected Plan completion (`EVIDENCE_REQUIRED`).

## Limits

- n = 2 per arm and tier, on one machine and one model. Medians with ranges are reported; no significance is
  claimed.
- The tasks are small and fully specified, and the seed code is tiny. The plain host got both right first
  time, which leaves no room for managed review to catch a defect. A fair quality test needs ambiguous or
  larger issues, or a seeded trap.
- The managed arm ran with QA and User Manual selected (the Quick-start configuration). That adds the QA and
  manual stages and the SD1 stop; a core-only managed run (QA and manual off) was not measured.
- The first standard feature in a repository pays the one-time manual setup (SD1). Both managed standard runs
  started from a `main` without a manual, so both paid it.
- Elapsed time includes my answer turnaround (a few seconds to minutes); model time does not.
- Post-merge is a local candidate merge with `main`, not a GitHub merge, and the held-out tests were written by
  me from the issue text.

## Evidence

`t08-paired-baseline.zip` in the PH-04 release assets: redacted transcript digests for all 16 sessions (tool
calls, assistant messages, final results, usage; tool outputs removed), session start and end stamps, both
issue bodies, the held-out tests, prompts, the post-merge log, the scripts that built this table
(`tools/t08.py`, `tools/analyze.py`, `tools/postmerge.sh`) and `SHA256SUMS`. The full raw transcripts are kept
by the maintainer and are not published, because they contain account and local machine details.
