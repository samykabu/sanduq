# Issue625 retrospective tooling implementation plan

Owner approved implementation of all three remaining tooling fixes. Work is isolated in `sanduq--retro625` and `sanduq-skills--retro625`; existing checkouts and Bunyan#17 are preserved. One independent review follows completion of all implementation, testing and package integration.

1. **Freeze the implementation boundary and shared contracts.**

   Sanduq was verified at `87bc437dc38071ffe7d50ce7f74a22048dcf5fc1`; sanduq-skills was verified at `260b7a5565c129617e6c12a1f6f06087af6e2f18`. The portable checkout already contains an untracked `skills/agent-tools/skills/delegate-task/bounded.mjs`; preserve it as concurrent implementation work.

   Existing behavior to retain:

   - Memory’s `Archive.run_checks()` already executes argv arrays with `shell=False`.
   - Portable `delegate.mjs` already uses argv arrays, UTF-8 stream decoders, append-only journals, exclusive terminal-result claims, timeout handling, and requested-versus-observed model fields.
   - Workflow’s `verification_plan.py` already binds commands, source files, fixtures, executable identity and environment to passing receipts. Its current evidence path is overwritten on subsequent execution.
   - `execution_tools.py` already validates project-owned preflight manifests, including executable and argument requirements.
   - Memory already batches provenance existence checks through `Repository.exists_at()`, but `memory.inventory()` reads each blob separately.

   Preserve the merged #624 repairs. Treat #625’s completed archive and recorded verification override as historical evidence, with no acceptance reruns.

2. **Coding batch A: Memory preflight, freshness and Workflow evidence — Sanduq only.**

   **Owning files**

   - `extensions/memory/scripts/archive.py`
   - `extensions/memory/scripts/git_state.py`
   - `extensions/memory/scripts/memory.py`
   - `extensions/memory/scripts/memory_delta.py`
   - `extensions/memory/archive-policy.json`
   - `extensions/workflow/scripts/verification_plan.py`
   - `extensions/workflow/scripts/execution_tools.py`
   - `extensions/workflow/scripts/workflow.py`
   - `extensions/workflow/schemas/receipt-v1.schema.json`
   - New focused helpers under `extensions/scripts/shared/`, plus corresponding Memory and Workflow tests.

   **Early preflight**

   Add `archive.py preflight` for explicit spec/check selection and an optional prepared run. Invoke the same deterministic checks internally before `verify()` launches commands and before `prepare()` creates its checkpoint and synthesis inventory.

   Extract reusable checks from `require_checks()`, `references()`, `spec_files()`, `materialize()`, and `Repository.check_scope()`. Share the actual output-ignore check using `git check-ignore --no-index`; do not create a weaker parallel validator.

   Preflight must report:

   - Selected check/profile coverage and command validity.
   - Live imports or references into selected spec folders.
   - Executable/configuration references that assume the retiring feature branch.
   - Missing declared checker, configuration, fixture and reference inputs.
   - Ignored source artifacts, including tracked files matching ignore rules.
   - Predicted ignored outputs, unsafe paths and scope violations.

   Scope branch detection to executable/configuration contexts and explicit project checks. Historical prose mentioning a branch is not itself an archive blocker. Preserve immutable Git references, fixture migrations and valid repair declarations.

   Split deterministic candidate materialization from critique admission. Both formats must support repair simulation and output guards before critique; final validation must still require the existing exact-candidate critique. Before a candidate exists, report candidate-only checks as pending, not passed. Existing repairable references must remain usable inputs to synthesis rather than becoming unconditional preparation failures.

   **Per-check fingerprints and reuse**

   Extend the existing Workflow identity mechanism through a small shared Python helper, packaged into Memory and Workflow. Keep Memory usable without adding Node as a mandatory dependency.

   Introduce an explicitly versioned, complete check-input manifest. Bind each check to:

   - Its definition, argv, selected executable and resolved executable bytes.
   - Checker code, configuration, fixtures, relevant transitive sources and lockfiles.
   - Directory membership where discovery determines inputs, so added files invalidate correctly.
   - Working directory, platform/runtime identity and declared environment identity.
   - Receipt and retained output hashes.

   Project declarations own dependency completeness. Missing declarations, unresolved dynamic dependencies, unavailable environment identity or unsupported manifest versions make reuse unavailable. An empty dependency list must never establish independence.

   Preserve legacy global freshness when the complete manifest is absent. Keep archive transaction guards separate: per-check reuse must not authorize applying a stale candidate after source, policy, scope or registry changes. Recompute fingerprints before and after execution; input mutation prevents a passing reusable receipt.

   Store every execution in an immutable attempt directory. Existing evidence paths may remain compatibility pointers or projections, while snapshots bind the immutable attempt’s hash. Report `executed`, `reused`, `invalidated` and `unknown` separately. Preserve manual override reasons and distinguish skipped verification from passing checks.

   **Compact, recoverable evidence**

   Add bounded archive projections for status, checks, inventory and coverage, usable with format 1 and format 2. Return whole typed records, counts and continuation information within a byte budget. Never truncate serialized JSON mid-document.

   Add bounded blob batching beside `Repository.exists_at()` and use it in `memory.inventory()`. Validate response framing, object type and size; preserve full immutable commit validation and path safety.

   For new Workflow evidence, introduce an additive immutable-Git reference form containing repository identity, full commit, path, blob identity and content hash. Validate it during receipt admission and reading. Retain legacy file evidence.

   The bounded inspection did not locate a general Workflow function that copies whole-document “before” snapshots. Do not assume installer rollback snapshots are that producer. Provide a focused evidence-capture helper and wire the relevant stage instructions to it.

   Omit copied bytes only when the exact required bytes are recoverable from retained Git objects and the receipt proves that binding. Preserve dirty/untracked bytes and checkout bytes differing from Git because of CRLF or filters. Keep existing archive recovery payloads unless replacement recovery has explicit regression proof.

   **Batch completion:** both formats reject representative early blockers, legacy freshness remains unchanged, complete manifests safely select affected checks, and compact evidence passes byte-exact recovery tests.

3. **Coding batch B: portable executor and collection — sanduq-skills only.**

   **Owning files**

   Under `skills/agent-tools/skills/delegate-task/`:

   - `delegate.mjs`
   - The in-progress `bounded.mjs`
   - A focused native check-batch module, if separation keeps `delegate.mjs` manageable
   - `contracts/result-schema-v2.md`
   - `contracts/status-precedence.md`
   - A new check-batch/projection contract
   - `test/run.mjs` and synthetic fixtures

   Add native check-batch execution through an additive capability advertised by `delegate.mjs contract`. Keep existing start/collect behavior compatible. Do not rewrite harness spawning merely to introduce argv arrays it already uses.

   The batch manifest must declare repository/worktree identity, owner, check IDs, executable/argv, timeout and output limits. Validate the entire manifest before launching the first check. Reject an absent executable, malformed argv, and interpreter invocations missing their required script/module. Permit intentional empty arguments only where the contract explicitly allows them.

   Execute without shell interpolation, with explicit UTF-8 handling and process-tree cleanup. Preserve separate launcher failure, command failure, timeout, parse failure and incomplete-output outcomes.

   Persist append-only attempts, including failed launches. A retry gets a new attempt ID and a link to its predecessor; it never replaces prior artifacts. Associate a batch with one execution owner through collection. Concurrent execution of the same batch must be refused; collection must be idempotent. Recover ownership only with positive evidence that the previous owner and child are gone.

   Extend collection with a bounded multi-run/batch summary and transition notifications. Keep machine-readable summaries independent of raw prompts and logs. Parse structured command output only after successful completion, within explicit size limits and with schema/type validation.

   Preserve `status_provenance`, model-reporting distinctions, legacy normalization, secret redaction and existing terminal-result ownership. Environment identities must not expose secret values; unknown secret-dependent identity disables reuse.

   **Batch completion:** synthetic Node fixtures prove argument fidelity, immutable attempts, exclusive ownership, reliable cleanup, bounded valid projections and unchanged legacy result semantics.

4. **Coordinator integration, documentation and package work.**

   The two workers may implement independently after agreeing on attempt identifiers, fingerprint fields and bounded-result envelopes. The portable worker does not edit Sanduq; the Sanduq worker does not edit portable source or vendored assets.

   The coordinator owns:

   - Thin integration in `extensions/workflow/scripts/delegate_dispatch.py` where the new portable capability is consumed.
   - Shared-helper inclusion in `extensions/scripts/package.py`.
   - Version manifests, changelogs and `extensions/pending-releases.json`.
   - Portable plugin metadata and release pin coordination.
   - `extensions/scripts/vendor.py` synchronization, `vendor.lock.json`, and marketplace pins.
   - User-facing documentation and durable status.

   Vendor from canonical source using the existing vendor tool. Do not edit `extensions/workflow/assets/delegate-task` directly. Keep unpublished versions out of published catalogs and pending status at `implementation-in-progress` until validation is complete.

   Document these proposed interfaces with runnable fixtures:

   ```text
   python .specify/extensions/memory/scripts/archive.py preflight --spec specs/412-refund-approval --check docs
   python .specify/extensions/memory/scripts/archive.py inspect --run <run-id> --view checks --max-bytes 16384

   node <delegate-task>/delegate.mjs checks --manifest checks.json --owner retro625-collector
   node <delegate-task>/delegate.mjs collect-batch --batch <batch-id> --owner retro625-collector --max-bytes 16384
   ```

   Retain the existing `verification_plan.py run/select/snapshot` interface. Explain opt-in completeness, invalidation reasons, retry ownership, projection limits and old-receipt behavior in one authoritative contract each.

5. **Regression and disposable-consumer acceptance.**

   Extend `test_archive.py`, `test_archive_v2.py`, `test_verification_plan.py`, `test_execution_tools.py`, and the portable Node suite. Add focused fixtures for:

   - Spec imports, branch-dependent configuration, missing inputs, missing coverage and nested ignore exceptions, all detected before a sentinel expensive command executes.
   - Valid immutable references, fixture migrations and repair simulation in both formats.
   - Checker-only changes invalidating their check; shared transitive/config/environment changes invalidating all affected checks.
   - Unknown dependencies, missing evidence, tampered receipts, new discovered files and mid-run mutations refusing reuse.
   - Spaces, quotes, Unicode/Arabic, literal shell metacharacters, malformed JSON, empty output and oversized single-line JSON.
   - Duplicate launch/collection, failed-launch retry preservation, timeout descendants, live-owner refusal and dead-owner recovery.
   - Byte-exact Git recovery; retained dirty/untracked/CRLF inputs; missing-object refusal.

   Run the affected Python and Node suites, vendor validation, documentation checks and `git diff --check`. Build versioned Memory and Workflow packages, then install and upgrade them in a disposable consumer using the existing smoke tooling. Verify packaged helper inclusion, capability detection, rollback behavior and preservation of project-owned policy/CI. Keep automatic Memory and deployment disabled. Do not upgrade active Bunyan #17.

6. **Final completion boundary.**

   Record actual commands, outcomes, package hashes, attempt IDs, skipped checks and limitations in the durable plan/status artifact. Complete implementation, tests, evidence and package integration before **one independent completed-feature review**. Close its findings and run affected retests, then prepare final PRs for the two canonical repositories.

   The main risks are false dependency completeness, secret-bearing environment receipts, ownership races, archive repair false positives, and loss of byte-exact recovery. Each has an explicit conservative fallback above. No nightly jobs, deployment changes, Playwright plans, forced format migration or additional review gates are required.

## Execution record

- Planning complete from current source. Prior #624 repairs are already merged; no duplicate repair work.
- Portable execution batch started on Codex with requested `gpt-6.1-sol`. The two initial Claude invocations stalled before producing output or edits, were stopped, and remain recorded; usage is unavailable.
- Memory/Workflow batch is next. No implementation review has started.
- Actual package versions, checks and source commit pins are recorded after integration. No release or remote CI has been triggered.
