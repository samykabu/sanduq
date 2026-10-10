# Sanduq documentation overhaul and repository split: plan

Status: **final draft for owner approval** (v2, after three-round review) · Date: 2026-10-10 · Owner: Samy K. Abushanab

This plan fixes the gaps in Sanduq's README and documentation and splits the repository so that
portable-skill users and Spec Kit users each get a clear starting point. Two independent reviewers,
Claude Fable 5.1 and Codex GPT-6 Astra, checked the findings and the plan against the repository.
Section 9 records how they reached consensus.

## 1. Decisions

| Topic | Decision |
| --- | --- |
| Repository layout | **Two repositories.** New `samykabu/sanduq-skills` for portable skills. `samykabu/sanduq` (URL unchanged) for the 8 Spec Kit extensions and presets. |
| Licenses | `sanduq-skills` is **MIT**. In `sanduq`, Scope, scope-gate and scope-brainstorm stay **MIT**; everything else stays **PolyForm Noncommercial 1.0.0**. |
| Canonical sources | **Illustrate, the User Manual skills and Delegate Task** live in `sanduq-skills`. The extensions repo vendors pinned releases of them. |
| Claude plugin marketplace | **Needs your confirmation (R1).** Recommended: keep the single `sanduq` marketplace at `samykabu/sanduq`, with entries pointing into `sanduq-skills`. See section 4.3. |
| Documentation home | Repository Markdown only, rendered by GitHub |
| Language | Plain English, a style guide and a glossary. Arabic is deferred. |
| Motion | Rich, delivered in stages. Motion never blocks a text release. |
| Hosts | Codex, Claude Code, Claude Desktop. opencode is deferred; Copilot is outside this plan's supported hosts. |
| Scope | Stays Workflow-only. Its Archify dependency is replaced by Illustrate in a **separate track (S)**. |
| "Superbrain" | Means Superpowers (obra/superpowers) |

## 2. Findings (corrected after review)

Several original findings overstated the gap: the information exists, but it is scattered across pages.
The table marks these **Consolidate**. Findings with no existing coverage are marked **Missing**.

| ID | Sev. | Kind | Finding |
| --- | --- | --- | --- |
| A1 | High | Missing | The README groups content by packaging format (skill, plugin, extension), not by product. There is no product catalog with purpose, version, standalone status and dependencies. |
| A2 | High | Consolidate | Dependencies are stated in several places (`getting-started.md`, `extensions.md`) but there is no single graph. The README's "use separately" framing contradicts Scope's hard dependency on Workflow. |
| A3 | High | Missing | Ten internal design and progress records, evidence JSON and `prototypes/` sit in the user path. |
| A4 | Medium | Missing | Skills are duplicated across `skills/` and `extensions/`. Illustrate has three version schemes: extension 2.2.0, plugin 3.2.0, READMEs 3.1.0. `plugins/README.md` and `skills/README.md` are stale. |
| A5 | Low | Missing | Authorship is inconsistent (illustration-tools is credited to "Resal Engineering"). |
| B1 | High | Consolidate | Phase hooks are documented per package, but no page shows the whole lifecycle. |
| B2 | High | Consolidate | Install paths exist. End-to-end scenarios per adoption level do not. |
| B3 | Medium | Consolidate | Hook optionality is explained thinly. Init-time changes are not explained at all: Project and Assure can make hooks required, and Workflow reconciles hooks. |
| C1 | High | Missing | No Claude Desktop guidance. |
| C2 | High | Missing | No complete list of 8 install lines and no recipes for installing a set. |
| C3 | Medium | Consolidate | Prerequisites are partly present (`gh` scopes, Node 18, the Spec Kit link). Missing: install commands, tested versions, per-OS notes, PDF libraries, and Node for Illustrate's hand-drawn generator. |
| C4 | High | Missing | User docs give no source or install steps for SuperSpec (its source is only in `extensions/workflow/dependencies.json`), the Superpowers Bridge, or Superpowers. Versions come from upstream manifests: Bridge 1.3.0 requires Superpowers ≥5.1, per `lihan3238/speckit-superpowers-bridge` `extension.yml` as installed in a consumer. |
| C5 | Medium | Missing | Compatibility is recorded as maintainer evidence, not as a user support matrix. |
| D1 | High | Missing | No glossary. Terms such as claim, receipt, dispatcher and evidence gate are never defined. |
| D2 | Medium | Missing | The prose is dense with caveats aimed at agents rather than people. |
| D3 | Low | Consolidate | Claude syntax appears in only one table. Worked narratives use Codex only. |
| D4 | Low | Missing | Arabic coverage is inconsistent. |
| D5 | Medium | Missing | The Workflow README is 1,380 lines, with guide and reference mixed. |
| E1 | High | Missing | There is no product map and no lifecycle overlay diagram. |
| E2 | Medium | Consolidate | Output screenshots exist. Terminal and session recordings do not. |
| F1 | Medium | Consolidate | The license is stated at the bottom of the README. It is not per package and not shown where users decide to install. |
| F2 | Medium | Missing | One entry point serves three audiences. |
| G1 | High | Missing | Package READMEs drift from their manifests: Illustrate lists 3 of 4 commands and about 27 of 44 types; Scope's README calls 1.5.0 pending while the catalog advertises 1.5.1. These READMEs ship inside the installed packages. |
| G2 | High | Missing | The portable User Manual copy has diverged and is **older** than the extension copy: it lacks theme support and the newer asset and privacy protections. The docs promise features the portable copy lacks. |
| G3 | Medium | Missing | Copilot is named as a host, but it is outside the supported hosts. Delegate Task's **harness** targets (codex, claude, opencode, copilot, pi) are not distinguished from **host** support. |
| G4 | Low | Missing | Per-package Spec Kit minimums differ (≥0.2.0, ≥1.0.0, <2.0.0) and are not explained. |
| G5 | Medium | Missing | `install.sh` and `install.ps1` are a third, undocumented install path, mentioned only in the Project README. |
| G6 | Medium | Missing | Moved destination pages have no forwarding stubs. Packaged READMEs need absolute links to anything outside the package. |
| G7 | Medium | Missing | The new structure has no home for troubleshooting, upgrades or changelogs. |
| G8 | Medium | Missing | Delegate Task tests and the portable User Manual scripts are not run in CI. |
| G9 | Medium | Missing | There is no per-package license table. The MIT packages (Scope and its presets) are not visible. `skills/illustration-tools/README.md` says PolyForm, and no `plugin.json` has a license field. |
| G10 | Medium | Missing | Nowhere says who enforces `requires.extensions`. Spec Kit does not; Workflow's installer and `deps.py ensure` do. |

Counts used in the plan: **42 public commands** (Illustrate has 4), **7 portable skills**, **3 plugin bundles**, **8 extensions**, **3 presets**.

## 3. Target repositories

### 3.1 `sanduq-skills` (new, MIT)

The current layout is kept so that both `npx skills` and Claude plugins keep working.

```text
sanduq-skills/
├── README.md              # product cards, install by host, 60-second start, license
├── LICENSE (MIT)  THIRD_PARTY_NOTICES.md  CHANGELOG.md
├── skills/
│   ├── illustration-tools/.claude-plugin/plugin.json   + skills/illustrate/
│   ├── dev-tools/.claude-plugin/plugin.json            + skills/user-manual*/  (5 skills)
│   └── agent-tools/.claude-plugin/plugin.json          + skills/delegate-task/
├── docs/   install/{codex,claude-code,claude-desktop}.md  skills/<one page each>
│           glossary.md  style-guide.md  troubleshooting.md  media/
├── internal/                                        # design records, not linked
└── .github/workflows/  ci.yml (Illustrate verifiers + tests, delegate-task test/run.mjs,
                        user-manual script tests, `npx skills add . --list`)  release.yml (per-bundle tags)
```

History is copied at a tag, not rewritten with `git filter-repo`. The README notes that history before
tag `X` lives in `samykabu/sanduq`.

### 3.2 `sanduq` (existing URL)

```text
sanduq/
├── README.md               # product map, lifecycle map, adoption levels, install, license table
├── catalog.json            # unchanged URL
├── .claude-plugin/marketplace.json   # if R1 is confirmed: git-subdir entries → sanduq-skills
├── extensions/<8>/         # illustrate/skill, user-manual/skills+scripts, workflow assets/delegate-task are VENDORED
├── presets/
├── vendor.lock.json        # tag + digest of each vendored input (post-transform tree)
├── docs/  start/ (prerequisites, install-speckit, install-by-host, troubleshooting, upgrades)
│          scenarios/ (4 levels)  extensions/<one page each>  workflow/ (guide)
│          reference/ (commands.md — authoritative, hooks.md, compatibility.md, licenses.md, glossary.md)
│          media/
└── internal/               # plans, audits, pilot reviews, evidence; prototypes/ stays where CI expects it
```

## 4. Workstreams

### 4.1 Vendoring contract (A4, G2)

| Input | Canonical in `sanduq-skills` | Vendored to | Transform |
| --- | --- | --- | --- |
| Illustrate | `skills/illustration-tools/skills/illustrate` | `extensions/illustrate/skill/` | inject `metadata.internal: true` |
| User Manual (5 skills + scripts, assets, requirements, references) | `skills/dev-tools/skills/user-manual*` | `extensions/user-manual/skills/` and `scripts/` | Extension adapter (paths, command integration) as a **`package.py` transform**, never a hand edit; inject `internal` |
| Delegate Task | `skills/agent-tools/skills/delegate-task` | Workflow archive `assets/delegate-task` | none; version recorded in `extensions/workflow/dependencies.json` |

- **Order:** port the extension's newer User Manual code (themes, cross-audience link guard, asset privacy)
  into the portable copy **before** the split. After the port, the portable copy is canonical. The
  extension's own `scripts/` stop being a fourth copy.
- **Digests:** `vendor.lock.json` records each tag and a digest of the **post-transform** tree, excluding
  `node_modules`, `__pycache__` and `*.pyc`. CI fails on any hand edit.
- **Versions:** the bundle version in `sanduq-skills` is Illustrate's version authority. The extension
  version line stays independent and records the vendored skill version.

### 4.2 CI and build migration (runs before anything moves)

`extensions/scripts/package.py` (the delegate-task path), `ci.yml` (Illustrate suite, `docs/examples/booking-manual`,
`prototypes/sanduq-delivery`, the JSON `find` over `skills plugins`, and the install.sh and `*.ps1` lint steps),
`check_docs.py` and `test_check_docs.py` (guide list), `.gitattributes` (`skills/illustration-tools` rules), and
marketplace validation (replace the `./`-only check with `claude plugin validate .`).

### 4.3 Marketplace and old install paths (R1, R2)

**Recommended (R1, needs your confirmation).** Keep one marketplace named `sanduq` at `samykabu/sanduq`.
Each entry becomes:

```json
{ "source": "git-subdir", "url": "https://github.com/samykabu/sanduq-skills.git",
  "path": "skills/illustration-tools", "ref": "illustration-tools-v3.3.0", "sha": "<40-char sha>" }
```

Entries carry no `version` field; `plugin.json` is the source of truth. The skills release workflow opens
a PR against `samykabu/sanduq` that bumps `ref`/`sha`. The plugin version in `plugin.json` must also change,
or users receive nothing. Rollback means reverting that PR. *Why this deviates from your earlier answer:*
Claude Code has no deprecation state for a moved marketplace, only `renames` and `forceRemoveDeletedPlugins`,
which uninstall plugins on users' machines. A user can also register only one marketplace per name. Moving
the marketplace would break every existing `/plugin marketplace add samykabu/sanduq`.
*Alternative:* move it to `sanduq-skills` and announce a breaking change (users run `/plugin marketplace remove sanduq`
and then re-add it).

**Old `npx skills add samykabu/sanduq` (R2).** The documented command becomes `npx skills add samykabu/sanduq-skills`.

- `metadata.internal: true` is injected into **every** SKILL.md in the extensions repo: vendored copies,
  the six internal skills, and test fixtures. With it, `--list` and default discovery from the old repo
  show nothing.
- **Functional rule (adopted from the round-3 dissent):** CI tries a *named* install
  (`--skill <name>`) for every skill in the old repo.
  - A skill whose vendored bytes are unmodified apart from the flag (Illustrate, Delegate Task) must pass
    a functional smoke test after a named install.
  - Extension-adapted entrypoints (User Manual) are stored under a non-`SKILL.md` filename and restored
    by `package.py`, so a named install of them is impossible rather than broken.
- CI records the observed explicit-name behavior as a test expectation.

### 4.4 Track S: Scope moves from Archify to Illustrate (separate spec and release)

This track is a product change, not documentation. It gets its own Spec Kit feature and its own release:

1. Inventory every active Archify reference with a search; do not assume a fixed count. Known sites:
   `clarification.py` (inline image contract), `scope.py`, `accept_plan.py`, `commands/plan.md`,
   `references/archify-plan.md`, both Scope SKILL.md files, the Workflow README, and PR `pr-image-embedding.md`.
2. **First decision: image hosting** for GitHub clarification comments. Private-repo raw URLs fail
   (`docs/workflow-compatibility.md`); reuse the PR extension's embedding approach.
3. Redesign `accept_plan` around Illustrate's dependency-graph type with browser and visual checks.
   Preserve coverage, reachability, freshness hashes, pending markers, failed-render recovery and receipt semantics.
4. Migrate existing pending Archify plans. Historical records keep their original evidence.
5. New tests, replacing the Archify-specific validators. Add a `requires` entry for Illustrate, a
   `pending-releases.json` entry, a Scope minor bump, a Workflow dependency pin bump and a Workflow release,
   and a consumer upgrade note.

The documentation plan documents Scope only after Track S ships.

### 4.5 Content

**Product catalog (A1, A2, G9).** One table per README: product, purpose, lifecycle phase, standalone,
requires, hosts, license. Columns are *standalone* (works without Workflow), *requires* (hard dependencies),
*installed* and *enabled* (installing ≠ selecting a process); each is defined in the glossary. Host
cells stay "unverified" until Phase 4.

**Lifecycle (B1, B3).** `check_docs.py` is extended (no new generator) to emit two views:
- **Manifest defaults**, from `extension.yml` hooks.
- **Managed Workflow**, derived from `presets/workflow`, `workflow.py` stage selection and `reconcile.py`
  hook suppression.

Prose explains how init changes optionality (Project and Assure). CI fails on drift.

**Scenarios (B2).** Four levels: skills only; Spec Kit plus one extension; an à-la-carte set; managed
Workflow. Each page covers goal, prerequisites, install, first prompt (per-host `<details>` blocks),
what you will see (recording), next step, and who enforces dependencies (G10).

**Install by host (C1, C2, D3, G3).**

| Host | Skills | Extensions | Verify in Phase 4 |
| --- | --- | --- | --- |
| Codex | `npx skills add samykabu/sanduq-skills --skill <n> -a codex` | `specify init --integration codex` | — |
| Claude Code | `/plugin marketplace add …` or `npx skills … -a claude-code` | `--integration claude` | plugin upgrade across split |
| Claude Desktop | marketplace install **and** zip upload (both tested) | not supported | each script: Illustrate HTML, SVG, PNG export; User Manual build; Delegate Task |

Also: an install block for all 8 extensions in dependency order, three set recipes (QA, docs, managed),
and the docs-pack preview prerequisites (encrypted preview for public repositories, access expectations).

**Prerequisites (C3, C4, G4).** One page with tool, needed by, tested version, and install command per OS.
It covers Spec Kit (`uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`),
Python, Node (including Illustrate's hand-drawn generator), git, `gh` plus scopes, Playwright and Chromium,
MkDocs Material and the named PDF libraries, SuperSpec (`WangX0111/superspec`), the Superpowers Bridge
(`lihan3238/speckit-superpowers-bridge`) and Superpowers (`obra/superpowers`). Recipes pin versions instead
of installing floating versions. Each package's Spec Kit minimum is listed as information, not as a defect.

**Install scripts (G5).** Retire `install.sh` and `install.ps1`. The Spec Kit catalog is the supported path,
and the scripts only copy files. Update the Project README's fallback section and remove the CI lint steps.

**Reference.** `reference/commands.md` is the single authoritative command reference (42 commands), and
`check_docs.py` coverage is retargeted to it. Packaged READMEs keep essential setup and recovery steps and
link to the version-matched reference. Package READMEs are corrected against their manifests (G1).

**Licenses (F1, G9).** `reference/licenses.md` gives a per-package table. Both READMEs get a "Can I use this?"
box. Every `plugin.json` gets a `license` field. `THIRD_PARTY_NOTICES` is split: the Lavery and icon notices
move with Illustrate; the extensions repo adds the Illustrate MIT notice and keeps the Scope and Memory notices.
Notices ship **inside** each bundle, skill and archive.

**Moved paths (G6, G7).** Forwarding stubs stay at old doc paths for one release cycle. Troubleshooting,
upgrades and changelogs get a page each. The root changelog is split: plugin history moves to `sanduq-skills`.

### 4.6 Language (D1, D2, D5)

- **Style guide** (one page): second person, one idea per sentence, define each term on first use and link
  it to the glossary. Limits go in a "Limits" box. Packaged READMEs use absolute links for destinations
  outside the package.
- **Glossary**: about 20 terms.
- **Enforcement**: `check_docs.py` automates a banned-term list. First-use glossary links are checked in
  editorial review and automated only if misses recur. No Vale.
- **Workflow README**: split into a guide of about 200 lines and a reference. This ships as a Workflow release.
- Agent-facing files (`SKILL.md`, `commands/`) are out of scope.

### 4.7 Motion: rich, staged (E1, E2)

| Wave | When | Output |
| --- | --- | --- |
| A | Now, parallel to text | Hand-edit one existing `docs/diagrams/*.svg` with a CSS/SMIL reveal gated by `prefers-reduced-motion: no-preference`, and verify it on github.com. **That asset becomes the product map.** Start terminal and session recordings with one shared recording setup (about 4 GIFs, reused across pages). |
| B | After Phase 1 | Illustrate **animated-SVG export flag** (SVG-scoped `<style>`, no `@import`, no script) as a separately tested Illustrate release. Then the lifecycle overlay and per-product animations (8 extensions + 3 skills). |
| C | After the Phase 5 text has shipped once | One narrated overview video (HyperFrames, captions, poster). The other two videos (à-la-carte, managed Workflow) follow. |

Rules:
- Motion never blocks a text release.
- Acceptance: the asset animates on github.com web, and mobile shows the complete static frame.
- Editable sources sit beside each export. Size budgets: 300 KB or less per animated SVG, 2 MB or less per GIF.
- Videos go in release assets or `user-attachments`. No media in plugin directories and no LFS, because
  LFS files arrive as pointer files when plugins are cloned.

## 5. Phases

Work happens on a docs branch with a `docs-baseline` tag. There is no freeze on `main`, because release
automation commits catalog updates there.

| Phase | Work | Closes | Done when (measurable) |
| --- | --- | --- | --- |
| **1. Reconcile and migrate build** | User Manual port (4.1); CI and build migration (4.2); create `sanduq-skills` at a tag; per-bundle release workflow; vendoring and `vendor.lock.json`; marketplace switch (R1); `internal` injection and named-install tests (R2); notices and licenses split | A4, F2, G2, G8, G9 | Scripted test on a machine with the pre-split marketplace: `claude plugin marketplace update sanduq` then `claude plugin update <bundle>@sanduq` installs a skill whose digest matches the tag. `npx skills add <repo> --list` gives the expected output for both repos. Named old-path installs behave per R2. CI is green in both repos. |
| **2. Restructure** | Move records and evidence to `internal/`; new docs trees; forwarding stubs; fix stale versions and authorship | A3, A5, G6, G7 | No user page links to `internal/`; link check passes |
| **3. Core content** | Catalog, lifecycle views, scenarios, prerequisites, per-extension pages, single command reference, Workflow guide and reference split, G1 README fixes, install-script retirement | A1, A2, B1–B3, C2–C4, D5, G1, G3–G5, G10 | `check_docs.py` reports 42 of 42 commands and 7 of 7 skills, both lifecycle views without drift, and no banned terms |
| **4. Hosts** | Clean-machine runs for Codex, Claude Code and Claude Desktop (both Desktop install paths); consumer-state upgrade tests with project edits and active Workflow state | C1, C5, D3 | Every matrix cell is Verified, Partial (with reason) or Unsupported, with version, OS and evidence |
| **5. Language** | Style guide, glossary, rewrite of READMEs and guides | D1, D2 | Banned-term check passes; editorial checklist signed |
| **6. Release docs wave** | Package README changes batched into one `pending-releases.json` set; patch releases; catalog promotion | — | Released archives contain the updated READMEs |
| **7. Motion** | Waves B and C (wave A runs from Phase 1 onward) | E1, E2 | Section 4.7 acceptance |
| **8. Cold-read test** | 3 first-time testers × 3 tasks on prepared, authenticated environments: install a skill on a chosen host; choose and install extensions for scenario 3; take scenario 4 to a `doctor` pass. Extensions are tested on Codex or Claude Code. | — | Each task is done unaided in 15 minutes or less; findings are logged and fixed |

**Track S** (section 4.4) runs in parallel with its own spec. Its documentation lands in a later docs patch.

## 6. Risks

| Risk | Mitigation |
| --- | --- |
| Existing plugin users break | R1 keeps the marketplace registration; Phase 1 runs the scripted upgrade test |
| Old `npx skills` path installs a broken skill | R2: adapted entrypoints can't be installed; named installs of the others are smoke-tested |
| Vendored code drifts | Post-transform digest in `vendor.lock.json`; CI fails on mismatch |
| Pin bumps forgotten | The skills release workflow opens the pin PR automatically |
| Doc edits ship without a release | Phase 6 batches them into one release set |
| Motion cost overruns | Staged waves; text never waits on motion |
| Claude Desktop limits misreported | Phase 4 tests each script on a real install |

## 7. Open items for the owner

1. **Confirm R1**: keep the marketplace at `samykabu/sanduq` (recommended), or move it to `sanduq-skills`
   as a breaking change.
2. Approve **Track S** as a separate feature.

## 8. Out of scope

Arabic translation, opencode and Copilot host support, a docs website, and relicensing extensions other
than those already MIT.

## 9. Review record

| Round | Claude Fable 5.1 | Codex GPT-6 Astra | Outcome |
| --- | --- | --- | --- |
| 1 | Corrected 41→42 commands, the Scope MIT license, hook optionality and stale READMEs. Found the delegate-task build input, the marketplace name collision, the broken `bundles/` layout and the scope of the Archify change. | Re-graded overstated findings. Found the User Manual divergence, the release and CI sequencing gaps, the motion export limit and the README-only redirect flaw. | 17 positions synthesized |
| 2 | Agreed to 11 and amended 6. Verified `git-subdir` and `metadata.internal`; flagged notices, LFS and Claude Desktop marketplace support. | Agreed to 6 and amended 11. Flagged that R1 deviates from the owner's answer and that named installs bypass the flag. | Disputes narrowed to R1–R4 |
| 3 | Agreed to all; consensus | Agreed to R1, R3, R4 and R5; disagreed with R2 (named install of an adapted skill could be broken) | R2 amended with the dissent's fix: functional test, adapted entrypoints can't be installed. **Consensus reached.** |
