## 1. Verdict in five lines

Approve a narrower plan, with the migration design revised before implementation.  
The principal correctness defects are real; several important fixes are missing from “fix first.”  
Apply display names now; separate `scope → issue-scope` from the optimization release.  
Prioritize W1 and CI selection; treat savings percentages as estimates until remeasured.  
Defer W9, broad refactoring, and the project-init rewrite.

## 2. Verified claims

Reviewed `feat/round-3` at `8465c98`. Paths below are relative to Sanduq unless prefixed **Spec Kit**.

| Claim | Assessment | Evidence |
|---|---|---|
| Assure’s fallback enables a parsed `false` when its comment contains `true` | **Verified** | `extensions/assure/scripts/assure_state.py:15–30`. An in-memory check supplying a successfully parsed `False` returned `True` for `false # set to true`. |
| QA audit rejects permitted placeholders | **Verified** | `extensions/assure/scripts/audit_qa.py:78–80` lacks `extensions/user-manual/scripts/audit_manual.py:96–99`’s exclusions. Checks reproduced findings for all three supplied placeholder forms. |
| QA audit mishandles encoded and root-relative links | **Verified** | `audit_qa.py:70–75` joins the undecoded URL path directly to the document directory. A mocked existing `a b.png` was reported missing for `a%20b.png`. Root-relative URLs likewise lack web-root resolution. |
| Diagram instructions bypass the common theme/check procedure | **Verified** | `extensions/assure/commands/speckit.assure.document.md:121–125`; `extensions/user-manual/commands/speckit.user-manual.update.md:46–48`; compare `extensions/illustrate/skill/SKILL.md:16–33,55–62`. This proves missing instructions, not that every resulting diagram is necessarily unthemed. |
| Illustrate’s opt-in hook is registered unconditionally | **Verified** | `extensions/illustrate/extension.yml:34–38`; runtime opt-in is checked later in `hooks/self_check_hook.py:21–32`. |
| Illustrate covers Codex writes and costs 223 ms per event | **Partly** | Its matcher excludes `apply_patch`; `self_check_hook.py:35–46` also requires a dictionary containing `file_path` or `path`. The advertised Codex patch path is unsupported. I did not reproduce the timing. |
| PR publishing preserves broken relative image paths | **Verified** | `extensions/pr/scripts/pr_publish.py:114–124` copies document content unchanged before linting. The image contract requires verified remote assets in `references/pr-image-embedding.md:16–30`. |
| Project sync repeats Workflow’s remote-parser bug | **Verified** | `extensions/project/scripts/project_sync.py:371–374,156`. Checks produced `acme/my` for `acme/my.app.git` and **`443/acme`** for `ssh://git@github.com:443/acme/app.git`. Workflow handles these through normalization: `extensions/workflow/scripts/workflow.py:236–240,325–341`. |
| W1 repeats source hashing and identity subprocesses | **Verified** | `workflow.py:3011–3016` checks receipts individually; `:1896` recomputes source fingerprints. A mocked three-receipt probe called it three times. `Run.load` reaches `repo_identity` through `:2227,530–533`; `:408` always computes the root, including `rev-list` at `:377`. |
| Spec Kit supports command aliases but no extension-ID migration | **Verified in supplied source** | **Spec Kit** `src/specify_cli/extensions/__init__.py:703–761` distinguishes primary commands from aliases. Searches found no extension `replaces`/`renamed_from` implementation. `_commands.py:1241–1244` rejects updates whose archive ID differs. |
| `extension remove --keep-config` preserves consumer state | **Wrong if stated broadly** | **Spec Kit** `extensions/__init__.py:1568–1600`: only top-level `*-config.yml` and `*-config.local.yml` survive. JSON config and state directories are deleted. Without the flag, only those YAML files are backed up before deletion. |
| Scope has no independently installed consumers | **Unproven** | `extensions/scope/extension.yml:13–15` requires Workflow. That dependency does not establish that everyone used Workflow’s installer or follows its upgrade path. |
| Shipped examples contradict required checks | **Verified for sampled templates** | Running `self_check.py --strict` on `assets/template-full.html` failed on four off-grid rectangles. The technical-color architecture template failed the default check on toolbar handlers. I did not rerun the 296-file census. |
| Memory duplicates lifecycle actions in managed projects | **Partly** | `reconcile.py:11` excludes Memory; `memory_handoff.py:59,68,121` overlaps its commands. However, `:113–115` explicitly recognizes already-queued work. Actual duplicate execution remains unconfirmed. |
| CI over-selects suites and takes 46–47 minutes | **Partly** | Local checks returned **16 regression jobs** for README, pending-release, and project-script changes. `.github/workflows/ci.yml:266,321,347,369` leaves four job groups ungated. GitHub access was blocked, so historical durations remain review-reported evidence. |

## 3. Answers to the five questions

1. **Are the fix-first items accurate?**  
   Mostly. Move PM6 into an investigation gate. Add PM3’s publication failures, AU5’s unstable scan date, W5’s missing guard-approval warning, and the sampled template/check contradictions. X2 and W8 are cleanup priorities, below these defects.

2. **Is `issue-scope` the right single rename?**  
   Yes as a destination. It improves the name and avoids the ID collision. Recommend display names for this release and a separate compatibility release for the rename: the installer already uses explicit release URLs, reducing the urgency for managed consumers.

3. **Is the migration sound?**  
   Not yet. Its transaction boundary is a useful foundation, but preservation, compatibility-alias cleanup, hook overrides, skipped-version upgrades, and standalone installation paths need explicit handling. One successful upgrade fixture and an idempotent rerun are insufficient.

4. **Which optimizations should change?**  
   Keep W1, measured CI selection improvements, AU3, bounded instruction reads, and small deterministic helpers. Defer W9, SC8’s extraction, and PM5’s rewrite. Add PR publication hardening, stable scan output, and compatibility testing against the actual Spec Kit CI pin.

5. **Are the streams safe, and is W9 worthwhile?**  
   The streams are not disjoint. Installer, packaging, manifests, CI, and presets have multiple writers. Give each shared surface one owner. W9 has no demonstrated consumer benefit and changes patching/import behavior across many callers; defer it.

## 4. Changes wanted in the plan

### Drop or narrow

- **Replace PM5 with a small command fix initially.** Both init scripts already support noninteractive operation: Bash `project-init.sh:8,18,88`; PowerShell `project-init.ps1:13,24`. Pass the existing flags, remove unconditional interactive authentication, and report missing choices. Measure the remaining problem before rewriting 463 lines.
- **Reject X3’s “project changes run no regression suite.”** Project tests already exist at `extensions/workflow/tests/test_project_sync_summary.py`. Keep that coverage selected until PM9 moves it into a dedicated suite.
- **Remove the arbitrary 30 KB documentation failure rule.** No demonstrated defect justifies it.
- **Separate cheap deduplication from broad extraction.** AU4 may be reasonable; SC8’s transport move, W9, and X9 add integration work without demonstrated runtime savings.
- **Do not shorten worker prohibitions on the assumption that a Codex guard always runs.** W5 itself documents an approval gap.

### Add and promote

- **PM3 belongs in fix first.** `pr_publish.py:118–119` treats every PR lookup failure as absence; `:145–148` can then push. `splice:60–64` tolerates malformed markers. Workflow’s guard checks only file bodies at `hooks/guard.py:67–80`, leaving inline bodies outside that check.
- **Stabilize scan output before adding freshness shortcuts.** `assure_scan.py:207–218` rewrites the date across days; `.github/memory/project-memory.md` is not excluded by `sanduq_freshness.py:79–88`. The resulting cross-extension staleness is plausible and needs a focused regression.
- **Fix the diagram procedure and its inputs together.** AU1 restores required checks, while sampled templates already fail those checks. Prioritize IP2/IP3 alongside AU1. A baseline alone does not give consumers a clean starting example.
- **Keep gate parsing authoritative.** A successfully parsed `false` must return false. Malformed configuration needs a deliberate, tested outcome; the fallback must not reinterpret comments.
- **Correct the compatibility evidence.** The supplied Spec Kit checkout is `92b7cf7`; CI installs `8147943` (`ci.yml:257,281,330`). The latter object is unavailable locally. The supplied checkout also lacks the `specify_cli.events` module assumed by the hook review. Test migration and event wiring against the CI pin.

### Installed-consumer migration risks

- **The proposed cleanup deletes compatibility aliases.** Spec Kit renders aliases into their own named skill directories (`agents.py:701–772`). Deleting `speckit-scope-*` after re-registration deletes the newly rendered old-name aliases. Remove recognized obsolete outputs **before** rendering replacements, or reconcile against the expected new output inventory.
- **`preservation()` is narrower than the draft promises.** `install.py:285–290` keeps selected config/state paths, not arbitrary consumer files; it also misses `*-config.local.yml`. Inventory user additions and edits before removal; preserve or refuse explicitly.
- **A frozen catalog entry does not migrate anyone.** `replaced_by` is ignored. Direct `specify extension update scope` remains on the old ID. Publish an actionable upgrade route and retain old-ID recognition for consumers who skip releases.
- **One minor release is an inadequate compatibility rule.** Base retirement on an explicit support window. Normalize historical command names when reading receipts; avoid rewriting evidence merely to modernize names.
- **Test both IDs already installed, locally edited skills, customized hook flags, both host defaults, failure after removal, and upgrading past intermediate releases.** Existing snapshots are helpful, but newly touched paths must be included.
- **Compatibility aliases temporarily retain the old command namespace.** The ID rename does not immediately eliminate command collisions or catalog-description cost.

### Hook registration risks

- **Workflow-only wiring removes the standalone Illustrate path.** Give Illustrate an explicit install/uninstall interface that Workflow calls.
- **Handle existing dispatcher entries and native entries across both Codex configuration locations.** Current Progress wiring distinguishes `.codex/config.toml` from `.codex/hooks.json` (`install.py:533,625`).
- **Define removal behavior.** Spec Kit cannot clean up a native hook it does not own. Removal must not leave commands targeting a deleted script.
- **Test real host payloads**, including multiple changed HTML files and moved files. Parsing only Add/Update headers misses valid patch cases.
- **Treat Codex approval and policy-toggle activation as visible upgrade steps.** Preserve unrelated hooks and include failures in rollback tests.

### Ownership and ordering

- **One installer owner:** naming migration, SC2, IP5, IP9, X7, and host reconciliation.
- **One packaging owner:** IP6, IP8, X8, and vendored-test mapping.
- **One CI owner:** X3–X6, PM9, IP7, IP10, and project-init changes.
- **Each extension owner edits its manifest and command descriptions.** S-X integrates generated docs and release metadata afterward.
- AU6 is a **Sanduq vendoring change**; upstream already has `AllEditionsTests` at `sanduq-skills/skills/dev-tools/skills/user-manual/tests/test_build_manual.py:103`. Remove its supposed upstream implementation dependency.
- Assign PM9’s Memory fixture work explicitly; the draft assigns only its CI portion.
- Keep SC3’s narrower dependency scan behind completeness tests and a fallback. Request-count reductions do not prove that every dependent is still found.
- Rebenchmark after W1 before choosing shard sizes. Do not add overlapping savings percentages. Browser-download caches also do not establish that fresh runners have Chromium’s OS dependencies.

## 5. Final naming and ordered work

Use these display names now, retaining current IDs:

| Extension | Display name |
|---|---|
| workflow | Sanduq Workflow |
| scope | Sanduq Issue Scope |
| assure | Sanduq Assure |
| user-manual | Sanduq User Manual |
| pr | Sanduq Pull Requests |
| project | Sanduq GitHub Project Sync |
| illustrate | Sanduq Illustrate |
| memory | Sanduq Memory and Archive |
| progress | Sanduq Progress Report |

Presets: **Sanduq Managed Workflow**, **Sanduq Scope Gate**, **Sanduq GitHub Brainstorm**. Describe Workflow positively as issue-to-PR orchestration. Reserve `issue-scope` for the separately tested rename.

### Fix first

1. AU5 gate parsing; AU2 placeholder/link handling.
2. PM3 publication hardening; PM4 remote parsing, scope checks, and timeouts.
3. AU5 stable scan output; AU1 procedure restoration; IP2/IP3 template/check consistency.
4. IP5 hook correctness and migration, including standalone consumers and removal.
5. W5 approval visibility; broken invocation names and export paths; AU6 missing build coverage.

### Do

1. Correct benchmark scenarios and establish the Spec Kit compatibility target.
2. Implement W1 with operation-scoped caches and invalidation tests.
3. Fix CI selection while preserving project coverage; remeasure, then shard and cache.
4. Apply W2/W3, AU3, SC1, SC4, IP1, IP4, and shorter descriptions.
5. Add small receipt/analysis/plan helpers: W4, SC5, SC6, SC9.
6. Implement PM1 before linting the final PR body; retain explicit verification failures.
7. Reduce SC3 calls with dependency-completeness tests.
8. Consolidate packaging exclusions and preset no-op detection; preserve required assets.
9. Add release-version consistency tooling, factual documentation checks, and display names.
10. Investigate PM6; change ownership only if duplication is demonstrated.

### Defer

- `scope → issue-scope` publication until the expanded migration fixtures pass; ship separately.
- W9, SC8 extraction, X9, PM5’s Python rewrite.
- SC2 preset consolidation, PM2’s reply/resolve automation, and fixture-copy optimizations pending measurement.
- Backup pruning until migration recovery requirements are settled.

### Drop

- Full ID renaming.
- Project changes receiving no regression coverage.
- Arbitrary documentation-size gates.
- Guaranteed savings percentages and the claim that no independent Scope consumers exist.

**Not checked:** full suites, real host upgrade/removal flows, and live CI timings; GitHub access was blocked.  
**Main risk:** the proposed rename cleanup and hook ownership transfer can break installed consumers unless the migration gates above are completed.

