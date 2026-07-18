---
name: api-docs
description: Generate, filter, validate, and integrate audience-safe API documentation for REST/OpenAPI, AsyncAPI, GraphQL, RPC, webhooks, and code APIs. Use when a User Manual feature adds or changes endpoints, messages, schemas, authentication, examples, integrations, or API migration behavior.
---

# API documentation

1. Inventory the real external, administrative, and internal API surfaces. Never infer that an
   endpoint is public from its route alone.
2. Prefer checked-in contracts. For OpenAPI/AsyncAPI, lint and bundle before rendering. Read
   [openapi.md](references/openapi.md).
3. Produce separate audience bundles so internal/admin operations cannot leak into public output.
4. Document purpose, caller, authentication concept, permissions, method/path or channel, parameters,
   request/response schemas, statuses/errors, rate limits when evidenced, versioning, and redacted
   examples.
5. Explain APIs in plain language before presenting technical reference. Keep exact identifiers in
   code formatting.
6. If no reliable contract exists, generate a clearly marked draft from implementation/tests and add
   a task to establish or correct the contract.
