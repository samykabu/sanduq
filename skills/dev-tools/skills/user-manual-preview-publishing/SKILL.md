---
name: user-manual-preview-publishing
description: Configure private CI preview artifacts, approved ephemeral documentation hosting, and versioned standalone User Manual releases with separate End User, Administrator, and Technical access controls. Use when establishing or troubleshooting preview and release publishing.
---

# User Manual Preview Publishing

Read [provider-contract.md](references/provider-contract.md). Inspect a target provider's current
official documentation before creating or changing an adapter.

1. Always produce and link a private CI artifact first.
2. Deploy an ephemeral hosted preview only when `User-Manual/manual.yml` names an approved provider.
3. Public hosting may contain only approved End User content. Administrator and Technical editions
   require provider-enforced authentication.
4. Pin third-party actions according to the project's supply-chain policy.
5. Do not expose tokens in commands, logs, configuration, preview URLs, or documentation.
6. Skip credentialed deployment for untrusted fork PRs and explain the private-artifact fallback.
7. Update one marker-delimited PR comment instead of creating duplicate comments.

On a feature PR, upload all editions as a repository-reader-only artifact. If a provider is
approved, deploy only the allowed edition and protect internal content with an identity policy.
