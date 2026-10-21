# Round 4 notes: S-IL (Illustrate and Progress)

## IP11 (fix-first): the self-check hook reads its setting without PyYAML, or fails closed

`extensions/illustrate/hooks/self_check_hook.py`:

- `enabled()` uses PyYAML when the hook's Python has it. Without it, `read_key()` reads the key from block mappings,
  flow mappings (`illustrate: {hooks: {self_check: true}}`, as the docstring shows, including multi-line flow), mixed
  block and flow, quoted keys, comments, a leading `---`, unindented lists and block scalars elsewhere in the file,
  YAML 1.1 true values, and duplicate keys (the last wins, as in PyYAML).
- No partial fallback (Codex amendment). Anything on the key's path the reader cannot read the way PyYAML would
  (anchors, aliases, tags, merge keys, block scalars, odd indentation, unparseable flow) raises `Unreadable`. PyYAML
  parse errors raise it too (before, they returned off). A reader bug is treated the same way.
- `main()` looks at the payload first. Only when a written `.html` contains `<svg` does it read the setting. An
  unreadable setting then exits 2 with one line: what failed, and the fix (install PyYAML for `<sys.executable>`,
  write plain block lines, or set the key to false and rerun the installer, or `uninstall`).
- `subprocess` is imported inside `first_failure`. A non-diagram write loads neither PyYAML nor `subprocess`.

Tests (`tests/test_self_check_hook.py`, class `PolicyForms`, 6 tests): 10 on-forms and 8 off-forms, each with PyYAML
absent (`sys.modules['yaml'] = None`) and present; the stdlib reader agrees with PyYAML on all 18; three
PyYAML-only forms fail closed without PyYAML and read as on with it; invalid YAML fails closed in both modes; a
non-diagram write never reads the setting (subprocess probe: no `yaml`, no `subprocess` in `sys.modules`). Against
the old hook these fail (21 failures, 18 errors, checked in a scratch copy).

Not changed: a missing `skill/scripts/` still exits 0 (documented "no skill allows"). It is a broken install, not
the setting read.

## IP12 (fix-first, command side)

`commands/speckit.illustrate.import.md` step 7 now runs, after theme apply and validate: `verify-geometry.py
<output.html>`, `self_check.py --strict <output.html>` (technical-color: `--profile technical-color`), and the type's
`verify-<type>.py` when one exists; fix and rerun until they pass. Regression test: `tests/test_commands.py` (also
pins the SKILL.md step 7 wording it mirrors). Fails on the old command text.

## IP16

- `generate.md` Output: export per SKILL.md §12 (the `references/export.md` pointer is gone).
- `theme.md`: the script and `--help` for `init`, `set`, `list`, `resolve`, `validate`; `theme-initialization.md`
  only for `create` or a design source.
- `import.md` step 3: full `.specify/extensions/illustrate/skill/references/theme-initialization.md` path.

`benchmark_instructions.py --extensions illustrate,progress`, before (22917b5 tree) and after:

| command | instruction bytes before | after |
| --- | ---: | ---: |
| speckit.illustrate.theme | 9017 | 1200 (7990 now conditional) |
| speckit.illustrate.generate | 13804 | 13788 |
| speckit.illustrate.import | 27231 | 27603 (+372, the IP12 checks) |
| illustrate command bytes | 51664 | 44203 (-14%) |
| illustrate total instruction bytes | 154767 | 155296 (+0.3%) |

The harness does not resolve the bare `references/export.md` link in `generate.md`, so that saving (about 10.5 KB
when an agent followed it) does not show in its numbers. The total rises because `theme-initialization.md` is still
counted through SKILL.md and import grew by the IP12 lines. Progress unchanged (9195).

## IP22 (deprecation notice only)

`extensions/progress/CHANGELOG.md` `## Unreleased` with a Migration block; `extensions/progress/README.md` (Quick
start, Commands, Theming, Upgrading) says `--schema v2` and `--layout classic` are deprecated and will be removed in a
later release. No code removed. `docs/contracts.md` and `docs/commands.md` are vendored: see Requests.

## Orchestrator request

`extensions/progress/README.md:28`: `--priority 10` changed to `--priority 1`.

## Tests run (uv python 3.11)

- Illustrate: `python -m unittest discover -s tests`: 18 tests, OK.
- Progress: 14 tests, OK (with tiktoken; 7 skipped without it).
- Workflow `test_install_hooks.py` (copies the Illustrate hook): 14 tests, OK.
- `vendor.py check`: vendored inputs match. `check_docs.py`: no finding in Illustrate or Progress (other files have
  findings owned by other streams, including a stale `docs/reference/hooks.md`).

## Requests

- **U-UP (illustration-tools)**: IP12 references: add the step 7 line (`verify-geometry.py <out>`, `self_check.py
  --strict <out>`, technical-color `--profile technical-color`) to the "Run" steps of `import-drawio.md`,
  `import-excalidraw.md` and `import-mermaid.md`.
- **U-UP (agent-tools, progress-report)**: IP22 docs: mark `--schema v2` and `--layout classic` deprecated in
  `docs/commands.md` (around :244) and `docs/contracts.md` (around :393); both still name "the Workflow shim".
- **S-DOC**: the round's migration table can take the Illustrate Migration line (an unreadable `workflow.yml` now
  blocks written diagrams when `self_check: true`).
