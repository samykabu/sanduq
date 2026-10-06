---
title: Review a refund
module: payments
audiences: [end-user, administrator, technical]
language: en
content_type: how-to
source_evidence: [README.md]
last_verified: 2026-10-06
status: example
---

# Review a refund

## Review the request

1. Open **Payments** and select the pending refund.
2. Compare its amount and reason with the booking.
3. Choose **Approve** or **Reject** and record your decision.

Expected result: a rejected request ends without settlement. An approved request is sent to the payment provider once using its existing idempotency key.

## Reconcile a failed settlement

Check the provider's actual result before attempting recovery. A failed response is not proof that money moved. Record the confirmed outcome in the refund history.
