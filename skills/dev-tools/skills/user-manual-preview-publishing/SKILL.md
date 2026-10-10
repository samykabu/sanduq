---
name: user-manual-preview-publishing
description: Configure private CI preview artifacts, approved ephemeral documentation hosting, and versioned standalone User Manual releases with separate End User, Administrator, and Technical access controls. Use when establishing or troubleshooting preview and release publishing.
---

# User Manual Preview Publishing

Read [provider-contract.md](references/provider-contract.md). Inspect a target provider's current
official documentation before creating or changing an adapter.

1. Always produce and link a private CI artifact first; hosted preview success cannot replace it.
2. Deploy an ephemeral hosted preview only when `User-Manual/manual.yml` names an approved provider
   id and a matching provider descriptor is checked in.
3. Public hosting may contain only approved End User content. Administrator and Technical editions
   require provider-enforced authentication and must never rely on an unlisted URL alone.
4. Pin third-party actions and dependencies according to the project's supply-chain policy.
5. Do not expose tokens in commands, logs, generated configuration, preview URLs, or documentation.
6. Skip hosted deployment for untrusted fork PRs when provider credentials are unavailable; keep the
   private or encrypted CI artifact and report the reason.
7. Capture the provider URL and update one marker-delimited PR comment instead of creating
   duplicate comments.

On a feature PR, upload all editions as a repository-reader-only artifact. If a provider is
approved, deploy only the allowed edition and protect internal content with an identity policy.
