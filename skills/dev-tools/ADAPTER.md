# Portable to extension adapter

The portable skills in `skills/dev-tools/skills/user-manual*` are the canonical source. The
`extensions/user-manual` package is built from them by the transform below. Every file not listed
in a table is copied byte for byte. Paths in the "Portable" column are relative to
`skills/dev-tools/skills/`; paths in the "Extension" column are relative to `extensions/user-manual/`.

## 1. Path mapping (copy, no content change)

| Portable | Extension |
| --- | --- |
| `user-manual/scripts/audit_manual.py` | `scripts/audit_manual.py` |
| `user-manual/scripts/build_manual.py` | `scripts/build_manual.py` |
| `user-manual/assets/scaffold/**` | `assets/scaffold/**` |
| `user-manual/assets/user-manual-config.template.yml` | `user-manual-config.template.yml` |
| `user-manual/references/*.md` | `skills/user-manual/references/*.md` |
| `user-manual-api-docs/references/*.md` | `skills/api-docs/references/*.md` |
| `user-manual-preview-publishing/references/*.md` | `skills/preview-publishing/references/*.md` |
| `user-manual-release-docs/references/*.md` | `skills/release-docs/references/*.md` |
| `user-manual-ui-screenshots/references/*.md` | `skills/ui-screenshots/references/*.md` |

## 2. Content rewrites

| File (portable → extension) | Portable form | Extension form | Reason |
| --- | --- | --- | --- |
| `user-manual/assets/github/user-manual-preview.yml` → `assets/github/user-manual-preview.yml` | `"User-Manual/tools/**"` (paths filter, line 8) | `".specify/extensions/user-manual/**"` | Extension scripts live in the Spec Kit install, not in the manual |
| same file | `User-Manual/tools/` (3 occurrences: audit and two build calls) | `.specify/extensions/user-manual/scripts/` | Same |
| `user-manual/assets/github/user-manual-release.yml` → `assets/github/user-manual-release.yml` | `User-Manual/tools/` (3 occurrences) | `.specify/extensions/user-manual/scripts/` | Same |
| `user-manual/scripts/init_manual.py` → `scripts/init_manual.py` | `import sanduq_ci` | `import sys` on the line after `import shutil`; `import sanduq_ci` becomes `try: import sanduq_ci` / `except ImportError:` that inserts `Path(__file__).resolve().parents[2] / "workflow" / "scripts"` on `sys.path` and retries | Extension uses Workflow's canonical `sanduq_ci`, which `extensions/scripts/package.py` vendors beside the scripts |
| same file | `parser.add_argument("--ci-policy", ...)` (2 lines) | absent | Extension reads the policy from the fixed Spec Kit path |
| same file | `sanduq_ci.load_ci(args.ci_policy)` | `sanduq_ci.load_ci(root)` | Workflow's `load_ci(root)` reads `.specify/workflow.yml` |
| same file | identifier `skill_root` (7 occurrences) | `extension_root` | Naming only |
| same file | `for name in ("audit_manual.py", "build_manual.py", "manual_state.py"): copy_if_missing(skill_root / "scripts" / name, manual_root / "tools" / name)` | absent | Extension runs scripts from `.specify/extensions/user-manual/scripts/`; no copies in the manual |

## 3. Extension-owned files (not generated; keep the extension's file)

| Extension file | Portable counterpart | Reason |
| --- | --- | --- |
| `scripts/manual_state.py` | `user-manual/scripts/manual_state.py` | Extension delegates to the shared `sanduq_freshness` helper (Spec Kit feature dirs, Workflow checkpoint `target_branch` default for `--base-ref`, `.specify/` and `workflow/`/`evidence/` exclusions, `tasks.md` checkbox normalization, `sanduq_hash.portable_files` EOL handling). Portable is a self-contained equivalent with the same CLI (`record`/`status`, `--feature`, `--repo-root`, `--base-ref`, `--output`, `--summary`, `--json`), state schema 2 shape and exit codes |
| `skills/user-manual/SKILL.md` | `user-manual/SKILL.md` | Front matter `description` names `UserManual.Init/Analyze/Update/Release`; routes to companions by `../api-docs/SKILL.md` etc.; no standalone/workflow section, no example, rule 7 names Illustrate. Portable is standalone, routes to `user-manual-*` skills, documents `scripts/*.py`, `User-Manual/tools/` and has rule 9 (cross-audience links) |
| `skills/api-docs/SKILL.md` | `user-manual-api-docs/SKILL.md` | `name: api-docs`; Spec Kit wording ("add a task"); no example |
| `skills/preview-publishing/SKILL.md` | `user-manual-preview-publishing/SKILL.md` | `name: preview-publishing`; no example |
| `skills/release-docs/SKILL.md` | `user-manual-release-docs/SKILL.md` | `name: release-docs`; grounds items in Spec Kit artifacts; no example |
| `skills/ui-screenshots/SKILL.md` | `user-manual-ui-screenshots/SKILL.md` | `name: ui-screenshots`; no example |
| `skills/*/agents/openai.yaml` (5 files) | `user-manual*/agents/openai.yaml` | `display_name`, `short_description` and `default_prompt` use the extension skill names (`$api-docs`, ...) |
| `tests/test_build_manual.py` | `user-manual/tests/test_build_manual.py` | Same tests except portable adds `test_one_audiences_assets_do_not_leak_into_another_edition` and a different module docstring; can be generated from portable once accepted |
| `tests/test_manual_state.py` | `user-manual/tests/test_manual_state.py` | Tests the checkpoint `--base-ref` default (Spec Kit only) |

## 4. Portable-only files (drop in the extension build)

| Portable file | Reason |
| --- | --- |
| `user-manual/scripts/sanduq_ci.py` | Vendored subset of `extensions/workflow/scripts/sanduq_ci.py` without gate policy and with `load_ci(policy_path=None)` reading an explicit YAML file instead of `.specify/workflow.yml`. The extension package vendors Workflow's copy |
| `user-manual/tests/test_init_manual.py` | Asserts the portable scaffold (tool copies, no `.specify/`) |

## 5. Extension-only files (no portable counterpart)

| Extension file | Reason |
| --- | --- |
| `extension.yml`, `dependencies.yml` | Spec Kit manifest and Illustrate dependency |
| `commands/speckit.user-manual.{init,analyze,update,release}.md` | Spec Kit commands, hooks and `deps.py ensure illustrate` |
| `README.md`, `CHANGELOG.md` | Package documentation and release history |
| Packaged `scripts/sanduq_freshness.py`, `scripts/sanduq_hash.py`, `scripts/sanduq_ci.py`, `scripts/deps.py` | Added by `extensions/scripts/package.py` from `extensions/scripts/shared/` and `extensions/workflow/scripts/` |
