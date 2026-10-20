# Round 4 notes: S-AU (Assure and User Manual)

Worktree `D:\Projects\Personal\sanduq-round4`. Design source `round-4-review-assure-user-manual.md`, amended by
`round-4-codex-review.md` (AU8 wording, AU16 input and output).

## Items

| Item | Done | What changed | Regression test |
| --- | --- | --- | --- |
| AU8 | yes | `documentation-gates.yml` checkout sets `ref: ${{ github.event.pull_request.head.sha }}` (with a one-line comment). `assure_init.py update_gate`: writes the gate when absent, replaces a file equal to the render without the two `HEAD_CHECKOUT` lines (CRLF-insensitive), keeps any other file and prints the `ref:` line to add. Prints `ci_gate=written/updated/current/kept/managed`. Init command text passes on that line. | `assure/tests/test_assure_init.py` (gate renders the head ref; unedited earlier gate replaced, edited kept) |
| AU8 S-INST | confirmed | `install.ASSURE_HEAD_CHECKOUT == assure_init.HEAD_CHECKOUT` (checked by import, True) and both are in the template bytes. Keep them byte-equal. | |
| AU9 | yes | `config_text(mode, text, source)`: on an existing config only the three `lifecycle` values are substituted (regex inside the `lifecycle:` block, trailing comments kept), then reparsed; a config without the three keys stops init with a message and is not written. `extensions.yml` written only when `changed > 0`. | `test_assure_init.py`: custom `scan.exclude` and a comment survive integrated/manual reruns; same-mode rerun leaves `extensions.yml` bytes identical; keyless config refused |
| AU10 | yes (sanduq copy) | `init_manual.py` guards `docs/<lang>/index.md` with `if not exists`; dead `title` line dropped. **Upstream copy (dev-tools portable `user-manual/scripts/init_manual.py`) needs the same fix: U-UP.** | `user-manual/tests/test_init_manual.py` (new; first test of `main()`) |
| AU11 | yes | `assure_scan.git_folders`: one `git ls-files --cached --others --exclude-standard -z`; the walk prunes folders git never reaches; `scan.exclude` still applies; plain walk outside git. One listing per folder (os.walk's), matched with one cached regex per pattern set (`fnmatch.translate`, case-insensitive on Windows like `Path.glob`). Template exclude list adds `.venv`, `venv`, `__pycache__`, `target`, `vendor`, `Pods`, `.gradle`. Known limit (commented): folders inside a submodule are not walked. | `test_assure_scan.py`: ignored `.venv`/`out/target` rows absent, untracked project present, `scan.exclude` still prunes in git; non-git fallback honours the list |
| AU12 | yes | User Manual Analyze step 6 names `<!-- user-manual-tasks:start -->` / `:end -->` and says to replace the block on rerun. | `user-manual/tests/test_commands.py` |
| AU13a | yes | Document step 5.3 and Update step 6 say `python .specify/extensions/illustrate/skill/scripts/<script>` instead of the bare `` `scripts/` `` token. | both `test_commands.py` carry the pinned 8147943 pattern and assert no command matches it |
| AU13b | yes | `--check` prints rows and the `memory:` line; `--show-block` adds the block. Analyze text: "one line per detected project". | `test_assure_scan.py` (`--check` omits, `--show-block` prints); `test_commands.py` |
| AU14 | yes | Update step 8: `build_manual.py --all`; `--archive` only when `manual.yml` names an approved provider. Release keeps `--archive`. README row updated. | `user-manual/tests/test_commands.py` |
| AU16 | yes | `sanduq_freshness.task_bytes(content, kind)`: checkbox normalisation, plus for `analyze` the manual block (with the blank lines before it) removed. Used in `fingerprints(..., kind)` and in the `inputs()` tasks.md override (the second pass Codex named), and for output hashes at record and at status. Document and manual kinds unchanged. Old states: a state recorded over a `tasks.md` without the block hashes exactly as before (stays current, and now survives the manual hook); one recorded over a `tasks.md` that already held the block goes stale once. No state marker needed. | `assure/tests/test_freshness_tasks.py`: block add/replace/remove keeps analyze current; a QA task edit stales it (input and output); document kind still sees the block; hashes of a block-free tasks.md unchanged |
| AU17 | yes (deps.py and Assure/User Manual text) | `deps.py` non-zero line ends `; after the user agrees, re-run with --approve` (prompt) or `; the user runs it, then re-runs the command` (manual). The four command blocks became one sentence: report the line verbatim, follow it, skip diagrams. | `assure/tests/test_deps_route.py`; existing `extensions/scripts/tests/test_deps.py` passes unchanged |
| AU18 | yes, partly | `SKILL.ext.md` loses the routing section; rule 7 and `documentation.md` point at `.specify/extensions/assure/scripts/`. Rule 1 (feature resolution) kept: Document relies on it ("as the contract says") and its `specs/` fallback is not stated in the commands; dropping it would change behaviour. | `assure/tests/test_commands.py` |
| AU19 | yes | `sanduq_freshness.cli` calls `default_outputs(root)` only for `record`. `status --summary` still prints `outputs=<number of explicit --output>` (0 without), so Workflow's existing summary tests keep passing; the walk is what is gone. | `user-manual/tests/test_manual_state.py` `ManualStateStatusWalkTests` |
| AU20 | yes (sanduq side) | Template drops `freshness.policy`, `freshness.state_directory`, `output.directory_name`; comment says init sets the three lifecycle keys and the analyze gate is the `before_implement` hook. `user-manual-config.template.yml` not touched (vendored): U-UP and the orchestrator. | existing `test_init_writes_the_default_exclude_list` |
| orchestrator request | yes | `## 2.1.0 (unreleased)` (Assure) and `## 1.1.0 (unreleased)` (User Manual) renamed to `## 2.1.0` / `## 1.1.0`; `check_docs.py` passes. | |

## Measurements

Instruction benchmark (`benchmark_instructions.py --extensions assure,user-manual`, same machine):

| | before | after |
| --- | ---: | ---: |
| assure instruction bytes | 23,622 | 19,573 (-17.1%) |
| user-manual instruction bytes | 27,582 | 27,429 |
| both | 51,204 | 47,002 (-8.2%) |
| assure analyze / document | 8,773 / 12,325 | 8,042 / 11,642 |
| user-manual analyze / update | 8,250 / 7,067 | 8,174 / 6,990 |

`assure_scan.py --check` on this repo: output 3,319 B to 925 B (`--show-block` output byte-identical to the old
`--check`); `scan()` in-process 0.239 s to 0.108 s (min of 5, 14 projects either way).

AU14 build on `docs/examples/booking-manual` (English, 3 audience editions, mkdocs-material 9.7.6, uv Python
3.11, min of 3): `--all --archive` 16.1 s, `--all` 10.4 s (-35%).

## Requests

- **U-UP**: apply AU10 to the portable dev-tools `user-manual/scripts/init_manual.py` (guard `docs/<lang>/index.md`,
  drop the dead `title = product if language == "en" else product`). AU20: delete
  `user-manual-config.template.yml` in dev-tools (nothing reads it).
- **Orchestrator (vendor.lock.json)**: after U-UP's release, drop the `user-manual-config.template.yml` map entry and
  delete `extensions/user-manual/user-manual-config.template.yml`. I left both alone (vendored).
- **S-PM**: `deps.py` now prints the approval route itself. PR's `speckit.pr.generate.md` dependency block can
  shrink to one sentence: run `deps.py ensure illustrate`; on non-zero, report the line verbatim, follow it, skip
  diagrams.
- **S-INST**: `install.py` `LEGACY_CI_HAS_LOCAL_EDITS` compares a legacy gate to the installed reference; with
  the AU8 template an unedited older legacy gate differs. You said this is handled via `ASSURE_HEAD_CHECKOUT`;
  confirmed equal above.
- **S-DOC**: `docs/extensions/assure.md` and `user-manual.md` may describe `--check` printing the block, the
  default exclude list or `--all --archive` on Update; align with the changelogs.
- **S-WF**: `workflow/tests/test_assure_init.py` still passes; my AU8/AU9 tests live in
  `extensions/assure/tests/test_assure_init.py` (the review named the workflow file, which S-WF owns).

## Tests (uv Python 3.11, end of stream)

- `extensions/assure/tests`: 41 tests OK (was 24; new: `test_assure_init.py`, `test_freshness_tasks.py`,
  `test_deps_route.py`, scan and command cases).
- `extensions/user-manual/tests`: 51 tests OK (was 44; new: `test_init_manual.py`, status-walk, command cases).
- `extensions/scripts/tests` (includes `test_deps.py`, package tests): 151 run, 1 error not mine:
  `test_ci_matrix.Round4Selection.test_shards_balance_measured_seconds` wants `.github/scripts/shard_weights.json`,
  which S-CI has not written yet.
- Workflow tests touching the shared helpers (`test_freshness`, `test_assure_state`, `test_assure_init`,
  `test_ci_policy`, `test_eol_fingerprints`): 82 OK.
- `vendor.py check` clean; `validate_skills.py` 6 skill files, 0 errors; `check_docs.py` OK.
