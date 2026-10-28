# Native versus external task routing (October 2026)

PH-05-T07, run on 2026-10-28 with Workflow 2.0.2. Raw evidence, redacted: [`native-routing-2026-10/raw/`](native-routing-2026-10/raw/).

**Question.** With Workflow 2.0.2, what does the same small feature cost, how long does it take, and how many
attempts does it need when its tasks are done (a) by the host session itself, (b) by a native host subagent on
the route's pinned model, or (c) by an external harness started through the delegate-task driver? And do the two
required live fixtures, one on Claude Code and one on Codex, each finish a feature with one task native and one
task external, with the ledger saying so?

**Answer from this run.** All eight runs were valid and every PR passed its own tests and all 13 held-out tests,
so the routes made no difference to the result on this feature. Native routing cost about the same as
in-session work (median 4.79 against 4.41 USD) and had the shortest model time (589 s against 726 s). External
routing cost the most (5.66 USD) and took the longest (992 s); its driver runs added 1.13 to 1.33 USD on top of
the host. With n = 2 per arm the ranges overlap in every column, so this sample does not show a reliable
difference between the arms. The arms also differ in more than routing: in-session tasks ran on the session
model, native and external tasks on the standard-tier model. Both fixtures finished with T001 external and
T002 native, and each ledger records both routes.

## Method

Scripts, issue text, held-out tests and per-run rows are in [`raw/`](native-routing-2026-10/raw/). Local paths in
them are replaced with `<sandbox>` and `~`.

- **Repository.** Private sandbox `samykabu/sanduq-sandbox-ph04`, package `textkit` (only `slugify` on `main`).
  [`tools/prepare-base.sh`](native-routing-2026-10/raw/tools/prepare-base.sh) upgraded a fresh clone of `main` to
  the released Workflow 2.0.2, ran `doctor --project` and pushed it as the new `main`. Spec Kit 1.1.3 was first
  on `PATH`; see Limits for the Codex fixture.
- **Install.** The PH-04 install: QA and User Manual selected, advisory gate, Claude Code and Codex hosts.
- **Hosts.** Claude Code 2.1.312 with its default model `claude-opus-5-5` for seven runs. Codex CLI 0.163.0 with
  `gpt-6.1-sol` (reasoning high, subscription) for `fx-codex`. Native and external tasks run on the standard-tier
  model: `sonnet` on Claude Code, `gpt-6-sol` on Codex.
- **Feature.** One issue text, filed once per run ([`issue.md`](native-routing-2026-10/raw/issue.md)): add
  `initials` and `squeeze`, two independent functions and subcommands. The fixtures got one extra paragraph
  asking Plan for at least two separately testable tasks.
- **Tier.** Lite for every run. The continue prompt approves the proposed score and caps it at 3.
- **Per run.** [`tools/setup-run.sh`](native-routing-2026-10/raw/tools/setup-run.sh) makes a fresh clone, writes
  the arm's delegation block ([`tools/policy.py`](native-routing-2026-10/raw/tools/policy.py)), re-renders the role
  files, installs the delegate-task driver when delegation is on, runs `doctor --project` and commits the policy.
  [`tools/checkroute.py`](native-routing-2026-10/raw/tools/checkroute.py) records the route each task should take.
- **Prompts.** `/speckit-workflow-scope N`, then the PH-04 continue prompt through the PR stage (do not merge),
  plus one sentence for every arm: "Do not edit .specify/workflow.yml; run each task on the route its claim
  records." Clarify questions were answered with the recommended option by
  [`tools/answer.sh`](native-routing-2026-10/raw/tools/answer.sh).
- **Isolation.** No user-level instructions reached a measured session. Codex ran with its own `CODEX_HOME`
  per run ([`tools/codex-home.py`](native-routing-2026-10/raw/tools/codex-home.py)): login, model settings and
  hooks only, with user skills, plugins and apps off. Claude Code ran with `--setting-sources project,local`
  from a folder with no user `CLAUDE.md` above it. Both were checked without a model call.
- **Order.** One run at a time: `fx-codex`, `fx-claude`, then `a1`, `b1`, `c1`, then `c2`, `b2`, `a2`.

### Arms

| Arm | Runs | Delegation | Expected task route |
| --- | --- | --- | --- |
| (a) in-session | a1, a2 | off | No route; the host does every stage and task |
| (b) native | b1, b2 | on | Tasks and discovery stages `native` / `native-first` on `sonnet` |
| (c) external | c1, c2 | on, native off for implementation, `qa_author`, `qa_collect` and documentation | Every non-review task and Verify `external` / `native-unsupported:work-type-disabled`, `claude` harness on `sonnet`. Review and discovery stages stay native |
| Claude fixture | fx-claude | on, plus an override for T001 | T001 `external` / `native-unsupported:model-pin`; later tasks `native` |
| Codex fixture | fx-codex | the same, host Codex | T001 `external` on the `codex` harness; later tasks native through `.codex/agents/sanduq-worker.toml` |

Arms (b) and (c) differ only in where implementation tasks run. Discovery stages route native-first in both.

### Measures

- **USD.** Claude Code `total_cost_usd` over the run's sessions (this includes native subagents) plus the
  `cost_usd` of every external driver result. Codex is subscription-billed, so only tokens are recorded.
- **Model time.** Sum of `duration_ms` (Codex: session end minus start). **Elapsed**: first session start to last
  end, including the answer turnaround.
- **Attempts.** Rows in the feature's `delegations.json`, stages and tasks together. Arm (a) has no ledger.
- **Rejected completions.** `rejected-completion` events in `lifecycle.jsonl`.
- **Held-out tests.** [`tools/postmerge.sh`](native-routing-2026-10/raw/tools/postmerge.sh): a fresh clone merges
  the PR head with `main` locally and runs the PR's own suite plus the 13 held-out tests
  ([`heldout/test_heldout_t07.py`](native-routing-2026-10/raw/heldout/test_heldout_t07.py)), written from the issue
  text and checked against a reference implementation (13 of 13 pass).

[`tools/collect.py`](native-routing-2026-10/raw/tools/collect.py) builds one row per run
([`rows/`](native-routing-2026-10/raw/rows/)) and [`tools/report.py`](native-routing-2026-10/raw/tools/report.py)
builds the tables below.

## Validity

[`tools/validate.py`](native-routing-2026-10/raw/tools/validate.py) runs after each collection. A run is invalid
when:

- (a) `.specify/workflow.yml` differs from the setup commit;
- (b) a task attempt's route differs from the route the setup commit predicts for its work type;
- (c) arm (c) has an adopted, in-session or substituted attempt, or no external task attempt;
- (d) a fixture lacks one external and one native task attempt;
- (e) arm (b) has no native task attempt, or a delegation arm has no task attempt at all.

All eight runs are **valid**. Task attempts by route: b1 5 native, b2 9 native, c1 7 external, c2 6 external,
fx-claude and fx-codex 1 external (T001) and 1 native (T002) each.

## Results

| Run | Arm | Issue | PR | Sessions | USD host | USD external | USD total | Model s | Elapsed s | Tool calls | Attempts (native / external) | Rejected completions | Held-out failed / ran |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| a1 | in-session | #98 | #109 | 3 | 5.71 | 0.00 | 5.71 | 899 | 908 | 145 | 0 / 0 | 0 | 0 / 13 |
| a2 | in-session | #99 | #114 | 2 | 3.10 | 0.00 | 3.10 | 554 | 559 | 76 | 0 / 0 | 0 | 0 / 13 |
| b1 | native | #100 | #110 | 2 | 3.51 | 0.00 | 3.51 | 625 | 630 | 94 | 10 / 0 | 1 | 0 / 13 |
| b2 | native | #101 | #113 | 3 | 6.07 | 0.00 | 6.07 | 553 | 935 | 167 | 14 / 0 | 2 | 0 / 13 |
| c1 | external | #102 | #111 | 3 | 5.00 | 1.33 | 6.32 | 1,087 | 1,096 | 117 | 4 / 8 | 2 | 0 / 13 |
| c2 | external | #103 | #112 | 2 | 3.86 | 1.13 | 5.00 | 898 | 905 | 98 | 4 / 7 | 1 | 0 / 13 |
| fx-claude | fixture | #104 | #108 | 2 | 4.51 | 0.20 | 4.71 | 765 | 769 | 113 | 6 / 1 | 1 | 0 / 13 |
| fx-codex | fixture | #106 | #107 | 2 | n/a | n/a | n/a | 1,802 | 1,804 | 111 | 6 / 1 | 1 | 0 / 13 |

Issue and PR numbers are in the private sandbox. Every PR also passed its own suite after the local merge.

| Arm | n | USD total, median (range) | Model s, median (range) | Elapsed s, median | Attempts, median | Rejected completions | Held-out failures |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: |
| in-session | 2 | 4.41 (3.10 to 5.71) | 726 (554 to 899) | 734 | 0 | 0 | 0 |
| native | 2 | 4.79 (3.51 to 6.07) | 589 (553 to 625) | 782 | 12 | 3 | 0 |
| external | 2 | 5.66 (5.00 to 6.32) | 992 (898 to 1,087) | 1,000 | 12 | 3 | 0 |

The external driver runs of arm (c) used 2,498,053 input and 19,378 output tokens in all.

**Rejected completions.** Six of the seven in the delegation runs were `DELEGATION_STAGE_NOT_VERIFIED` on Scope
or Clarify: the host tried to complete a native-first stage before it had recorded the native attempt, then
recorded it and completed. The seventh, in `fx-codex`, was `INPUT_MANIFEST_REQUIRED` at Execute. The in-session
runs had none.

## Pilots and what they found

Three earlier batches and one stalled run were pilots, not measurements. Their raw files are not published.
Each surfaced a defect that was fixed and released before the measured batch.

1. **Workflow 1.25.0, a stalled Codex fixture.** A Clarify comment that mentioned SD1 made Scope stale: the
   decision fingerprint hashed the diagnostic value `unparsed`, and Scope's own comments were not recorded.
   Fixed in Workflow 1.25.1 ([#148](https://github.com/samykabu/sanduq/pull/148)).
2. **Workflow 1.25.1 pilot** (a1, b1, c1 and both fixtures). An external route could be replaced by in-session
   work plus `adopt`: c1 adopted T001 to T005 and had no external attempt. Fixed in Workflow 2.0.1
   ([#152](https://github.com/samykabu/sanduq/pull/152)).
3. **Workflow 2.0.1 pilot.** In `fx-codex` the agent edited `.specify/workflow.yml` during a claim to turn an
   external route native. Fixed in Workflow 2.0.2 ([#154](https://github.com/samykabu/sanduq/pull/154)): a claim
   now pins its delegation policy.
4. **Harness.** The owner's global agent instructions reached measured Codex sessions (the agent cited one of
   them to change a route), and in a first isolated home Codex fetched curated plugins. Fixed in the harness: each
   run gets its own `CODEX_HOME` with plugins and apps off. One Codex Scope session on 2.0.2 ran under the first
   isolated home; it is a pilot as well.

**Observation for PH-05-T08.** After a pilot batch was stopped on Windows with `taskkill /T`, child processes of
the run (a `bash` process and a Claude Code session) kept running. This is the kind of orphaned process PH-05-T08
is about. It was not traced to the delegate-task driver, and no conclusion about the driver is drawn here.

## Limits

- n = 2 per arm, one feature, one machine, one sandbox. Medians and ranges are reported; no significance is
  claimed, and every arm's range overlaps the others.
- Arm (a) ran its tasks on the session model (`claude-opus-5-5`); arms (b) and (c) ran them on `sonnet`. That is
  the product's real difference between delegation off and on, and it is not corrected for.
- Discovery stages run native-first in arms (b) and (c), so those arms differ only in their tasks.
- The feature is small and fully specified. No arm had a held-out failure, which leaves no room to show a
  quality difference.
- Lite tier only. Standard tier was not measured.
- `fx-codex` has no USD figure: Codex is billed by subscription. Its native agents' tokens were not found in the
  isolated home (`fidelity: unavailable` in its row); the external T001 tokens were.
- Spec Kit: every clone's `.specify/init-options.json` records 1.1.3, except `fx-codex`. Its host switch to
  Codex ran `specify integration use codex`, which recorded 1.2.3, so a newer Spec Kit on the machine ran that
  one command although 1.1.3 was first on `PATH`.
- Elapsed time includes the automatic answer turnaround. In b2 it is about six minutes above model time.
- Post-merge is a local candidate merge with `main`, not a GitHub merge. The PRs were left open.

## Spend

| Set | USD |
| --- | ---: |
| Measured set (8 runs; [`tools/spend.py`](native-routing-2026-10/raw/tools/spend.py)) | 34.43 |
| Workflow 1.25.1 pilot | 14.39 |
| Workflow 2.0.1 pilot | 10.58 |
| **Total** | **59.40** |

The budget cap was 160 USD. Codex sessions are subscription-billed and not in these figures.

## Reproduce

From Git Bash in the sandbox folder, with the scripts in [`raw/tools/`](native-routing-2026-10/raw/tools/) (put
your own paths back where they read `<sandbox>`; `redact.py` is not published):

```bash
bash tools/prepare-base.sh 2.0.2 release --push   # upgrade the sandbox main to the released Workflow
bash tools/file-issues.sh                          # one issue per run
bash tools/t07.sh 2.0.2 fx-codex
bash tools/t07.sh 2.0.2 fx-claude
bash tools/t07.sh 2.0.2 a1 b1 c1
bash tools/t07.sh 2.0.2 c2 b2 a2
python tools/report.py > results.md
python tools/spend.py | tail -1
```

`t07.sh` sets up each run, runs its sessions, collects the row, runs the held-out tests and validates the run.
It stops the batch at the first invalid run.
