# Stage reference: pr

Read for `stage: pr` and for the **finalize** entry point and its post-merge follow-up.

## Entry point

**finalize**: run the stage loop with `--finalize`. It authorizes PR generation within the
user's requested scope, not merge or deploy. Finish prerequisite stages before creating a PR.
If the bound PR is already merged, use the post-merge verification below; never create a
replacement PR or claim the old readiness receipt verifies new source.

## Required work and evidence

Run the PR extension, include every relevant visual inline, verify them, and reuse an existing
PR. Receipt: `pr_url`, `images_verified: true`, `image_verification: api` (rendered `body_html`
plus the contents API per pinned commit, both hosts) or `browser` (those checks plus loading in an
authenticated browser, when the host has a browser tool), and actual evidence; when no visuals
apply, record that inventory result. In lean mode the coordinator owns PR mechanics,
including reuse of unchanged evidence, with no model dispatch; claim tokens, publication
evidence, human decisions and project checks stay enforced.

Publish with `python .specify/extensions/pr/scripts/pr_publish.py --feature specs/<feature>
--explained docs/<slug>/<Feature>-Explained.md`: it writes the exact UTF-8/LF body, lints it with
`execution_tools.pr_lint` against the bound issue and prerequisites from `scope-source.json` (not
PR prose), refuses on findings (exit 1), and prints `pr_url`, `pr_body_file`, `pr_lint_file`,
`pr_body_sha256` and `evidence`; copy them into the receipt as printed. Completion recomputes the
lint; the guard hook refuses `gh pr create|edit --body-file` without a matching sibling
`.lint.json`. Keep the actual publication evidence and body bytes.

For source-only PRs, write the affected features to `.specify/workflow/pr-features.json` as
`{"features": ["specs/001-example"]}` and include it in the PR. CI uses it in addition to the
changed feature directories, never instead. Refresh readiness evidence after source edits.

## Order

Code and affected tests, the independent review, documentation and portable evidence, and
Ready come first. Then freeze the candidate, run the indexed and clean-candidate gates below,
publish or reuse one PR with `pr_publish.py`, `complete` the claim, run the claim's
`project-sync` (in-review), and check the exact final PR head. Syncing before `complete` is
also safe: a status-only write does not touch receipts. On a stale receipt use the bounded
recovery in [dispatcher-operations.md](dispatcher-operations.md#finalization-order)
(`sync-amend`, `amend`, scoped revalidation) before dispatching another semantic agent.

## Publication preflight and post-merge verification

Before the last Verify/Review/Ready pass, prepare portable evidence: prefer
`specs/<feature>/evidence/` for reviewed, credential-free receipts, keep the original failed
attempts and separate not-run work. Inventory every receipt dependency, including selected QA
and manual state. Inspect ignored evidence one file at a time before staging; never force-add
the whole artifacts folder. New tracked files can change the source inventory and need
revalidation.

After staging, run `ci_gate.py --feature specs/<feature> --base-ref <current-target-sha>
--check-index`; it reports missing index entries and unstaged dependencies, but stages nothing
and certifies no test run. Then run the gate in a clean checkout of the exact candidate commit.
Run graph updates before final audits (`graphify-out/` is excluded from implicit documentation
inputs; declared graph outputs stay hashed). Re-fetch the target before publication; if merging
it changes source or build inputs, rerun the affected checks and readiness on the combined tree.
Require the remote workflow-evidence check on the exact final PR head and recommend branch
protection for it, reporting missing enforcement without changing it. The CI template is
PR-only; push workflows need an explicit feature mapping and comparison base. A promotion PR
with pre-adoption features needs an explicit legacy-adoption decision per missing checkpoint;
never synthesize receipts or skip those features.

When the user reports a merge, read the bound PR through GitHub: repository, target, merged
flag, final head and merge SHA, and checks on both SHAs. Verify deployment statuses and actual
rollout separately; an image build or docs preview is not live acceptance. Keep pending,
failed, cancelled, skipped and absent checks distinct. Save a post-merge report in the feature
workflow folder with URLs, timestamps, failures and follow-ups. Keep original stage receipts;
`pr_open` is the last dispatch state, not proof the PR is open or verified. Never infer merge or
deploy authorization from Finalize, or claim completion while required checks fail.

After verified delivery, run the post-merge Memory handoff in
[memory-lifecycle.md](memory-lifecycle.md) and dispatch its next action. A report-only
follow-up PR stops after reporting: never archive another feature or refresh dependency reports
again. A returned Memory action is pending work, not proof of an archive.
