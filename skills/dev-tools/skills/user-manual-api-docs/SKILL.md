---
name: user-manual-api-docs
description: Generate, filter, validate, and integrate audience-safe standalone API documentation for REST/OpenAPI, AsyncAPI, GraphQL, RPC, webhooks, and code APIs. Use when a manual must document endpoints, messages, schemas, authentication concepts, examples, integrations, or API migration behavior.
---

# User Manual API Docs

1. Inventory the real external, administrative, and internal API surfaces. Never infer that an
   endpoint is public from its route alone.
2. Prefer checked-in contracts. For OpenAPI or AsyncAPI, lint and bundle before rendering. Read
   [openapi.md](references/openapi.md).
3. Produce separate audience bundles so internal or administrator operations cannot leak into
   public output.
4. Document purpose, caller, authentication concept, permissions, method/path or channel,
   parameters, request/response schemas, statuses/errors, evidenced limits, versioning, and safe
   synthetic examples.
5. Explain each operation in plain language before presenting technical reference.
6. If no reliable contract exists, mark the generated reference as a draft and record the missing
   contract as documentation debt.

For a retailer integration API, publish order-submission examples to technical partners, keep
refund administration endpoints in the authenticated edition, and exclude internal health or debug
routes entirely.
