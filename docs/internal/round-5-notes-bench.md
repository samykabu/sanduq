# Round 5 notes: OS-neutral Progress token benchmark

Branch `fix/bench-os-neutral` in this worktree (from origin/main 3009647) and in
`D:\Projects\Personal\sanduq-skills-round5` (from sanduq-skills origin/main e3faeaa). Nothing committed, pushed or tagged.

## Cause

The difference was never in the token counts. Both token tables were already equal on Windows and Linux. Only the
**Bytes (diagnostic)** row for LEGACY differed: Windows had updates 29311 and setup 6757, Linux had 29301 and 6752.

`approaches.legacy_setup_and_events` builds the protocol read call as
`call(file_path=str(LEGACY_PROTOCOL.relative_to(REPO)))`. On Windows `str()` of that path is
`extensions\workflow\skills\workflow\references\execution-report.md`. In JSON each `\` becomes `\\`, so the five
separators add 5 bytes per call. The call is made once in setup (+5) and again at `resume` and `compaction` (+10 in
updates). Nothing else differs: the CLI lines and the script output contain no OS paths, `subprocess(text=True)` and
`Path.read_text` already turn CRLF into LF, and `.gitattributes` pins `*.md` to LF.

## Fix (upstream, agent-tools 1.7.1)

- `skills/agent-tools/skills/progress-report/tests/bench/approaches.py`: new `read_call(rel)` returns
  `call(file_path=rel.as_posix())`. LEGACY builds its protocol call once with it and reuses it for setup, resume and
  compaction.
- `skills/agent-tools/skills/progress-report/tests/test_token_budget.py`: new `OsNeutral` test. It passes a
  `PureWindowsPath` and a `PurePosixPath` of the protocol path to `read_call` and asserts equal text and equal o200k_base
  and cl100k_base counts. On any OS it fails with the old `str(rel)` and passes with the fix (checked both ways).
- `skills/agent-tools/plugin.json`, `skills/agent-tools/.claude-plugin/plugin.json`: 1.7.0 to 1.7.1.
- `skills/agent-tools/CHANGELOG.md` (1.7.1 entry), root `CHANGELOG.md` (2026-10-22 entry).
- Upstream `docs/token-benchmark.md` is unchanged. LEGACY does not run upstream because the Workflow extension is not
  there, and `python -m tests.bench.report --check` exits 0.

## Test results (Windows 11, Python 3.11, tiktoken 0.14.0)

- Upstream progress-report suite: `python -m unittest discover -s tests -q` gave 508 tests, OK (4 skipped).
- Upstream `python -m tests.bench.report --check`: exit 0.
- Sanduq `extensions/progress/tests/test_token_budget.py` with the Windows skip removed:
  - with the current vendored bench: 8 tests, 1 failure (`test_generated_report_is_current`, LEGACY bytes row);
  - with the patched `approaches.py` copied in temporarily (then reverted): 8 tests, OK. Windows now renders
    `tests/token-benchmark.md` byte for byte as committed (the Linux counts).

## Expected LEGACY counts after vendoring

Same on both OSes and equal to the Linux values already in `extensions/progress/tests/token-benchmark.md`:
Bytes row `| LEGACY | 29301 | 6752 |` (updates, setup). The token tables do not change. On Linux `as_posix()` equals
`str()`, so the Linux output is unchanged and the report needs no regeneration.

## Sanduq changes

Done in this worktree:

- `extensions/progress/tests/test_token_budget.py`: removed the `@unittest.skipIf(os.name == "nt", ...)` decorator and its
  two-line comment on `test_generated_report_is_current`. `import os` stays because the env defaults use it.
  Until the vendor sync lands, this test fails on Windows. It still passes on Linux CI.

Still to do, after the `agent-tools-v1.7.1` tag exists:

- `python extensions/scripts/vendor.py sync --source <sanduq-skills checkout> --input progress-report --ref agent-tools-v1.7.1`
  (and `--input delegate-task` if the ref should move with it). Do not hand-edit `vendor.lock.json`.
- Vendored files that will change: **only `extensions/progress/tests/bench/approaches.py`**. `vendor.lock.json` gets
  that file's new hash and the new `ref`/`sha` for `progress-report`, and for `delegate-task` too if it is synced.
  No delegate-task file changes. `extensions/progress/docs/token-benchmark.md` (vendored upstream report) does not change.
- `extensions/progress/tests/token-benchmark.md` (Sanduq's own report) does not change.
- Optional: a Progress CHANGELOG line ("Vendors agent-tools 1.7.1: the token benchmark is identical on Windows and
  Linux"). The bench is not packaged, so no extension version bump is needed for users.
