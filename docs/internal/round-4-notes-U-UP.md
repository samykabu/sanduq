# Round 4 notes: U-UP (upstream sanduq-skills)

Worktree `D:\Projects\Personal\sanduq-skills-round4`, branch `feat/round-4`. No git command changed the tree, index or
branches. Nothing tagged or released.

## Versions (bumped per that repo: both `plugin.json` files, plus `illustrate/package.json`)

- dev-tools 1.2.0 to 1.3.0 (a shipped file is removed and build output changes).
- illustration-tools 3.6.0 to 3.7.0 (new generator option).
- agent-tools 1.6.0 to 1.6.1 (docs only).

Changelog: root `CHANGELOG.md` gets an `## Unreleased` entry for the three bundles; `skills/agent-tools/CHANGELOG.md`
gets `## 1.6.1 — Unreleased`. dev-tools and illustration-tools have no bundle changelog. Put the date in at release.

## Items

- **AU10** `user-manual/scripts/init_manual.py`: writes `docs/<lang>/index.md` only when it is missing. The dead
  `title = product if ... else product` line is gone. Test `test_init_manual.py`
  `test_an_authored_home_page_survives_and_a_missing_one_gets_the_stub` (failed before the fix). sanduq does not vendor
  this file; S-AU fixes the sanduq copy.
- **AU15** `user-manual/scripts/build_manual.py`: the renderer's stdout and stderr are captured. A successful build
  prints only the per-edition lines. A failed one prints `<edition>: <renderer> build failed` and the last 40 lines to
  stderr, then exits with the renderer's code. Tests `BuildOutputTests` (2, both failed before). I also checked a real
  MkDocs Material 9.7.6 build: `--all` printed 3 lines, and a broken `custom_dir` printed the MkDocs error.
- **AU20** deleted `user-manual/assets/user-manual-config.template.yml`. Nothing upstream read it (grep). It is a removal,
  so there is no regression test.
- **IP12** `import-drawio.md`, `import-excalidraw.md`, `import-mermaid.md`: Step 6 gets a new item 3 (the later items
  are renumbered) that runs `verify-geometry.py`, `self_check.py --strict` (technical-color: `--profile
  technical-color`) and the type's verifier, matching sanduq's `speckit.illustrate.import.md`. The coordinator's later
  request asked for exactly this, so it is done. Test `test_skill_frontmatter.py` `test_imports_run_the_step_7_checks`.
- **IP17** `technical-color-process-flow.md`: the Claude.ai "Preview & Fix" section (about 2.9 KB, including the
  coordinate guide, as the review said) is now three steps: run step 7, run `lint-render.py <file>` when Playwright is
  installed, else ask the user to open the file. The Contents anchor is updated. Size went from 19,898 B to 17,004 B.
  Test `test_technical_color_process_flow_has_no_host_specific_qa`.
- **IP18a** `scripts/generate-hand-variants.cjs --in X --out Y [--seed N]` converts one file. With no arguments it
  regenerates every example as before. Arguments are parsed before the npm packages load. A bad call exits 2 with the
  usage line. Missing packages exit 1 and tell you to run `npm ci` in the skill folder (Node 18+, network). This is the
  supported way to convert any consumer file. `primitive-sketchy.md` shows the route from the installed skill folder
  (`.specify/extensions/illustrate/skill/` under Spec Kit). `primitive-sketchy.md` and `variants.md` both say: without
  Node, deliver the minimal variant and say so. New `tests/test_generate_hand.py` (3 tests): `--in/--out` rebuilds
  `example-flowchart-hand.html` byte for byte (it is skipped unless `node_modules` exists), plus the usage and
  missing-package cases. CI (`ci.yml` tests job) now runs `npm ci` in the skill folder so the byte test runs there.
- **IP22 (coordinator request)** progress-report `docs/commands.md` (the `--schema v2` paragraph and the `--layout`
  row) and `docs/contracts.md` (the v2 section and the `layout` paragraph) mark v2 and `classic` as deprecated, to be
  removed in a later release. "The Workflow shim" now reads "older Workflow releases".

## Tests (uv, Python 3.11, `--with-requirements requirements-test.txt`)

- dev-tools user-manual: 32 tests, OK (29 before plus 3 new).
- illustration-tools: 223 tests, OK, 5 skipped (none of them new; `node_modules` was installed).
- agent-tools progress-report: 507 tests, OK, 13 skipped.
- `git diff --check` is clean, and every touched JSON file parses.

## Found, not changed

- A full `npm run generate:hand` is not byte-stable against the committed files. Ten committed `-hand` files
  (architecture, datalake, deployment, high-level, high-level-vertical, it-state, medallion, quadrant, state, timeline)
  end with a newline that the generator does not write. I put the committed bytes back each time. Fixing this means
  either the generator writes a final newline (53 files change) or those 10 lose theirs. That is for the next
  hand-variant change.
- `node_modules/` is installed in the worktree's illustrate folder. It is git-ignored, and both the release zip and
  sanduq's `package.py` exclude it.

## For sanduq to vendor (after release)

- `user-manual` input (dev-tools): `scripts/build_manual.py`, `tests/test_build_manual.py`. Drop the map entry for
  `assets/user-manual-config.template.yml` (S-AU, AU20 sanduq side). `init_manual.py` is not vendored.
- `illustrate` input (illustration-tools): `references/import-drawio.md`, `import-excalidraw.md`, `import-mermaid.md`,
  `primitive-sketchy.md`, `variants.md`, `technical-color-process-flow.md`, `scripts/generate-hand-variants.cjs` and
  `package.json`.
- `progress-report` input (agent-tools): `docs/commands.md`, `docs/contracts.md`.

## Requests

- S-AU: remove the `user-manual-config.template.yml` map from `vendor.lock.json` when vendoring dev-tools 1.3.0.
- S-IL: Illustrate's `references/variants.md` and `primitive-sketchy.md` now point at
  `.specify/extensions/illustrate/skill/` for `npm ci`. Check that the installed layout ships `package.json` and
  `package-lock.json` there. `vendor.lock.json` lists both today.
