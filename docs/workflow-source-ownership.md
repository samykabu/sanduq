# Reusable workflow source ownership

| Component | Canonical source | Consumer status |
| --- | --- | --- |
| Scope runtime, analyst and GitHub clarification | Sanduq `extensions/scope/` | The pilot project still uses its previous install; migration pending |
| Scope gate and brainstorm presets | Sanduq `presets/scope-gate/`, `presets/scope-brainstorm/` | Bundled in archives; no consumer edits yet |
| Managed dispatcher and task adapter | Sanduq `extensions/workflow/` | Clean-install fixtures only |
| Managed core/SuperSpec command overlays | Sanduq `presets/workflow/` | Installed by the public preset CLI |
| Short Scope entry skill | Sanduq `extensions/workflow/skills/speckit-scope/` | Installer replaces only a recognized legacy alias or identical owned source |
| Legacy short Bridge router | Sanduq `extensions/workflow/skills/speckit-superpowers-bridge/` | Recognized pilot-project mirror can migrate; upstream native executor remains separately owned |
| Installation and self-upgrade adapters | Sanduq `extensions/workflow/scripts/` | Consumer package invokes public CLI; local backups and project lock retained |
| PR visuals contract | Sanduq `extensions/pr/commands/speckit.pr.generate.md` | Generated skills inherit after installation |
| QA/manual freshness helper | Sanduq `extensions/scripts/shared/` | Copied deterministically into release archives |
| Core Spec Kit and SuperSpec | Their upstream repositories | No vendored upstream fork; tested via installed distributions |
| Archify | Existing separately installed Archify skill | Workflow illustrations use it; not relabeled as Sanduq original work |
| The pilot project's requirements, issue IDs and board settings | Pilot-project policy/configuration | Must remain project data, not hardcoded Sanduq source |
| Other installed design/third-party skills | Existing upstream sources pending individual provenance audit | No blanket copying or relicensing |

Scope migration source: the pilot project's `tools/speckit-scope`, observed clean at commit
`41fa4322368ac0c3e71d497a39939a751dd61247`. Scope's MIT license is preserved. The
legacy `speckit-scope` alias now has a canonical distribution path in the workflow
package; the pilot-project replacement awaits adoption. Do not retain its old installer as a
second authority. No custom `.codex/agents`
files were found in the inspected pilot-project checkout. This is a scoped workflow inventory,
not a completed audit of every third-party skill installed on the workstation.
