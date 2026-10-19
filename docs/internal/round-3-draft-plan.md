# Round 3: draft plan for joint review

Draft by the orchestrating session (Claude Opus 5.5), written to be challenged by an independent review
(Codex, gpt-6.1-sol) before the user sees it. Sources: `round-3-naming.md` and the six
`round-3-review-*.md` files in this folder; BEFORE numbers in `benchmarks/round-3-before-*`.

## 1. Naming (decision for the user)

Recommendation from the naming review, which I adopt as the default:

- Display names get one family prefix and stop misleading: "Sanduq Workflow", "Sanduq Issue Scope",
  "Sanduq Assure", "Sanduq User Manual", "Sanduq Pull Requests", "Sanduq GitHub Project Sync",
  "Sanduq Illustrate", "Sanduq Memory and Archive", "Sanduq Progress Report"; presets "Sanduq Scope
  Gate", "Sanduq Scope Brainstorm", "Sanduq Managed Workflow". Descriptions say what each is not
  (workflow is not `specify workflow`).
- One id rename: `scope` to `issue-scope` (collides with the community "Spec Scope"; only Workflow's
  installer installs it, so the installer can migrate it inside its existing rollback).
- Every other id stays. `workflow` and `memory` renames are L and risky with no Spec Kit support for id
  aliases; `pr`, `project`, `illustrate`, `assure`, `user-manual`, `progress` fit.
- Offer the user three presets: display names only; recommended (above); full rename (adds
  `project` to `project-sync`, `memory` to `spec-memory`, the `workflow` preset to `workflow-overlay`).

Migration for `scope` to `issue-scope` (and any id the user adds): Workflow's `upgrade.py`/`install.py`
detect the old registry entry, copy state (`.specify/extensions/scope/` files that are not package
content, scope cache), run `specify extension remove scope` then `add issue-scope` from the release URL,
remove old host skills on every installed host, keep old command names as Spec Kit command aliases for
one minor release, record `renamed_from` in `install-lock.json`, keep policy keys and state paths that
consumers own unchanged, and freeze the old catalog entry with a `replaced_by` field. Tests: a fixture
project at the old version upgrades to the new one on both hosts, and a re-run is idempotent.

## 2. Fix first (correctness defects found in round-2 work)

| Id | Defect | Source |
| --- | --- | --- |
| AU5 | Assure gate fallback turns the gate on for `false  # set to true` (my round-2 fix) | R3 |
| AU2 | `audit_qa.py` flags redacted placeholders and valid links; the command says fix every finding | R3 |
| AU1 | Diagram stages skip Illustrate's theme and check steps after the type-index wording | R3 |
| IP5 | The opt-in Illustrate hook is always registered (223 ms per Write/Edit; never fires on Codex) | R5 |
| PM1 | `pr_publish.py` copies relative image paths into the PR body; fixing after publish breaks lint | R4 |
| PM4 | `project_sync.py` reintroduces the remote-parsing bug Workflow fixed (dots, ports, case) | R4 |
| SC7 | Error messages point at `/speckit-scope`, which exists only with aliases on | R2 |
| X2 | Stale facts: "8 extensions", root CHANGELOG headings still "(pending release)" | R6 |
| W8 | Review identifiers still in four execution headings; receipt rules ask for inputs the runtime adds | R1 |
| PM6 | Memory hooks may double-run with Workflow's memory handoff in managed projects (confirm first) | R4 |

## 3. Optimizations (proposed set)

Highest value first; ranges are the reviews' own (fractions of that extension's cost).

- **CI wall time:** X4 split the Windows workflow suite four ways (PR wall time 0.55 to 0.65), X3 path
  filter for release metadata and docs, X5 caches, X6 vendored verifiers only on vendor bumps, IP7 stop
  duplicating the upstream Illustrate tests (210 s to under 10 s), IP10 browser tests out of the default
  Progress run, PM9 memory suite speed and a project suite.
- **Runtime:** W1 one git and fingerprint pass per command (dispatcher runtime 0.30 to 0.45, slowest test
  modules 0.25 to 0.50), W6 cache the delegation probe, SC3 fewer GitHub calls in publish/bind/clarify
  (63 to 263 calls per publish today), SC4 lighter gate with snapshot reuse, PM4's gh call cut.
- **Instruction load:** W2/W3 Execute carries only the protocol that applies (Execute is 20% of the front
  half), SC1 trim scope's path, IP1 icon lookup script instead of an 82 KB catalog read, IP4 export reads
  its reference only on failure, AU3 skip unchanged reruns, AU7 host-neutral names and lighter init, PM8
  memory descriptions, SC7 hook-only descriptions; plus the catalog: the 47 host-visible descriptions
  total 8,604 characters (over Codex's 8,000 fallback), and workflow 5/13 and scope 6/7 still fail.
- **Model work to scripts:** PM2 `pr_feedback.py`, PM5 `project_init.py` (non-interactive), SC5 plan
  waves and mapping, SC6 checkbox answers and the Q/A log, SC9 analysis skeleton, W4 receipt skeleton.
- **Packaging and install:** X7 bounded backups and presets re-added only when changed, X8 and IP6/IP8
  smaller archives, W7 runtime-only delegate-task install, IP9 installer hint for native Progress wiring.
- **Release tooling:** X1 `release.py bump` writes every version copy; X2 new `check_docs` rules.
- **Refactoring:** AU4 one freshness CLI, AU5 one exclude list, AU6 vendored test, SC8 scope transport
  module, SC2 fold scope-brainstorm into scope-gate, W9 split `workflow.py` (L; after W1), X9 deferred
  except a one-line temp-name fix.
- **Upstream (sanduq-skills):** IP1, IP2 (examples pass `--strict` plus a baseline test), IP3, IP4 part,
  IP7 part, IP10.

Not proposed: renaming workflow or memory ids, splitting `archive.py`, merging memory commands, a
shared git helper module.

## 4. Streams (after the user's naming choice)

Disjoint file ownership, Opus 5.5 high agents, one notes file; the orchestrator reviews and commits.
U-A illustration-tools (IP1, IP2, IP3, IP4 upstream part), U-B agent-tools and dev-tools (IP10, AU6
upstream test, IP8 docs), S-WF workflow runtime and references (W1-W8, PM6, IP5 installer part, IP9,
W7, X7), S-SC scope and presets plus the rename (SC1-SC9, naming), S-AU assure and user-manual
(AU1-AU7), S-PM pr, project and memory (PM1-PM5, PM7, PM8), S-IL illustrate and progress sanduq side
(IP4 command, IP5 hook registration, IP6, IP7 sanduq part, IP8), S-X CI, release and docs (X1-X6, X8,
PM9 CI part, display names and descriptions across all manifests, check_docs rules). W9 runs last,
alone, after W1 lands.

## 5. Questions for the reviewer

1. Are any of the "fix first" items wrong, overstated, or missing a regression we introduced?
2. Is `scope` to `issue-scope` the right single rename, or should the user be steered differently?
3. Is the migration design sound given Spec Kit has no id alias? What breaks for an installed consumer?
4. Which optimizations are not worth their risk, and what high-value item is missing?
5. Is the stream split safe (shared files, ordering), and is W9 worth doing at all?
