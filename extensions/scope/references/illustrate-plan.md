# Illustrate dependency plan and clarification images

Scope draws its implementation dependency plan and its clarification diagrams with
Sanduq Illustrate (`illustrate >=2.2.1`, installed at `.specify/extensions/illustrate/skill`).

## Dependency-plan handoff

This step is required after publication creates scoped children. There is no reason
to redraw the existing product plan when merely installing this extension.

1. Run `python .specify/extensions/scope/scripts/scope.py export-plan --apply`.
   Read `<scope-artifact-directory>/scope-dependencies.json`, `issues.json`,
   `.issue-map.json`, and the existing `<scope-plan-file>`.
2. Confirm every new leaf exists, all incoming parent dependencies now target the
   correct leaves, no executable dependency points to a scope aggregate, and no
   cycle exists. Recalculate topological waves and the critical path from executable
   nodes, excluding both scope aggregates and existing `kind: epic` containers.
   Preserve coverage of the original use cases and source IDs. Update reverse
   `blocks` data and Project `Blocks` fields alongside `Blocked by`.
3. Load the installed Illustrate skill and its dependency-graph type
   (`references/type-dependency.md`). Author
   `<scope-artifact-directory>/implementation-plan.illustrate.html` as a dependency graph
   whose nodes are implementation waves, ranked top to bottom, with clearly identified
   issue groups in each node. Respect the type's complexity budget; keep the full issue
   dependency table in `DEPENDENCIES.md` and link it in the caption. Add focused linked
   diagrams for large waves; do not force every issue into an unreadable overview.
   Apply the project theme with `scripts/illustration_theme.py --project-root . apply`.
4. Mark the plan structure in the HTML itself, which acceptance reads back:
   - each wave node's box: `data-plan-node="<wave-id>"` (unique);
   - each dependency connector: `data-plan-from="<wave-id>" data-plan-to="<wave-id>"`.
   Write `<scope-artifact-directory>/implementation-plan.mapping.json` with
   `graph_sha256` (SHA-256 of `scope-dependencies.json`) and `issue_to_node`, mapping
   every executable GitHub issue number string to its wave ID. Do not map aggregate or
   epic containers. Every dependency must be a forward path between different waves.
5. Run the acceptance command:

   ```text
   python .specify/extensions/scope/scripts/accept_plan.py --html <scope-artifact-directory>/implementation-plan.illustrate.html --mapping <scope-artifact-directory>/implementation-plan.mapping.json
   ```

   Pass `--illustrate <skill-dir>` when Illustrate is installed elsewhere. The command:
   - checks issue coverage, dependency reachability and acyclicity against the marked HTML;
   - runs Illustrate's `self_check.py` and `verify-geometry.py`, then `export_diagram.py`
     to `<scope-artifact-directory>/implementation-plan.svg` and `.png`;
   - renders the HTML in headless Chromium at 1280x800, 1440x900 and 1920x1080 and fails
     on script errors, an invisible diagram, invisible or overlapping wave nodes, nodes
     outside the diagram, or zero-length connectors; screenshots go to
     `<scope-artifact-directory>/plan-review/`;
   - records graph, candidate, delivered HTML, export and screenshot hashes in
     `scope-plan-receipt.json`, and refuses to accept if the graph or candidate changed
     during the run.

   Any failure writes `.specify/scope/plan-failed-receipt.json`, keeps the pending marker
   and leaves the previous plan file untouched. Fix the diagram and rerun. PNG export and
   the browser check need Playwright with Chromium
   (`pip install playwright && playwright install chromium`); without them acceptance
   fails closed with that instruction.
6. Unmanaged projects: success copies the plan to `<scope-plan-file>` and the
   compatibility copy, and clears the pending marker. Managed projects keep the marker
   until image review: inspect the actual screenshots listed in the receipt, write review
   JSON with `html_sha256`, `reviewer`, `passed: true`, `findings: []` and `screenshots`
   (`path` relative to the project and `sha256` for each inspected image), then rerun the
   same command with `--review <review.json>`. Do not rerender between review and
   acceptance; changed bytes are rejected.
7. Review the diff and include plan data, candidate HTML, exports and receipt with the
   scope operation handoff. Never claim completed dependency-plan maintenance if a check
   failed, sources changed, or the pending marker remains.

Resolve `<scope-artifact-directory>` and `<scope-plan-file>` from
`scripts/workflow_policy.py paths(root)`: managed defaults are
`.specify/scope/github` and `docs/workflow/implementation-plan.html`. Project policy
may override both. Unmanaged defaults retain Design/UI-Spec paths. Never copy a
project-specific path into another project's configuration.

### Command-line changes in 1.6.0

`--html` replaces `--spec`, and `--illustrate` (optional) replaces the previous
renderer's CLI path. `--spec` remains an alias of `--html`, and the old renderer flag is
accepted and ignored with a warning, until Scope 1.7.0. `--mapping` and `--review` are
unchanged. `--migrate-only` converts a pending plan without accepting anything.

### Pending plans from Scope 1.5.x

A pending marker without `renderer: illustrate` came from the previous renderer. Every
`accept_plan.py` run (or `--migrate-only`) converts it in place: the marker stays pending,
records the original under `migrated_from`, and prints `PLAN_REGENERATION_REQUIRED` with
the issue number. An unreviewed receipt from that flow is kept as
`scope-plan-receipt.legacy.json` and can never be reviewed as Illustrate evidence. A
`.json` candidate passed to `--spec` is refused with the same regeneration message.
Regenerate the plan with steps 3 to 6. Historical receipts and plan files are not edited.

## Clarification images on GitHub

Decision: a clarification question embeds an Illustrate PNG through a commit-pinned
GitHub blob URL, the PR extension's approach
(`extensions/pr/references/pr-image-embedding.md`), and falls back to text when that
cannot be proven.

- Draw with Illustrate, export the PNG (`export_diagram.py <file> --png-only`), commit it
  and push it. In the analysis JSON give the question
  `diagram_image: {"path": "<project-relative .png>", "alt": "<description>"}` and
  `diagram_text`, a text version such as a dependency list. Both are required together.
- At publish time the runtime reads the local `HEAD` commit and the file's git blob hash,
  then asks the contents API for that path at that commit. Only when GitHub returns the
  same blob does it embed
  `![alt](https://github.com/<owner>/<repo>/blob/<commit>/<path>?raw=true)`.
  This URL loads for every reader who can see the repository, private repositories
  included. `raw.githubusercontent.com` URLs are never generated, and legacy
  `diagram_markdown` using one is rejected.
- If the file is missing, not a PNG, outside the project, not pushed at that commit, or
  different on GitHub, the comment carries `diagram_text` under a note with the exact
  reason, and the publish result lists it under `image_fallbacks`. Publishing never waits
  for an image. Push the file and rerun before posting if the picture matters.
- Managed projects do not accept Mermaid `diagram` source in questions
  (`ILLUSTRATE_REQUIRED`); use `diagram_image` with `diagram_text`.
- Do not upload private material to public hosts, put tokens in URLs, or use data URLs.
