# Reviewing the result

The delegate did the typing; you own the judgment. This is where delegation earns its keep or
quietly ships a mistake.

**Read the measurements before the prose.** The summary is the delegate's account of itself. The
git fields are what actually happened.

## Read these first, in this order

| Field | What it tells you |
|---|---|
| `status_provenance.primary` | *Which rule* produced the status. `self_report` means the delegate's own word decided it — treat accordingly. |
| `status_provenance.evidence` | Everything else that was true. A timeout after success telemetry keeps both facts. |
| `dirty_paths_changed` | What git measured changing during the run window. |
| `files_claimed` | What the delegate said it changed — a claim, not evidence. |
| `files_mismatch` | `true` = they disagree. **`null` = it could not be checked.** |
| `head_changed` / `index_changed` | Something committed or staged. Go look. |
| `read_only_violation` | `true` / `false` / **`null`**. `false` ≠ "no writes occurred". |
| `records_dropped` | Non-zero means evidence is missing — the status is sound, the summary may not be. |
| `tokens.fidelity` | `unavailable` means the zeroes are *unknown*, not *free*. |

A `null` anywhere means **unknown**. It is never a quiet "fine".

## Check the tests before you trust the gates

If the change touches existing tests, review those edits **first**. A weakened assertion, an added
skip or a deleted test makes the gate measure less than it did before — green is only meaningful
if the yardstick was not shortened.

- **Unbriefed edits to existing tests are a contract change**, not part of the fix. Flag them.
- **Skipped or commented-out tests added in this diff** — treat the underlying test as failing
  until proven otherwise, whatever the annotation claims.
- **Loosened assertions** — exact match relaxed to "contains", error types broadened, tolerances
  widened — same treatment.

## Re-run the gates yourself

The summary carries the delegate's claim that the gates passed. That is a claim. Re-run the real
commands and read the output. And keep it in proportion: **passing is necessary, not sufficient.**
A delegate can *satisfy* a gate without doing the work.

Go further where the change has its own shape:

- **Migrations / schema** — round-trip them: apply, reverse, re-apply on a scratch target.
- **Removals / renames** — grep the tree for dangling references.
- **Anything stateful** — exercise the behaviour; compiling is not evidence.

## Read the diff against the brief

- **Scope creep** — did it touch what the brief said to leave alone?
- **Scope shortfall** — did it finish, including edge cases, or stop at the first plausible version?
- **Quiet decisions** — a defensible call the brief did not anticipate. Understand it and decide;
  do not accept it because it looks reasonable.

## The generated-code sweep

These fail in ways a green gate is structurally blind to. Each can sit in a diff whose tests pass:

- **Hardcoded success or fixture data** on a path meant to do real work. A canned `{status:"ok"}`
  passes tests *by design*. Work that could not be done should fail loudly, not pretend.
- **Catch-all error handling returning a default** — the suppressed failure is exactly what the
  gate would have caught.
- **Unverified imports and API calls** — confirm every new dependency, method and signature exists
  in the *installed* version. Read the lockfile; plausibility is not evidence.
- **Dead weight** — unused imports, helpers nothing calls, unreachable branches, "Step 1 / Step 2"
  comment scaffolding, comments restating the line below.
- **A second way to do what the file already does** — a new HTTP client, error idiom or logging
  style beside the existing one.
- **Tests that assert internals** — asserting a private helper was called, or mocking the project's
  own functions. Green, brittle, worthless as regression cover.
- **Near-duplicate test bodies** differing by one value. Bloat reads as coverage.
- **Speculative surface** — optional parameters, flags or abstractions with no caller.
- **Guards for impossible cases** — null checks for values the contract already excludes, which
  bury the validation that matters at real boundaries.

## The working tree is evidence

From dispatch until you decide, the uncommitted tree is the authoritative copy of the delegate's
work — often the only copy.

🚨 **Never run `git checkout`, `reset`, `clean` or a branch switch before inspecting it.** However
messy an interrupted run looks:

- `git status`, `git diff`, and `git diff --cached` for anything staged — plain `git diff` is blind
  to the index
- open untracked files (`??`) directly; no diff shows their contents

After inspection the verdict may legitimately be to discard, and then `checkout`/`clean` is the
right tool. The ban is on reflexive cleanup before anyone has looked.

If `head_changed` is `true`, something committed inside the run window. The driver deliberately
does not undo it — the commit may have been yours. Read `git log` before deciding.

## Reworking: send the delta

```bash
node "$DELEGATE" start --harness codex --cwd <same dir> --resume <run_id> \
  --task "The fix is right, but the test mocks the DB session — use the real migrated fixture, and drop the now-unused import."
```

`--resume` keeps the delegate's context, so a short delta is enough, and it restates the policy
rules rather than assuming the old session still honours them. Then review again — rework gets the
same gate re-run, test check, diff read and sweep.

## Surface, don't absorb

Delegation was opted into, so acting on verified, gate-passing work is the agreed contract. Keep
the human in the loop on anything that changes the shape of the work:

- **Report the decisions** the delegate made, and defensible-but-unrequested turns.
- **Note nitpicks you chose not to block on**, so they can be overruled.
- **Stop and ask** if correct completion needs going beyond the brief. A scope change is the
  human's call.
