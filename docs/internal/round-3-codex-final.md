1) Agree with the direction; these changes remain:

- **§1.2:** Say “`remove --keep-config` preserves only top-level YAML config; ordinary removal backs those files up.” The current wording incorrectly implies preservation without the flag.
- **§2.7:** Explicitly require reconciliation of `.codex/config.toml` **and** `.codex/hooks.json`, preservation of unrelated hooks, visible approval/policy activation, and rollback tests covering failures. “Dispatcher cleanup” does not cover the full hook migration.
- **§2.4:** Restore PM4’s **scope checks**, alongside remote normalization and timeouts; they remain part of the correctness fix.
- **§3.4:** Add “retain worker prohibitions independently of guard availability.” Shortening instructions must not assume the Codex guard is active.

2) Other review requirements dropped or weakened:

- **§2.8:** Restore the explicit fix for broken **export paths**; correcting command names alone does not cover it.
- **§3.1:** Explicitly test **event wiring** against the CI pin, including the assumed `specify_cli.events` API; a generic compatibility check leaves this ambiguous.
- **§3.3:** Retain Chromium **OS dependency installation** on fresh runners; browser caching alone is insufficient.
- **§4 / §7:** The small PM5 fix also needs actionable reporting of missing noninteractive choices.
- **§1.4:** State that retained command aliases temporarily retain namespace collisions and catalog-description cost. Renaming the ID does not immediately remove either.
- **Measurement:** Keep the explicit rule against adding overlapping savings percentages.

3) The one risk I would watch most: **Illustrate hook ownership transfer breaking existing installations** through missed host configuration, inactive approval, or dangling commands. It ships before the separately gated rename.

Not checked: implementation, tests, or live upgrade flows; read-only document comparison only.