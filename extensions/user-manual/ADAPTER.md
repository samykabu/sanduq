# Portable to extension adapter

The portable `user-manual` skill in [samykabu/sanduq-skills](https://github.com/samykabu/sanduq-skills)
(`skills/dev-tools/skills/user-manual`) is the canonical source. `extensions/scripts/vendor.py`
copies the files in section 1 byte for byte and applies the rewrites in section 2; the pinned commit
and file hashes are in `vendor.lock.json`. Files in sections 3 to 5 are owned here. Paths in the
"Portable" column are relative to `skills/dev-tools/skills/` in sanduq-skills; paths in the
"Extension" column are relative to `extensions/user-manual/`. Extension skill entrypoints are
stored as `SKILL.ext.md` and restored to `SKILL.md` by `extensions/scripts/package.py`.

## 1. Path mapping (copy, no content change)

| Portable | Extension |
| --- | --- |
| `user-manual/scripts/audit_manual.py` | `scripts/audit_manual.py` |
| `user-manual/scripts/build_manual.py` | `scripts/build_manual.py` |
| `user-manual/tests/test_build_manual.py` | `tests/test_build_manual.py` |
| `user-manual/tests/test_audit_manual.py` | `tests/test_audit_manual.py` |
| `user-manual/assets/scaffold/**` | `assets/scaffold/**` |
| `user-manual/references/*.md` (including the API, release, screenshot and preview references) | `skills/user-manual/references/*.md` |

## 2. Content rewrites

| File (portable → extension) | Portable form | Extension form | Reason |
| --- | --- | --- | --- |
| `user-manual/assets/github/user-manual-preview.yml` → `assets/github/user-manual-preview.yml` | `"User-Manual/tools/**"` (paths filter, line 8) | `".specify/extensions/user-manual/**"` | Extension scripts live in the Spec Kit install, not in the manual |
| same file | `User-Manual/tools/` (3 occurrences: audit and two build calls) | `.specify/extensions/user-manual/scripts/` | Same |
| `user-manual/assets/github/user-manual-release.yml` → `assets/github/user-manual-release.yml` | `User-Manual/tools/` (3 occurrences) | `.specify/extensions/user-manual/scripts/` | Same |
| `user-manual/scripts/init_manual.py` → `scripts/init_manual.py` | `import sanduq_ci` | The same import, with a `sys.path` fallback to `../workflow/scripts` | The source tree keeps `sanduq_ci` in Workflow; a built package has it beside the script. The command passes `--no-tools`: the extension runs its scripts from `.specify/extensions/user-manual/scripts/`, so none are copied into `User-Manual/tools/` |

## 3. Extension-owned files (not generated; keep the extension's file)

| Extension file | Portable counterpart | Reason |
| --- | --- | --- |
| `scripts/manual_state.py` | `user-manual/scripts/manual_state.py` | Extension delegates to the shared `sanduq_freshness` helper (Spec Kit feature dirs, Workflow checkpoint `target_branch` default for `--base-ref`, `.specify/` and `workflow/`/`evidence/` exclusions, `tasks.md` checkbox normalization, `sanduq_hash.portable_files` EOL handling). Portable is a self-contained equivalent with the same CLI (`record`/`status`, `--feature`, `--repo-root`, `--base-ref`, `--output`, `--summary`, `--json`), state schema 2 shape and exit codes |
| `skills/user-manual/SKILL.md` | `user-manual/SKILL.md` | Front matter `description` names `speckit.user-manual.init/analyze/update/release`; no standalone/workflow section, no example, rule 7 names Illustrate. Portable is standalone, documents `scripts/*.py`, `User-Manual/tools/`, a routing table and rule 9 (cross-audience links). Both route API, release, screenshot and preview work to the same `references/*.md` files |
| `tests/test_manual_state.py` | `user-manual/tests/test_manual_state.py` | Tests the checkpoint `--base-ref` default (Spec Kit only) |

## 4. Portable-only files (drop in the extension build)

| Portable file | Reason |
| --- | --- |
| `user-manual/scripts/sanduq_ci.py` | Vendored subset of `extensions/workflow/scripts/sanduq_ci.py` without gate policy and with `load_ci(policy_path=None)` reading an explicit YAML file, or a project root's `.specify/workflow.yml` when given a directory. The extension package vendors Workflow's copy |
| `user-manual/tests/test_init_manual.py` | Asserts the portable scaffold (tool copies, no `.specify/`). The extension's own `tests/test_init_manual.py` runs the vendored script with `--no-tools` |

## 5. Extension-only files (no portable counterpart)

| Extension file | Reason |
| --- | --- |
| `extension.yml`, `dependencies.yml` | Spec Kit manifest and Illustrate dependency |
| `commands/speckit.user-manual.{init,analyze,update,release}.md` | Spec Kit commands, hooks and `deps.py ensure illustrate` |
| `README.md`, `CHANGELOG.md` | Package documentation and release history |
| Packaged `scripts/sanduq_freshness.py`, `scripts/sanduq_hash.py`, `scripts/sanduq_ci.py`, `scripts/deps.py` | Added by `extensions/scripts/package.py` from `extensions/scripts/shared/` and `extensions/workflow/scripts/` |
