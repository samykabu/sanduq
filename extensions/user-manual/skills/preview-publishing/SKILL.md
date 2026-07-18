---
name: preview-publishing
description: Configure and publish ephemeral User Manual previews through a project-approved hosting provider while preserving End User, Administrator, and Technical audience access controls. Use only when User-Manual/manual.yml names an ephemeral provider or when the user is approving, changing, or troubleshooting preview hosting.
---

# Preview publishing

Read [provider-contract.md](references/provider-contract.md), then inspect the target provider's
current official documentation before creating or changing its adapter.

1. Always produce and link the private CI artifact first; hosted preview success cannot replace it.
2. Require an approved provider id in `User-Manual/manual.yml` and a checked-in matching descriptor.
3. Publish only approved End User content without authentication. Administrator and Technical
   editions require provider-enforced authentication and must never rely on an unlisted URL alone.
4. Pin third-party actions and dependencies according to the target project's supply-chain policy.
5. Do not expose tokens in commands, logs, generated configuration, preview URLs, or documentation.
6. Skip hosted deployment for untrusted fork PRs when provider credentials are unavailable; keep the
   private/encrypted CI artifact and report the reason.
7. Capture the provider URL and update the existing marker-delimited PR comment without duplicating
   comments.
