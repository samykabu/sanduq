# Round 4 review: cross-cutting (stream R6)

Read-only review, 2026-10-20, worktree `sanduq-round4` (branch `feat/round-4`, base b482e06, Workflow 1.16.0).
Spec Kit facts are read at the CI pin 8147943 (`git show 8147943:<path>` in `../spec-kit`). CI numbers come from
`gh run view --json jobs` and one job log. Published archives were fetched with `gh release download` into a
scratch folder. Local builds used `package.package(name, output=<scratch>)`. Local test times were taken on this
Windows 11 machine with Python 3.11, one process per module. Nothing in the tree changed except this file.
Option numbers continue after round 3 (X1-X9).

## 1. Summary

- Round 3's CI work held. PR wall time is now 11.6-18.7 min (it was 46-47), and runner time is 46-92 min per run
  (it was 113-122). Two new limits now set the wall time:
  - **Self-hosted Linux capacity.** At most 4 `homek8-general` jobs run at once, and a full run has 18 Linux
    jobs. Jobs wait up to 8 min to start. On push 39412785282 the wall time was 14.6 min, but the longest job
    took 6.2 min.
  - **Uneven Windows shards.** The workflow shards took 2.0, 5.1, 4.9 and 10.7 min on PR 39411311648. They are
    split by file size. Local times confirm that shard 4 holds the slow modules.
- On the self-hosted runners, `setup-python` downloads CPython in every job. That costs 9.8-15.6 runner-min per
  run, more than the test suites (7.0-7.6).
- Playwright is installed in every Illustrate job (1.7-2.2 min on Linux, 3.3-3.9 on Windows). Since round 3's
  X6, nothing that runs by default uses it.
- Verified defects:
  - Scope parses the origin with its own regex. It refuses valid remotes that Workflow accepts, and it binds
    `https://evil.example/github.com/acme/app` as `acme/app`.
  - The install guide says catalog priority 10 puts Sanduq "ahead". In Spec Kit, the lower number wins.
  - Smaller items: a stale docs requirement row, a stale README version, old "(unreleased)" headings, three
    `gh` calls without a timeout, and CRLF in local Windows packages.
- D4 needs one new shared file, injected like `deps.py`. X7 (backup pruning) can go ahead: the rename it waited
  for was dropped, and no rollback reads the zips. A general X9 I/O module is still not worth building. Only the
  remote normaliser has a real cross-extension need.

## 2. Design input for decided items

### D2. Docs note on the community `scope` and `memory`

Facts:

- `catalog add` writes `.specify/extension-catalogs.yml` (`extensions/catalog/command_add.py:16-110`).
  While that file exists, it replaces the built-in default and community stack
  (`extensions/__init__.py:3848-3915`). So the README quick start leaves Sanduq as the only catalog, and
  `add scope` and `add memory` work.
- The defaults come back only when the user lists them in that file again. `SPECKIT_CATALOG_URL` replaces
  every catalog, Sanduq's too. Built-in priorities are default 1 and community 2, with community at
  `install_allowed: False`.
- The first catalog in priority order wins an id (`__init__.py:4126`). With Sanduq at 10, `extension add`
  refuses (`command_add.py:181-202`). `extension update` skips it without an error ("Updates not allowed from
  'community' (skipping)", `_command_update_discovery.py:92-98`). `update` reads the catalogs only, so
  `--from` is not remembered. `add --from` asks for confirmation (`command_add.py:73-91`). `add --force` removes
  the extension first (`__init__.py:2158-2170`), so it is not an update route.
- **Reproduced** with the local `specify 1.1.4.dev0` in a scratch project listing default 1, community 2 and
  Sanduq 10. `info memory` shows "Spec Kit Memory (v0.3.0)", and `add memory` refuses ("Discovery-only catalogs
  are intentionally not installable"). With Sanduq at 1, `info memory` shows "Sanduq Memory (v2.4.0)" and
  `info scope` shows "Speckit Scope (v1.9.0)".
- The docs today:
  - `docs/start/install-speckit.md:39-40` says "Priority 10 puts it ahead of other catalogs". This is wrong (C2).
  - `docs/extensions/scope.md:28` names the collision but gives no route.
  - Memory's pages say nothing. Memory users are the most exposed, because Workflow never installs Memory.

Placement. Write the text once and point to it, so no paragraph is copied:

1. **Canonical:** replace `install-speckit.md:39-40` with the subsection below.
2. **Pointers:** one linked sentence under the `catalog add` line in `README.md:81`, in `docs/extensions/scope.md`
   (replacing lines 28-29) and in `docs/extensions/memory.md` "Setup". `check_docs.py` already checks the anchors.
3. **Upgrades:** one line in `docs/start/upgrades.md` "One extension", saying `update` skips these two when the
   community catalog wins.

Proposed text:

> `catalog add` writes `.specify/extension-catalogs.yml`. While that file exists, Spec Kit reads only the
> catalogs it lists, so after this command Sanduq is your only catalog.
>
> ### If you keep Spec Kit's default catalogs
>
> If that file also lists Spec Kit's `default` and `community` catalogs, the catalog with the **lowest**
> priority number wins when two catalogs publish the same ID. The community catalog (priority 2) publishes
> unrelated extensions called `scope` ("Spec Scope") and `memory` ("Spec Kit Memory") for discovery only. With
> Sanduq at priority 10, `specify extension add scope` or `add memory` refuses to install, `search` and `info`
> show the other product, and `specify extension update` skips the extension without an error.
>
> Register Sanduq ahead of the community catalog, so install and update both find Sanduq's package:
>
> ```bash
> specify extension catalog remove sanduq
> specify extension catalog add --name sanduq --priority 1 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
> ```
>
> For a one-off install, use `download_url` from the [catalog](../../catalog.json):
> `specify extension add memory --from https://github.com/samykabu/sanduq/releases/download/memory-v<version>/memory.zip`.
> Spec Kit asks you to confirm. `update` still reads the catalogs, so it keeps skipping that extension.
>
> The Workflow installer is not affected. It installs Scope from Sanduq's release and refuses a package with
> the same ID from another repository. `SPECKIT_CATALOG_URL` replaces every catalog, Sanduq's too.

Notes for landing:

- `--priority 1` ties with `default` at 1. The sort is stable (`catalogs.py:190`), so file order decides. The
  default catalog does not list `scope` or `memory` today.
- `catalog add` refuses a second entry with the same name and different fields (`command_add.py:71-90`). That is
  why the text removes the entry first. `catalog remove` exists at the pin.
- Tests: `check_docs.py` (links and anchors).

### D4. One shared remote normaliser (packaging side)

**File.** `extensions/scripts/shared/sanduq_remote.py`, stdlib only, because Project is stdlib only
(`project_sync.py:7`). It holds:

- `_strip_dotgit`, `_normalize_path_remote` and `normalize_remote_url`, moved verbatim from
  `workflow.py:360-441`.
- `github_repo(url) -> str | None`: the `github\.com(?::\d+)?/([^/]+/[^/]+)` match that
  `workflow.github_repository` (`:312-330`) and `project_sync.github_repo` (`:106-119`) both repeat.
- Optional: `origin_url(root)` (`git config --get remote.origin.url`). Workflow keeps its memo wrapper
  (`workflow.py:455`). Scope reads `git remote get-url origin` (`scope.py:525`), which applies `insteadOf`
  rewrites, so Scope and Workflow can compare different strings. One reader removes that difference (R2).

**Injection.** It follows the same pattern as `deps.py`. Add one rule in `package.py:63-84` that ships
`scripts/sanduq_remote.py` to `workflow`, `project` and `scope` (Scope only if X10 is taken). Importers use the
existing fallback (`execution_tools.py:32-36`):

```python
try:
    import sanduq_remote
except ModuleNotFoundError:  # source tree; the packaged copy sits next to this file
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_remote
```

- `workflow.py` re-exports `normalize_remote_url`, so about 40 test references keep working.
- `project_sync.py` deletes its copy (`:65-103`), `WORKFLOW` (`:33`) and the `exec_module` of `workflow.py`
  (`:106-119`). That load costs about 0.3 s cold: 293 ms on the first exec, 324 ms cumulative in `-X importtime`,
  mostly PyYAML and packaging. When either package is missing, the load fails and silently falls back to the copy.
- Optional, same size: turn the four `if extension in (...)` rules into one `{source: (extensions...)}` table.
  Tests and X23 can then read one list. Keep the skip-when-missing behaviour, because `test_release.py` packages
  fixture roots that have no shared folder.

**Tests that prove one source:**

1. **Archive bytes** (extend `test_package_deps.py`). Each consumer archive has
   `<ext>/scripts/sanduq_remote.py`, byte-identical to the source, and listed in `package-inventory.json`.
2. **One definition.** An AST scan of `extensions/*/scripts/**/*.py`, excluding vendored `illustrate/skill`,
   finds `def normalize_remote_url` only in the shared file. No script `exec_module`s an installed `workflow.py`.
3. **Identity.** `workflow.normalize_remote_url is sanduq_remote.normalize_remote_url`. The same holds for
   `project_sync` and `scope`.
4. **Installed layout.** Unzip the project archive alone, with no Workflow present. `github_repo('git@github.com:a/b.git')`
   returns `'a/b'`, and it does the same with a broken `workflow.py` in place. This replaces
   `test_project_sync_summary.py:231-234`, which pins the opposite behaviour.
5. **Behaviour.** The parity cases at `test_project_sync_summary.py:229` and Workflow's identity cases run once
   against the shared module, plus the C1 cases.

**Consumer impact:** none. Each package ships its own copy, so Project and Workflow need not upgrade together.
A later change to the file must bump every consumer. Today that relies on review, as it does for `deps.py` (X23).

## 3. X9 / SC8 across extensions

| Kind | Where | Errors | Timeout |
| --- | --- | --- | --- |
| remote parse | `workflow.py:385`; `project_sync.py:78` (copy); `scope.py:526` (own regex) | 3 shapes | - |
| `gh api` wrapper | `scope.GitHub` (`scope.py:245,337`), `decisions.GitHub` (`:43`), `task_issues.GitHub` (`:88`), `project_sync.gh_raw/rest` (`:41,162`), `pr_publish.gh/run` (`:56,64`), `ci_evidence._run` (`:47`), `install.required_gate_checks.api` (`:306`), `release.gh_json` | 8 codes | 30, 30, **none**, 120, 120, **none**, **none**, none |
| GraphQL-to-REST fallback | Scope `GitHub` + `ProjectRest` (reset time, masked-owner check); `project_sync.use_rest` (remaining <= 0 only); `decisions` borrows Scope's | 2 designs | - |
| `git()` | `workflow.py:242` (drops the W1 memo), `project_sync.py:54` (returns `''`), `memory/git_state.py:52`, `shared/evidence_snapshot.py:25`, `shared/sanduq_freshness.py:19`, `sanduq_hash.py:14`, `source_key.py:88` | 6 types | Project only |

Proposal:

1. **`sanduq_remote.py`. Do now** (D4 + X10). Workflow and Project move first, because D4 decides it. Scope
   follows in the same release because of C1. PR's `pin_images` uses `gh repo view` (`pr_publish.py:113`), not
   the bound repo; that is R4's call. The risk is low: the code moves unchanged and its test cases stay pinned.
2. **Timeouts where missing. Do now** (X21). One keyword per call site. No module is needed.
3. **`sanduq_gh.py`. Defer.** If R2 or R4 need it later, the interface is
   `api(endpoint, *, method='GET', payload=None, pages=False, timeout=60, cwd=None)`. It returns parsed JSON with
   pages flattened and raises `GhError(returncode, stderr)`. Callers map that to their own codes. The rate-limit
   fallback stays in Scope, which has the complete one. `task_issues`, `decisions` and `install` would move first;
   they are all Workflow files, so no injection is needed. It saves about 40 lines. The risk is the test seams
   (`FakeGitHub`, `run`).
4. **Shared `git()`. Drop.** Each copy is 5 lines with its own pinned error contract, and Workflow's copy carries
   the W1 cache invalidation.

R2 and R4 have not sent needs to this stream. The interfaces above match what their files call today, so check
them in the cross-check.

## 4. Correctness defects (verified)

| # | Defect | Evidence | Effect |
| --- | --- | --- | --- |
| C1 | Scope's origin parser differs from Workflow's | `scope.py:525-528`. Both parsers were run on the same inputs. `https://github.com/acme/app/`, `https://GitHub.com/acme/app.git`, `ssh://git@github.com:22/acme/app` and `ssh://git@github.com/acme/app.git/`: Scope `None`, Workflow `acme/app`. `https://evil.example/github.com/acme/app`: Scope `acme/app`, Workflow `None`. With no origin, `check_output` raises `CalledProcessError`. | Valid remotes are refused. A non-GitHub remote is bound to a GitHub repo |
| C2 | The install guide has catalog priority backwards | `install-speckit.md:39-40`; `command_add.py:20` ("lower = higher priority"); reproduced in §2 | Advice that leaves the community packages winning |
| C3 | Stale requirement row | `docs/extensions/scope.md:12` "Workflow 1.8 or later"; the manifest says `>=1.13.0,<2.0.0` | Wrong compatibility promise |
| C4 | Stale README version | `extensions/scope/README.md:8` "describes Scope 1.8.0"; the manifest says 1.9.0. The file ships in the package | Wrong version shown |
| C5 | Old "(unreleased)" headings | `assure/CHANGELOG.md:102` (2.1.0), `project/CHANGELOG.md:50` (2.1.0), `user-manual/CHANGELOG.md:149` (1.1.0); X2 checks only the root changelog | Cosmetic |
| C6 | `gh` calls with no timeout | `task_issues.py:92`, `ci_evidence.py:48`, `install.py:307` | A stalled `gh` hangs a stage or an install |
| C7 | Local Windows packages differ from CI packages | No `.gitattributes` rule covers `*.txt` or `LICENSE`, and `core.autocrlf=true`. Rebuilt inventories were compared with all nine published archives: only `LICENSE` and `requirements*.txt` differ, in five extensions. Zip sha256 also differs across zlib versions when every member is identical. | "Reproducible" holds only for CI builds. Nothing depends on it today (`package_digest` hashes installed files, `workflow.py:1212`) |

Checked and found fine:

- The release job stages `CHANGELOG.md` (`release-extensions.yml:84`).
- `promote` writes exactly four files (`release.py:224-229`).
- Tests that call `bash` skip the System32 launcher (`test_project_sync_summary.py:317`, `test_archive.py:799,879`).
- Published inventories equal the source apart from C7, so no shared-file change has shipped half-way.

## 5. Measurements

### CI after round 3

| Run | Event | Wall | Runner-min | Longest jobs (min) |
| --- | --- | ---: | ---: | --- |
| 39411311648 | PR #100 | 11.6 | 74.3 | win workflow 4/4 10.7, win memory 8.3, linux workflow 6.7 |
| 39344703912 | PR #98 (2 files) | 12.4 | 60.3 | win memory 11.9, win workflow 2/4 9.2 |
| 39340432518 | PR #97 | 18.7 | 91.9 | linux illustrate 13.9 (render lint 10.7), win memory 13.3 |
| 39359728801 | nightly | 18.6 | 90.6 | linux illustrate 13.5, win memory 11.8, win workflow 4/4 9.5 |
| 39412785282 | push | 14.6 | 46.3 | linux workflow 6.2 |

- **Windows workflow shards** (1/2/3/4, min): 2.0/5.1/4.9/10.7, 2.4/7.4/3.8/9.3, 2.4/9.2/3.2/6.0 and
  2.1/9.1/2.5/9.5. They sum to 21-23 min, so even shards would take about 5.5-6 min each.
- **Self-hosted Linux:** at most 4 jobs run at once. The median start delay after `changes` is 3.1-3.5 min, and
  the worst is 7.7-8.3. Windows jobs start within 0.1 min.
- **Linux runner-min by step** (three runs): setup-python 13.4 / 15.6 / 9.8, suites 7.6 / 7.0 / 7.0,
  Playwright 1.7 / 2.2 / 1.8, other 11.0 / 11.1 / 20.8. The log of `regression (ubuntu-latest, memory)` in
  39412785282 says "Version 3.13 was not found in the local cache", followed by a 2 min 15 s download.
- **Illustrate:** the suite step takes 0.1 min. Its two test modules do not use Playwright. Even so, every
  Illustrate job installed it: 3.3 min on Windows, and 0.6 min plus a 1.1 min cache restore on Linux.
- **Path filter:** `ci_matrix.py --files .github/workflows/release-extensions.yml CHANGELOG.md` selects every
  suite, because any `.github` path runs everything (`ci_matrix.py:85-86`). PR #98 ran 27 jobs for a one-line
  fix. No suite reads the three non-CI workflow files. The `.github/workflows/` paths in tests are consumer
  fixtures.

### Local test runtime (Windows 11, Python 3.11)

- **Workflow suite:** 1,722 s over 55 modules. 8 modules stopped at import, because `jsonschema` was not
  installed, so their times are missing. Slowest: `test_gate_explain` 228, `test_ci_gate` 227,
  `test_delegation` 227, `test_checkpoint_identity` 206, `test_memory_handoff` 120, `test_progress_shim` 120,
  `test_workflow` 110, `test_freshness` 61, `test_hosts` 60, `test_evidence_snapshot` 49.
- **Today's size-based shards, timed locally:** 286 / 415 / 326 / 695 s. Shard 4 is the slowest, as in CI. A
  greedy split on these times gives 430 / 430 / 431 / 431 s, which is -38% on the longest shard.
- **Uniform per-test cost:** each `test_gate_explain` test takes 15-22 s. Its `ready()` claims and completes
  every stage up to PR (`test_gate_explain.py:30-45`). `test_ci_gate` (13 `ready()` calls) and
  `test_receipt_contract` (7) use the same pattern.
- **Memory suite:** 898 s. `test_archive` alone is 593 s (66%), then `test_archive_v2` 169 and
  `test_memory_delta` 46.
- **D5:** retiring `progress_shim.py` also removes `test_progress_shim` (120 s, 7% of local workflow time).

### Packaging and install

- Zip / raw KB: workflow 551 / 1,462, illustrate 2,724 / 9,521, progress 153 / 442, memory 105 / 323, scope
  96 / 263.
- Each package ships its `CHANGELOG.md`. Workflow's is 74 KB raw (28 KB zipped, 5% of the archive). Spec Kit only
  prints the catalog's changelog URL (`command_info.py:220`), and no Sanduq script reads the file.
- No code reads `before.zip`. Rollback restores from the dict that `snapshot()` returns (`install.py:827,929`,
  `upgrade.py:49,106`; host switches at `hosts.py:549`).
  - An upgrade writes two zips: one for `upgrades/` and one for the inner install.
  - Smoke projects from 2026-10-18 hold six zips of 5.2-5.4 MB each (about 32 MB).
  - The same folders hold alias backups of replaced skills (`test_hosts.py:436`). Those are consumer content.

## 6. Options

Cost bases:

- **CI:** PR wall 11.6-18.7 min, push 6.2-18.5 min, 46-92 runner-min per run, of which Linux is 36-42.
- **Install:** a consumer's `.specify/workflow/backups`.
- **Tokens:** no option changes instruction text, so the token saving is 0 for all of them.

| Id | What | Saving (base) | Effort | Risk | Verdict |
| --- | --- | --- | --- | --- | --- |
| X10 | Scope parses the origin with `sanduq_remote` (`scope.py:525-528`), keeps its message, and a missing origin becomes a `ScopeError` | Correctness: 4 refused remote forms and 1 wrong binding (C1) | S | low | **fix-first** |
| X11 | D4 as in §2 | About 60 lines; about 0.3 s per Project sync | S | low | **do** |
| X12 | D2 note, and fix the priority sentence (C2) | Memory users with the defaults get a working install and update | S | none | **do**, land first |
| X13 | Gate "Cache the Playwright browser" and "Install Playwright" (`ci.yml:218-227`) on `illustrate_vendored` | 5.0-6.1 runner-min per run that selects Illustrate without a vendor bump; Windows Illustrate job 3.8-4.5 min to about 0.6 min; wall time about 0 | S | low | **do** |
| X14 | Keep CPython 3.13 in the `homek8-general` tool cache (persistent `/opt/hostedtoolcache` or a baked image). In-repo fallback: the image's `python3`, as `lint` uses | 9.8-15.6 runner-min per run (25-40% of Linux time); about 2.5-4 min of push wall time (base 14.6) | S (cluster) | low | **do**, cluster owner |
| X15 | Weigh shards by a checked-in `{module: seconds}` table (file size as the fallback), and shard Windows memory too, by test class, because `test_archive` is 66% of it | PR critical path from 10.7 min (workflow) and 8.3-13.3 min (memory) to about 6-7 min; [0.3, 0.45] of PR wall time once X14 lands | S | low | **do** |
| X16 | Path filter for tooling: the three non-CI workflows, `extensions/scripts/tests/**`, `test_check_docs.py`, `validate_skills.py` and `vendor.py` become lint-only. `release.py` maps to workflow (`test_release.py:8`), `check_docs.py` to assure (`test_descriptions.py:12`), `benchmark_instructions.py` to scope (`test_instructions.py:40`). Add `actionlint` to lint. | A PR like #98 drops from 27 jobs and 60 runner-min to lint plus at most one suite | S | low | **do** |
| X17 | `promote` returns `written`, and a test checks that the `git add` line in `release-extensions.yml` covers every path it can write | Prevents a repeat of #98 (a second PR, about 106 runner-min) | S | none | **do** |
| X18 | Fix C3-C5. Three `check_docs.py` rules: the Requires row matches the manifest lower bounds; README "describes X.Y.Z" matches the manifest (or delete the sentence); no "(unreleased)" heading below the manifest version | Ends the remaining version drift | S | low | **do** |
| X19 | X7 revisited: after a successful install, upgrade or host apply, delete `before.zip` everywhere except the three newest across `installs/`, `upgrades/` and `hosts/`. Keep `before.json`, `result.json` and alias backups. A failed apply prunes nothing. Doctor reports the count and bytes. | At most about 12-16 MB of zips per consumer, instead of about 5 MB per apply forever | S | low | **do** (installer owner) |
| X20 | Exclude `<ext>/CHANGELOG.md` (the README link rewrite at `package.py:59-61` covers the links). Add `*.txt` and `LICENSE` `text eol=lf` to `.gitattributes`. | About 125 KB raw (about 45 KB zipped) over nine archives, also in every snapshot; local builds equal CI builds (C7) | S | low | **do** |
| X21 | `timeout=60` on the three calls in C6, each mapped to its existing error code | No hung stage | S | low | **do** |
| X22 | `sanduq_gh.py` transport; shared `git()` | About 40 lines; about 0 | M | medium | `sanduq_gh` **defer**; `git()` **drop** |
| X23 | Bump guard: `prepare` stores `inventory_sha256` in each catalog entry (Spec Kit ignores extra fields, `__init__.py:4128`). Lint fails when an unpending package's inventory changed. | Catches a shared fix that ships in only some consumers | S-M | README-only edits would need a version | **defer**: needs a maintainer policy decision |
| X24 | Pin repository actions by SHA (25 tag refs), using the SHAs from 29a4224's templates. `release-extensions.yml` and `vendor-update.yml` have `contents: write`. | A moved tag cannot push to `main` | S | low | **do**, at least the two write workflows |
| X25 | Build the walked-to-PR fixture once per class (`setUpClass`, then copy the tree per test) in `test_gate_explain`, `test_ci_gate` and `test_receipt_contract` | About 15 of 16 s per test on 33 tests: about 7-8 min locally, about 1.5-2.5 min of Windows CI runner time | S | medium (shared state between tests) | **do**, R1 owns it |

Consumer impact:

- X10: remotes that were refused now work, and a look-alike remote now fails closed.
- X19: no manual restore further back than three applies.
- X20: no local changelog under `.specify/extensions/<id>/`.
- X15: branch protection must name the new memory shard jobs.
- All other options: none.

Tests per option:

- X10: the C1 table in Scope's tests.
- X11: §2 items 1-5.
- X12 and X18: `check_docs.py`, plus one failing fixture per new rule.
- X13: first CI run, which shows the skipped steps.
- X14: two CI runs whose logs show "Found in cache".
- X15 and X16: `test_ci_matrix.py`. Every module is in exactly one shard, a module missing from the table still gets a shard, and each new path is covered.
- X17: the new test.
- X19: four applies leave three zips and four results. A failed apply prunes nothing. Alias backups survive.
- X20: `test_package_exclusions.py` and `git ls-files --eol`.
- X21: one fake per site that raises `TimeoutExpired`.
- X25: the same test count and results before and after.

## 7. Not verified

- Per-module times on the Windows CI runners. X15's table needs one run with timings. The 8 modules that need
  `jsonschema` were not timed locally.
- D2 was reproduced with `info` and `add` on the local `specify 1.1.4.dev0`, not on the pin, and `update` was not
  run.
- The number of `homek8-general` runners. 4 is the observed concurrency. The runners API needs admin scope.
- What `gh repo view` resolves in a fork with an `upstream` remote (R4, PR image pinning).
- Local timings come from a loaded workstation. Compare the ratios, not the absolute times.
