# Illustrate dependency plan

Scope draws its implementation dependency plan with Sanduq Illustrate (`illustrate >=2.2.1`,
installed at `.specify/extensions/illustrate/skill`).

## Dependency-plan handoff

This step is required after publication creates scoped children. There is no reason
to redraw the existing product plan when merely installing this extension.

1. Run `python .specify/extensions/workflow/scripts/scope/scope.py export-plan --apply`.
   It writes `<scope-artifact-directory>/scope-dependencies.json` with the computed `waves`
   (`W1`... topological levels of executable issues; scope aggregates and `kind: epic`
   containers excluded), `critical_path` and `cyclic` (issues a cycle left unscheduled), the
   reverse `blocks` data and Project `Blocks` fields, and a draft
   `implementation-plan.mapping.json` (`graph_sha256`, `issue_to_node`).
   It validates the graph before its first write and refuses, writing nothing, on a link to a
   cancelled (closed as not planned) issue (`SCOPE_EXPORT_CANCELLED`), a missing issue
   (`SCOPE_EXPORT_MISSING`), work that depends on an aggregate or epic (`SCOPE_EXPORT_AGGREGATE`),
   an aggregate without its scope approval (`SCOPE_EXPORT_UNAPPROVED`) or a cycle
   (`SCOPE_EXPORT_CYCLE`); remove or correct the named link and run it again. Cancelled issues are
   never written. Its journal, `.specify/scope/runs/plan-export-<n>/`, holds the exact issue-body,
   Project-field and native-dependency before-images; `scope.py cancel plan-export-<n>` prints them.
2. Read `scope-dependencies.json` and the existing `<scope-plan-file>`. Confirm every new leaf
   exists, incoming parent dependencies target the correct leaves, `cyclic` is empty and the
   original use cases and source IDs stay covered.
3. Read `.specify/extensions/illustrate/skill/references/type-index.md`, choose the type (here
   the dependency graph), and read its `type-*.md` (`type-dependency.md`); read `SKILL.md` only
   when the diagram is created outside that recipe. Author
   `<scope-artifact-directory>/implementation-plan.illustrate.html` as a dependency graph
   with one node per entry of `waves`, ranked top to bottom, listing that wave's issues. Respect the type's complexity budget; keep the full issue
   dependency table in `DEPENDENCIES.md` and link it in the caption. Add focused linked
   diagrams for large waves; do not force every issue into an unreadable overview.
   Apply the project theme with `scripts/illustration_theme.py --project-root . apply`.
4. Mark the plan structure in the HTML itself, which acceptance reads back:
   - each wave node's box: `data-plan-node="<wave-id>"`, the `W1`... id from `waves`;
   - each connector between waves that an issue dependency crosses:
     `data-plan-from="<wave-id>" data-plan-to="<wave-id>"`.
   Keep the generated mapping. Only when a large wave is split into linked diagrams, edit
   `issue_to_node` to the new node ids; every dependency must stay a forward path between
   different nodes.
5. Run the acceptance command:

   ```text
   python .specify/extensions/workflow/scripts/scope/accept_plan.py --html <scope-artifact-directory>/implementation-plan.illustrate.html --mapping <scope-artifact-directory>/implementation-plan.mapping.json
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

Older plans: `accept_plan.py --migrate-only` converts a pending marker from the previous
renderer; it prints `PLAN_REGENERATION_REQUIRED`, after which steps 3 to 6 regenerate the plan.
