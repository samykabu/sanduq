# Release process

Sanduq ships in release trains. A train is the set of package versions that completes one phase of
the plan. Packages are not published one by one between trains, except for a fix to consumer data
loss or a broken workflow, which may ship on its own with the same checks.

This page is the checklist for each train. The commands are in
[Contributing](../../CONTRIBUTING.md#prepare-a-release).

## Before the train

- [ ] Every package with changed shipped files has one version bump. `python extensions/scripts/release.py check-bumps` passes.
- [ ] Vendor syncs from sanduq-skills are part of the train. Run the `vendor-update` workflow by hand
  (it has no schedule) and merge its pull request into the train branch; it does not release on its own.
- [ ] Each package changelog and the root [CHANGELOG](../../CHANGELOG.md) describe the change.
- [ ] [Upgrades](upgrades.md) has one migration table for the train, written for a user on the
  previous train.
- [ ] [Compatibility](../reference/compatibility.md) and [prerequisites](prerequisites.md) match
  what CI and the live runs tested.

## Checks

- [ ] CI is green on the release commit, including the install and upgrade smoke jobs.
- [ ] Cumulative upgrade smoke: a project on the previous train's versions upgrades to this train
  with `upgrade.py`, then `workflow.py doctor --project` passes.
- [ ] For an unpublished train, run Quick-start on Claude Code and Codex from clean projects to open
  pull requests using the frozen staged candidate packages. Keep one retained run per host per train.
- [ ] The consumer project upgrades in an isolated worktree and `doctor --project` passes before the
  train is announced.

- [ ] Tear down what each live run created: delete its run repository and close or delete its
  GitHub Project board once the redacted evidence is attached to the release, or record why one is
  kept and until when. Name run repositories `sanduq-live-<date>-<host>` so leftovers are easy to
  find. The train is not finished while an unrecorded run repository or board remains.

A host without a live run in this train is listed as untested for this train in
[compatibility](../reference/compatibility.md). Do not carry a previous train's result forward as
this train's.

## Evidence

- [ ] Prepare the redacted per-host transcripts, lifecycle records, installation evidence and hashes
  before publication, and attach them as release assets during publication. Include `doctor` output
  and `lifecycle.jsonl`, with no tokens, user names, private repository names or local paths, and
  record each asset's SHA-256.
- [ ] The compatibility page links each "Tested" cell to that asset.

## Cost and scope record

Record these for every train, in the release notes and the root CHANGELOG entry:

- [ ] Agent cost: USD and wall time for the work that produced the train, and for each live run, by host.
- [ ] Code paths touched: the packages and the main source folders changed.
- [ ] Open consumer-reported data-loss or broken-workflow issues, each with an owner decision.

## Publish

- [ ] Both actual host runs, local qualification, independent review, prepared redacted assets,
  upgrade smoke, isolated-consumer doctor and the other maintainer checks must pass before the train
  is marked ready. Ready authorizes automatic publication once the required CI, including its Windows
  legs, passes on the exact release commit on `main`. The release workflow may obtain that CI after
  the train is marked ready; passing exact-commit CI remains required before publication.
- [ ] Run the release workflow. It publishes immutable assets and then promotes the catalogs.
- [ ] After publication, acquire the immutable assets through the supported released-package
  installation path and compare their member set and content hashes with the tested candidate
  inventory, recording archive hashes separately because ZIP wrappers may differ across platforms.
- [ ] Announce the train only after this verification and catalog promotion; payload differences or
  failed release transport remain pending and require correction and affected validation.

How the release starts on its own: every successful `ci` run on `main` from a push, the nightly
schedule or a person's dispatch triggers `release-extensions.yml` through `workflow_run`. The release
needs a `ci` run with the Windows legs on the same commit (push runs skip them); when there is none, it
dispatches `ci.yml` on `main` and stops with a notice. GitHub starts no `workflow_run` from a run that
`GITHUB_TOKEN` caused, so that dispatched run ends with a `release-trigger` job, which dispatches the
release when the run passes. That release often reaches its gate while the `ci` run is still
finishing, so the job passes the run's id (`ci_run_id`) and the gate counts that run once every other
job in it has passed. The `release-trigger` job runs only for a `workflow_dispatch` by
`github-actions[bot]` on `main`, so each `ci` run on a commit starts the release once, and pull
requests and forks never start it. Release runs share one concurrency group and wait for each other,
and `release.py publish` skips a tag that already exists after checking its bytes. If a release
still stalls, run the release workflow by hand.
- [ ] Wait for the catalog. The promoted catalog reaches `main` through a pull request that merges
  itself once lint passes, so for a few minutes after the assets are published the catalog still
  serves the previous versions (about 11 minutes on 2026-10-27, with the previous license shown). A
  `specify extension add` in that window installs the previous version. Check
  `specify extension list` after installing, and announce the train only after the pull request has
  merged.
