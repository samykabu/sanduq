# OpenAPI workflow

Use Redocly CLI when available: lint the source, bundle all references, then build static reference
HTML. Pin the CLI version in the consuming project rather than invoking an unbounded `latest` in CI.

Create distinct bundles for external, administrator, and internal audiences based on explicit
contract metadata or approved path/tag rules. Fail closed when classification is ambiguous. Keep the
bundled contract as an artifact and link it from the corresponding manual reference page.

Check operation summaries, descriptions, IDs, security schemes, parameters, request bodies,
responses, schemas, examples, deprecations, and version/migration notes. Redact bearer tokens,
cookies, secrets, real identifiers, and production hosts.
