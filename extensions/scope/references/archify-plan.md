# Archify dependency-plan handoff

This step is required after publication creates scoped children. There is no reason
to redraw the existing product plan when merely installing this extension.

1. Run `python .specify/extensions/scope/scripts/scope.py export-plan --apply`.
   Read `Design/UI-Spec/github/scope-dependencies.json`, `issues.json`,
   `.issue-map.json`, and the existing `Design/UI-Spec/implementation-plan.html`.
2. Confirm every new leaf exists, all incoming parent dependencies now target the
   correct leaves, no executable dependency points to a scope aggregate, and no
   cycle exists. Recalculate topological waves and the critical path from executable
   nodes, excluding both scope aggregates and existing `kind: epic` containers.
   Preserve coverage of the original use cases and source IDs. Update reverse
   `blocks` data and Project `Blocks` fields alongside `Blocked by`.
3. Load the installed `$archify` skill. Use its workflow schema/common schema and a
   workflow example. Author `Design/UI-Spec/github/implementation-plan.archify.json`
   as a new workflow v2 candidate. Keep at most 12 primary wave/phase nodes with
   clearly identified issue groups; retain the full issue dependency table in
   `DEPENDENCIES.md` and provide its link. Add focused linked diagrams if needed
   for large wave detail; do not force every issue into an unreadable overview.
   Use stable IDs, original issue links and the real dependency topology.
4. Write a sidecar `Design/UI-Spec/github/implementation-plan.mapping.json` with
   `graph_sha256` (SHA-256 of scope-dependencies.json) and `issue_to_node`, mapping
   every executable GitHub issue number string to its Archify wave node ID. Do not
   map aggregate/epic containers. Every dependency must be represented by a forward
   path between different waves. This is checked before accepting the delivered plan.
   Follow Archify's candidate-first authoring, update-awareness and validation
   procedure. Require showcase validation with all nine artifact checks, zero
   composition errors and zero warnings. Do not substitute a handcrafted SVG and
   call it Archify output. Render failures must preserve the previous HTML.
5. Deliver through Archify to `Design/UI-Spec/implementation-plan.html`, then run
   its bounded `visual-check` and inspect the actual screenshots. Check the desktop
   viewports required by the installed skill and keep deterministic/browser/perceptual
   evidence distinct. Fix diagnosed issues through the skill's normal repair process.
6. Run the bundled acceptance command (provide the installed Archify CLI path):

   ```text
   python .specify/extensions/scope/scripts/accept_plan.py --archify <skill>/bin/archify.mjs --spec Design/UI-Spec/github/implementation-plan.archify.json --mapping Design/UI-Spec/github/implementation-plan.mapping.json
   ```

   This runs validation and delivery itself, records the source graph/spec/HTML
   hashes, checks browser behavior, synchronizes the legacy duplicate HTML under
   `Design/UI-Spec/github/`, and clears the pending marker only on success.
7. Review the diff and include plan data, candidate, HTML and receipt with the scope
   operation handoff. Never claim completed dependency-plan maintenance if an
   Archify command failed, sources changed, or the pending marker remains.
