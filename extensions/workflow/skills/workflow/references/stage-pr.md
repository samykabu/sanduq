# Stage reference: pr

Loaded when `claim` returns `stage: pr`, and read for the **finalize** entry point
and its post-merge follow-up.

## Required work and evidence

Run the PR extension, include every relevant visual inline, verify authenticated
loading, and reuse an existing PR. Receipt needs `pr_url`, `images_verified: true`
and actual evidence; if no visuals apply record that explicit inventory result.

For source-only PRs, write the explicit affected feature list to
`.specify/workflow/pr-features.json` as `{"features": ["specs/001-example"]}` and
include that mapping change in the PR. CI consumes it in addition to all changed
feature directories, never instead of them. Refresh the relevant readiness evidence
after source edits; an old mapping does not make stale test evidence current.

## Publication preflight and post-merge verification

Before the last Verify/Review/Ready pass, prepare portable evidence. Prefer
`specs/<feature>/evidence/` for reviewed, credential-free test receipts; preserve
the original failed attempts and separate not-run work. Inventory every receipt
dependency, including selected QA/manual state and outputs. Inspect ignored
evidence individually before staging it; never force-add the entire artifacts folder.
Packaging new tracked files can change the source inventory and requires revalidation.

After staging the intended change, run `ci_gate.py --feature specs/<feature>
--base-ref <current-target-sha> --check-index`. This reports missing index entries
and unstaged dependencies. It does not stage files or certify test execution.
Then run the gate in a clean checkout of the exact candidate commit. Local ignored
files, unstaged content and checkout conversions must not supply hidden evidence.
Run graph updates before final audits; derived `graphify-out/` files are excluded
from implicit documentation inputs, but explicitly declared graph outputs remain hashed.

Re-fetch the target before publication. If merging the target changes source or
build/test inputs, rerun the affected checks and readiness on that combined tree.
Do not copy old fingerprints forward to turn a stale receipt green. Require the
remote workflow-evidence check on the exact final PR head. Recommend required
branch protection for this check; report missing enforcement without changing it
without authorization. The supplied CI template is PR-only: push workflows need
an explicit affected-feature mapping and correct comparison base, not a blanket
scan of legacy feature directories with no managed checkpoint.
Promotion PRs can also include pre-adoption feature history. Report each missing
checkpoint and require an explicit legacy-adoption decision; do not synthesize
receipts or silently skip those features to make promotion pass.

When the user reports a merge, read the actual bound PR through GitHub, verify
its repository, target, merged flag, final head and merge SHA, and inspect checks
on both SHAs. Fetch deployment statuses and verify actual rollout separately when
applicable. A passing image build or documentation preview is not live application
acceptance. Pending, failed, cancelled, skipped and absent checks remain distinct.
Save a post-merge report in the feature workflow folder with URLs, timestamps,
failures and follow-ups. Preserve original stage receipts. `pr_open` is the runtime's
last dispatch state, not a claim that a merged PR is still open or fully verified;
the post-merge report records external delivery state. Never infer merge/deploy
authorization from Finalize, or claim completion while required checks are failing.

## Managed overlay's finalize entry point

**finalize**: run the same loop with `--finalize`. This authorizes PR generation within the
user's requested scope, not merge/deploy. Finish prerequisite stages before creating a PR.
If the bound PR is already merged, use the post-merge verification protocol above;
do not create a replacement PR or claim the old readiness receipt verifies new source.
