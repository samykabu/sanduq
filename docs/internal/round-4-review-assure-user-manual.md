# Round 4 review: Assure and User Manual (stream R3)

Read-only review of `D:\Projects\Personal\sanduq-round4` at fb17f52 (branch `feat/round-4`): Assure 2.5.1,
User Manual 1.7.1, the issue-99 freshness change (79eacab), and the shared files `package.py:65-79` injects
(`sanduq_freshness.py`, `sanduq_hash.py`, `sanduq_ci.py`, `deps.py`). Spec Kit source: the CI pin 8147943
(`D:\Projects\Personal\spec-kit`). Reproductions ran in a scratch folder, never in the tree. Python 3.11 via
`uv run --no-project`. This review does not redo round 3 (AU1 to AU7 shipped, `round-3-notes.md:218-226`,
`:310-313`). Numbering continues at AU8.

Upstream (sanduq-skills, `vendor.lock.json` user-manual map at dev-tools-v1.2.0, f260c7b; `vendor.py check`
clean; no dev-tools commit after the tag): `audit_manual.py`, `build_manual.py`, `tests/test_build_manual.py`,
`assets/scaffold/**` (mkdocs.yml, requirements.lock, the six CSS files), `user-manual-config.template.yml`,
both `user-manual-*.yml` CI templates (with path rewrites) and every `skills/*/references/*.md`. Everything
else in both extensions is owned here (`ADAPTER.md` sections 3 and 5). A change to a vendored file is an
upstream change first.

## 1. Summary

1. Six defects, all reproduced. The worst: the Assure CI gate (`documentation-gates.yml`) checks out the PR
   merge commit, so the QA and User Manual freshness steps fail whenever the base branch moved after the
   last `record` (AU8). Two init scripts destroy consumer content: `assure_init.py` rewrites a customised
   `assure-config.yml` (AU9), `init_manual.py` overwrites an authored `docs/<lang>/index.md` (AU10).
2. AU3 (skip an unchanged Analyze) rarely fires for standalone users: in the documented install order the
   User Manual `after_tasks` hook edits `tasks.md` between the two Assure runs, so the second one is a full
   rerun (AU16).
3. The biggest runtime cost is the User Manual build. `build_manual.py --all --archive`, which Update runs on
   every pass, took 40.6 s on a 4-page bilingual manual; 15.4 s of it is the zip archives no local step uses
   (AU14). The build also streams 7,218 bytes of MkDocs banners into the agent transcript (AU15).
4. Instruction load is small and mostly settled. What is left: the scan block Analyze does not need
   (2,347 of 3,319 bytes of `assure_scan.py --check` output, AU13), the four dependency blocks (2,354 bytes,
   AU17), and the duplicated skill routing (AU18).
5. Several config keys look live but nothing reads them (AU20). No merge of the two extensions is proposed
   (O5 A1, user decision 2026-10-20).

## 2. Size and cost now

| Item | Value | Source |
| --- | ---: | --- |
| Assure instruction bytes (analyze / document / init) | 8,773 / 12,325 / 1,438 | `benchmarks/round-4-before-instructions.md` |
| User Manual instruction bytes (init / analyze / update / release) | 4,817 / 8,250 / 7,067 / 4,921 | same |
| Packages, zip (raw) | assure 51,122 (125,587), 22 files; user-manual 71,650 (162,427), 46 files | `package.py` into scratch |
| Injected shared bytes per package | 57,008 raw (`deps.py` 26,278, `sanduq_ci.py` 14,453, `sanduq_freshness.py` 10,233, `sanduq_hash.py` 6,044) | same |
| Test suites | assure 24 tests 6.9 s; user-manual 44 tests 20.1 s (top 8 are `test_manual_state` git fixtures, 1.3-3.2 s each) | ran, `--durations` |
| `assure_scan.py --check` on this repo | 0.48 s scan (201 dirs, 14 projects), 3,319 B output, 2,347 B of it the block | ran |
| `build_manual.py` on a 4-page en+ar manual | `--all --archive` 40.6 s, `--all` 25.2 s, one edition 4.5 s; 7,218 B output | ran, mkdocs-material 9.7.6 |

## 3. Defects (fix first)

| # | Defect | Reproduction | Where |
| --- | --- | --- | --- |
| AU8 | CI gate compares the merge commit | Branch from A, record a document state, add commit B on main, check out the merge as `actions/checkout` does for `pull_request`: `status` returns `stale-input-or-output`, `changed_inputs: ["other.txt"]`, exit 1 | `assure/assets/github/documentation-gates.yml:17-19` (no `ref:`); `sanduq_freshness.py:76` diffs the saved base against the working tree. Workflow's gate pins `head.sha` (`workflow-gates.yml:24`) |
| AU9 | `assure_init.py` drops consumer config | Config with `scan.exclude` adding `.venv` and `vendor`; rerun `--mode integrated` (same mode): both entries gone. `extensions.yml` loses its comment even when nothing changed | `assure_init.py:89,91`: `config.write_text(config_text(mode))` always writes the template; `extensions.yml` is re-dumped unconditionally |
| AU10 | `init_manual.py` overwrites an authored home page | `User-Manual/docs/en/index.md` with "# My authored home page" and no `manual.yml`: after init the file is the stub. The docstring says "without overwriting authored pages" | `init_manual.py:178` (module pages are guarded at `:183`). The portable copy upstream has the same line |
| AU11 | Scan lists projects inside ignored trees | A repo with `.venv/Lib/site-packages/foo/pyproject.toml` and `.../playwright/driver/package/package.json` prints `backend .venv/...` and `tooling .venv/...`; these rows go into `.github/memory/project-memory.md` on Document | `assure_scan.py:135-148` walks every directory; the exclude list (`assure-config.template.yml:11-24`) has no `.venv`, `venv`, `target`, `vendor`, `Pods`, `.gradle`, `__pycache__`. Existing consumers carry their own copy of the list, so a template fix does not reach them |
| AU12 | User Manual Analyze names no task marker | "Use marker-delimited blocks and do not duplicate tasks on rerun" with no marker anywhere (grep: Assure defines `qa-prepare`, User Manual defines none). Idempotence rests on the model inventing the same marker twice | `speckit.user-manual.analyze.md:42`; vs `assure/skills/assure/references/analysis.md:24-29` |
| AU13a | Rendered text is garbled by Spec Kit | Spec Kit 8147943 rewrites a bare `` `scripts/` `` to the extension's own folder (`agents.py:197-243`, applied at `:543`). Emulated on the shipped commands: "Its `.specify/extensions/assure/scripts/` are under `.specify/extensions/illustrate/skill/scripts/`" | `speckit.assure.document.md:124`, `speckit.user-manual.update.md:51`. The other rewrites (`skills/...` to `.specify/extensions/user-manual/skills/...`) are correct |

Not defects, checked: `gate_on` (AU5) handles `false  # set to true` and non-mapping YAML; `audit_qa.py` (AU2)
decodes `%20` and resolves `/x` under `public`/`static`; the issue-99 rule keeps declared outputs out of
inputs only for states carrying `outputsNotInputs` (`sanduq_freshness.py:108-121`); stage order
`qa_document` before `manual_update` (`workflow.py:44-46`) keeps the manual state valid after a QA run.
`record` needs `refs/remotes/origin/HEAD` or a checkpoint branch (`sanduq_freshness.py:59-65`); a repo created
with `git init` and pushed has neither, but the error names `--base-ref`, so this stays a note.

## 4. Options

Savings are estimates on the base named. They are not additive; each must be remeasured.

### AU8. Gate the PR head, not the merge commit

- what: add `ref: ${{ github.event.pull_request.head.sha }}` under the checkout in `documentation-gates.yml`
  (keep `fetch-depth: 0`). The recorded state describes the head; Workflow's gate already does this.
- evidence: reproduction above; `documentation-gates.yml:17-19`.
- saving: removes a false red check on every PR whose base moved after `record`, and the re-record or
  rebase it forces (one Document or Update rerun, 12 KB of instructions plus the build, per occurrence).
- effort S; risk low.
- consumer impact: `assure_init.py:95` never rewrites an existing workflow file. Migration: init (and
  Workflow `upgrade`, which does not install this file in managed projects) replaces the file when its
  bytes equal a known earlier render; otherwise print a one-line diff hint. CHANGELOG "Migration" block.
- tests: `workflow/tests/test_ci_policy.py` asserts the rendered `ref:`; a freshness test that builds the
  merge-commit history above and expects `current` at the head.
- verdict: **fix-first**.

### AU9. Init edits only what it owns

- what: when `assure-config.yml` exists, substitute the three `lifecycle` lines in its text (same regex
  approach `config_text` uses on the template), then reparse and check the postcondition; write
  `extensions.yml` only when `changed > 0`.
- evidence: reproduction; `assure_init.py:89-91`.
- saving: no lost consumer settings; no spurious diff in a committed file.
- effort S; risk low (the postcondition already exists, `assure_init.py:64-69`).
- consumer impact: none; the file shape is unchanged.
- tests: `workflow/tests/test_assure_init.py`: custom `scan.exclude` survives a rerun in both modes; a
  same-mode rerun leaves `extensions.yml` bytes identical.
- verdict: **fix-first**.

### AU10. Init never overwrites a page

- what: guard `docs/<lang>/index.md` with `if not exists`, as module pages are; drop the dead
  `title = product if language == "en" else product` (`init_manual.py:172`). Add the first test of
  `init_manual.main()`.
- evidence: reproduction; `init_manual.py:178`.
- effort S; risk low. Upstream: the same edit in portable `user-manual/scripts/init_manual.py` (dev-tools
  release) so the two copies do not drift further.
- tests: `user-manual/tests/test_init_manual.py` (new): an existing index survives; a fresh run writes the
  stub, modules and CSS.
- verdict: **fix-first**.

### AU11. Scan what git tracks, one listing per directory

- what: inside a git work tree, prune directories that `git ls-files --cached --others --exclude-standard`
  never reaches (one call, 0.09 s for 1,327 paths here), keep `scan.exclude` as an extra filter and the
  plain walk outside git. Replace the 35 `glob` calls per directory with one `os.listdir` plus `fnmatch`.
  Add `.venv`, `venv`, `target`, `vendor`, `Pods`, `.gradle`, `__pycache__` to the template for non-git use.
- evidence: reproduction; `assure_scan.py:95-96,135-148`. Timing on this repo's 201 directories:
  globs 0.557 s, listdir plus fnmatch 0.103 s.
- saving: correct inventory; scan time about -80% (0.48 to about 0.1 s here; on a tree with an unignored
  `.venv` of 10,000 directories, about 24 s at the measured 2.4 ms per directory).
- effort S to M; risk low to medium: the memory block changes once where bogus rows existed, which rewrites
  `project-memory.md` and stales recorded document and manual states once (it is a freshness input).
- consumer impact: one-time block change; CHANGELOG line.
- tests: `assure/tests/test_assure_scan.py`: ignored `.venv` and `target` rows absent; untracked new project
  present; non-git fallback still honours `scan.exclude`.
- verdict: **fix-first** (the git pruning), **do** (the listdir change in the same edit).

### AU12. Name the User Manual task marker

- what: Analyze step 6 names `<!-- user-manual-tasks:start -->` and `<!-- user-manual-tasks:end -->` and
  says to replace the block on rerun, as Assure does with `qa-prepare`.
- evidence: `speckit.user-manual.analyze.md:42`.
- effort S; risk low. Upstream: none (the command is sanduq's).
- tests: `user-manual/tests/test_commands.py` asserts both markers.
- verdict: **fix-first** (enables AU16).

### AU13. Command text survives Spec Kit's rendering

- what: (a) replace "Its `scripts/` are under `...illustrate/skill/scripts/`" with full script paths in
  both commands; (b) `--check` prints the summary rows and the `would write` line, and the block only with
  `--show-block` (left undone in round 3, `round-3-notes.md:226`); Analyze step 1 already says to read the
  inventory, not the block.
- evidence: AU13a emulation; `assure_scan.py:224-226`; 2,347 of 3,319 bytes.
- saving: 2,347 B of tool output per Analyze run (27% of Analyze's 8,773 B instruction base, a different
  base, so quoted separately).
- effort S; risk low.
- tests: `test_commands.py` in both extensions runs the pinned rewrite (copy of `rewrite_project_relative_paths`
  in the test, or a check that no command has a bare `` `scripts/` `` token); `test_assure_scan.py`
  `--check` omits the block, `--show-block` prints it.
- verdict: **do**.

### AU14. Update builds archives only when something publishes them

- what: Update step 8 runs `build_manual.py --all` and adds `--archive` only when `manual.yml` names an
  approved provider (the only local consumer of the bundle; CI builds its own, `user-manual-preview.yml`).
  Release keeps `--archive`.
- evidence: `speckit.user-manual.update.md:57`; measured `--all --archive` 40.6 s vs `--all` 25.2 s.
- saving: about 38% of the Update build time (15.4 of 40.6 s on the sample; zip time grows with site size,
  each Material edition is about 3 MB).
- effort S; risk low.
- consumer impact: `User-Manual/site/<v>/*.zip` stop appearing after a local Update (they are build output,
  not committed, `manual_state.py:15` excludes `site`).
- tests: `user-manual/tests/test_commands.py` text assertion.
- verdict: **do**.

### AU15. Quiet builds

- what: `build_edition` captures the MkDocs or Zensical output and prints its tail only when the build
  fails (`build_manual.py:299`). Upstream change (vendored `build_manual.py`), then a vendor sync.
- evidence: 7,218 B of output for 6 editions, of which the 6 result lines are about 1 KB; the rest is the
  Material "MkDocs 2.0" banner and INFO lines per edition.
- saving: about 6 KB of tool output per bilingual Update or Release, about 3 KB English-only.
- effort S; risk low (failure output kept).
- tests: upstream `test_build_manual.py`: success prints one line per edition; a failing build shows the
  renderer's error.
- verdict: **do** (upstream dev-tools release first).

### AU16. Make AU3's skip survive the User Manual hook

- what: for the `analyze` kind, `sanduq_freshness.fingerprints` drops the `user-manual-tasks` block (AU12)
  from `tasks.md` before hashing, as it already normalises checkboxes (`sanduq_freshness.py:36-37,91-97`).
  Manual tasks do not change QA coverage.
- evidence: documented order `install-by-host.md:105-106` installs Assure first, so its `after_tasks` hook
  records, then User Manual's adds tasks; reproduced: a status after appending a manual task line returns
  `stale-input-or-output changed_inputs=1`, so `before_implement` reruns Analyze in full.
- saving: one full Analyze per feature for standalone users with both extensions (8,773 B instructions plus
  10 to 18 tool calls, round-3 count), when the user accepts the optional `after_tasks` hook. Managed
  projects run `qa_analyze` once: no change.
- effort S; risk medium: an analyze state recorded over a `tasks.md` that already holds the block goes
  stale once; the helper is shared, so Workflow and both packages bump together.
- tests: `workflow/tests/test_freshness.py`: a manual block edit keeps analyze current; a QA task edit
  still stales it; the document and manual kinds unchanged.
- verdict: **do**, after AU12.

### AU17. One-line dependency handling

- what: `deps.py` adds the approval route to its non-zero line (`; after the user agrees, re-run with
  --approve` under `prompt`, `; the user runs it` under `manual`). Each command's block becomes one sentence:
  run `deps.py ensure illustrate`; on non-zero, report the line, skip diagrams and follow it.
- evidence: blocks of 721, 715, 463 and 455 B (`assure analyze.md:44-55`, `document.md:33-44`,
  `user-manual analyze.md:32-38`, `update.md:44-49`); the message lacks the route (`deps.py:468`).
- saving: about 1.7 KB across the four commands, about 0.55 KB per Assure run (6% of Analyze).
- effort S; risk low. Shared surface: `deps.py` also ships in PR, so R4 and R6 agree on the wording.
- tests: `extensions/scripts/tests` deps cases for both policies; `benchmark_instructions.py` before/after.
- verdict: **do** (owner: shared-scripts stream).

### AU18. Assure skill carries rules, not routes

- what: Analyze and Document stop loading the routing half of `SKILL.ext.md` (lines 11-16 repeat the
  commands; rule 1 repeats the feature resolution both commands state). Keep rules 2-7 and point rule 7 and
  `documentation.md:6` at `.specify/extensions/assure/scripts/` (they say `scripts/`, which from the skill
  folder does not exist).
- evidence: `SKILL.ext.md` 1,990 B read by both commands (`analyze.md:40`, `document.md:29`).
- saving: about 700 B per Analyze or Document run (8% and 6%).
- effort S; risk low (the skill has no host registration, round 3 Lens 4).
- tests: `validate_skills.py`, `check_docs.py`, benchmark.
- verdict: **do** (small; ship with AU13 and AU17 as one text pass).

### AU19. Status does not walk the manual

- what: `sanduq_freshness.cli` computes `default_outputs(root)` only for `record`; `status --summary` prints
  `outputs=` only for record (it prints 0 for every Assure status today).
- evidence: `sanduq_freshness.py:170`; `manual_state.py:15` walks all of `User-Manual/` on every status
  (PR preflight, Workflow Ready `workflow.py:2384-2393`, CI, `manual_impact.py:83-88`).
- saving: one full `rglob` of the manual per status call (grows with screenshots); not measured on a large
  manual.
- effort S; risk low (status already ignores the list, `sanduq_freshness.py:113`).
- tests: `user-manual/tests/test_manual_state.py`, `workflow/tests/test_freshness.py` (summary text).
- verdict: **do**.

### AU20. Config keys that do something

- what: drop from `assure-config.template.yml` the keys nothing reads: `freshness.policy`,
  `freshness.state_directory`, `output.directory_name` (paths are fixed, `assure_state.py:45`,
  `document.md:110-113`), and say in a comment that the `before_implement` hook, not
  `require_analyze_before_implement`, is the analyze gate (that key and `mode` are written by init and read
  by nothing; grep). Stop vendoring `user-manual-config.template.yml`: nothing reads it here or upstream, and
  Spec Kit deploys config templates only when a manifest declares them (neither does).
- evidence: grep over `extensions/` and sanduq-skills; `vendor.lock.json` user-manual map.
- saving: 896 B per user-manual package; no setting that silently does nothing.
- effort S; risk low. Upstream: delete the template in dev-tools (or keep it there and drop only the map).
- consumer impact: existing `assure-config.yml` keeps the keys harmlessly; `assure_init.config_text` keeps
  its postcondition on the three lifecycle keys.
- tests: `test_assure_scan.py` template test; `vendor.py check`; `test_package_exclusions.py`.
- verdict: **do**.

### AU21. PR reads the gate through the script

- what: PR's QA preflight decides "contains `require_document_before_pr: true`" by reading the file
  (`pr/commands/speckit.pr.generate.md:67-68`). Replace with
  `assure_state.py status --kind document --gate --summary --feature <f>`: `skipped gate=off` means skip.
  The comment-aware parse (AU5) then applies to PR too.
- evidence: the same heuristic AU5 removed from the script, now in prose.
- effort S; risk low. Owner: R4 (PR file); interface owned by Assure (no change needed).
- tests: `pr/tests` command text assertion.
- verdict: **do** (hand to R4).

### AU22. Vendor `init_manual.py` instead of owning a copy

- what: the extension copy differs from portable in four hunks (import fallback, `lifecycle.impact_scope`,
  `load_ci(root)` vs `--ci-policy`, no `tools/` copies). Upstream accepts `--project-root` for `load_ci`,
  `--no-tools`, and writes `impact_scope`; then map it in `vendor.lock.json` with one rewrite.
- evidence: `diff` of dev-tools-v1.2.0 portable vs `extensions/user-manual/scripts/init_manual.py`; AU10 had
  to be found in both.
- effort M; risk medium (portable CLI change, upstream release).
- verdict: **defer** (do AU10 in both copies now).

### AU23. CI selection for injected files

- what: `extensions/workflow/scripts/sanduq_{hash,ci}.py` ship inside both packages (`package.py:67-74`),
  but a change there selects only workflow and scope (`ci_matrix.py:43-44`). Add a path rule that also
  selects assure and user-manual (27 s together).
- effort S; risk low. Owner: CI stream.
- verdict: **do** if the CI stream touches `ci_matrix.py` anyway, else **defer** (Workflow's
  `test_freshness`/`test_ci_policy` cover most of it).

### Considered and not proposed

- **Parallel edition builds** (6 sequential MkDocs runs of about 4.2 s, `build_manual.py:355-359`): upstream,
  needs isolated temp roots per edition; **defer** until a manual large enough to matter is measured.
- **Scaffold duplicates.** Init copies `extra.css`, `rtl.css`, `print.css` into `docs/<lang>/assets/
  stylesheets/` for the scaffold `mkdocs.yml`, which `build_manual.py` never reads (it writes its own config
  and takes CSS from `User-Manual/theme/`, `build_manual.py:151-156,260-273`). Two sources of one stylesheet;
  only local `mkdocs serve` uses the copies. The RTL files repeat about 300 B (the LTR code rule and
  `body` direction). Total theme CSS is 4,215 B. **Drop**: too small, and vendored.
- **Duplicate tasks normalisation** (`sanduq_freshness.py:91-97` recomputes what `fingerprints` did, with an
  inner `import re`): it differs only for byte-sensitive `tasks.md`, so removing it changes hashes in rare
  cases. **Drop** unless AU16 rewrites that function anyway (then fold it in).
- **Three front-matter parsers** in User Manual (`manual_impact.py:28`, vendored `audit_manual.py:24` and
  `build_manual.py:23`): importing vendored internals couples to upstream. **Drop**.
- **`audit_manual.py` link check** reads `[t](a%20b.png)` and `[t](p.md "Title")` as missing (no decode, no
  title split, `audit_manual.py:100-105`); `build_manual.py:78` decodes. Upstream fix, low frequency.
  **Defer**, report upstream.
- **Merging the state wrappers or the two extensions:** 52 and 24 lines, shared body already in
  `sanduq_freshness.cli`. **Drop** (user decision, O5 A1).
- **Smaller injected helpers** (`deps.py` 26 KB, `sanduq_ci.py` 14 KB per package; upstream portable
  `sanduq_ci` is 8.8 KB): X9/R6. **Defer**.

## 5. Recommended do-list

1. Fix first, one Assure release and one User Manual release: AU8, AU9, AU10, AU11, AU12, and AU13 (a).
2. Same releases: AU13 (b) `--show-block`, AU14, AU19, AU20, AU18.
3. Shared surfaces, one owner each: AU16 (`sanduq_freshness.py`, with Workflow), AU17 (`deps.py`, with PR),
   AU21 (PR stream), AU23 (CI stream).
4. Upstream dev-tools release: AU15, the AU10 portable edit, AU20 template removal; then `vendor.py sync`.
5. Defer AU22, parallel builds, the `audit_manual.py` link fixes.

Measure after: `benchmark_instructions.py` (AU13, AU17, AU18), `assure_scan.py --check` bytes and time
(AU11, AU13), `build_manual.py` time and output bytes on the same 4-page sample (AU14, AU15).

## 6. Not verified

- AU8 on GitHub itself; reproduced with a local merge commit shaped like `refs/pull/N/merge`.
- AU13a rendering through a real `specify extension add`; emulated with the pinned function bodies.
- AU16 hook order on a live Spec Kit install; inferred from append order and the documented install list.
- AU19 on a large manual; AU11 timing on a large tree (extrapolated from 2.4 ms per directory).
- MkDocs timings are one machine (Windows, loaded); PDF (`--pdf`) not measured.
