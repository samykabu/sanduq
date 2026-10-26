# Licenses

Every Sanduq package is MIT licensed: all extensions, all presets and every portable skill. Each package folder
carries its own `LICENSE` file, and each built package ships it.

## Per package

| Package | Kind | License |
| --- | --- | --- |
| Assure | Extension | MIT ([LICENSE](../../extensions/assure/LICENSE)) |
| Illustrate | Extension | MIT ([LICENSE](../../extensions/illustrate/LICENSE)) |
| Memory | Extension | MIT ([LICENSE](../../extensions/memory/LICENSE)) |
| PR | Extension | MIT ([LICENSE](../../extensions/pr/LICENSE)) |
| Progress | Extension | MIT ([LICENSE](../../extensions/progress/LICENSE)) |
| Project | Extension | MIT ([LICENSE](../../extensions/project/LICENSE)) |
| Scope | Extension | MIT ([LICENSE](../../extensions/scope/LICENSE)) |
| User Manual | Extension | MIT ([LICENSE](../../extensions/user-manual/LICENSE)) |
| Workflow | Extension | MIT ([LICENSE](../../extensions/workflow/LICENSE)) |
| `workflow` | Preset | MIT ([LICENSE](../../presets/workflow/LICENSE)) |
| `scope-gate` | Preset | MIT ([LICENSE](../../presets/scope-gate/LICENSE)) |
| `scope-brainstorm` | Preset | MIT ([LICENSE](../../presets/scope-brainstorm/LICENSE)) |
| Illustrate, User Manual (5 skills), Delegate Task, Progress Report | Portable skills in [sanduq-skills](https://github.com/samykabu/sanduq-skills) | MIT |

The repository itself is covered by the root [LICENSE](../../LICENSE) (MIT).

## Earlier versions

Versions released before the MIT change remain under PolyForm Noncommercial 1.0.0, the license they shipped with.
The first MIT version of each package is listed below. Scope, `scope-gate` and `scope-brainstorm` were always MIT.


| Package | First MIT version |
| --- | --- |
| Assure | 2.6.2 |
| Illustrate | 2.7.2 |
| Memory | 2.5.1 |
| PR | 4.6.1 |
| Progress | 1.6.1 |
| Project | 2.6.1 |
| User Manual | 1.8.2 |
| Workflow | 1.19.0 |
| `workflow` preset | 1.3.1 |

## Vendored skills

Illustrate, User Manual, Progress and Workflow ship copies of portable skills, pinned in
[`vendor.lock.json`](../../vendor.lock.json). Those skills are MIT in sanduq-skills too. Each of these packages
ships a `THIRD_PARTY_NOTICES.md` with the notices for what it vendors.

## Third-party material

Bundled upstream material keeps its own license (MIT or CC0 1.0). See
[THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).
