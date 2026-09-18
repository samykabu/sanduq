Continue implementing the reusable Sanduq workflow plan in D:\Projects\Personal\sanduq,
branch feat/reusable-workflow. Read docs/workflow-implementation-progress.md and
workflow-extension-implementation-plan.md first. Preserve all existing changes,
including the PR inline-image contract and Archify diagram artifacts. The active
goal is implement the plan and remains unfinished. Do not mark it complete merely
because local unit tests or installation fixtures pass.

Completed verification: 98 Scope tests, 34 workflow/adapter/freshness tests; actual
Spec Kit public-CLI clean install, composition, four QA/manual choices and
same-version reinstall for Codex+SuperSpec and Claude+core. No live GitHub issues,
PR, release or Bunyan installation has been changed. Public catalogs retain old
published versions; extensions/pending-releases.json declares intended versions.

Next priorities are automated Init/dependency/preset installation with rollback,
version-upgrade and CI gate tests, runtime revalidation of existing features,
coordinated immutable releases before catalog publication, then live GitHub and
Bunyan/second-project pilots. The older release workflow is not yet safe for the
new coordinated release. Scope's community ID collides with an unrelated package;
use explicit Sanduq source URLs and validate provenance. See the progress file for
remaining correctness audits. User input for Bunyan's QA/manual selection was
requested asynchronously; use an answer if provided, otherwise preserve the
pending selection rather than assuming it. All reusable source stays in Sanduq.

Use labelled estimated context monitoring with small work batches because this
host has no reliable occupancy telemetry. Make another durable handoff before
running out of context. Never claim the 60% target is a measured hard guarantee.
