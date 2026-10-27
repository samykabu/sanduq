# Local transport

Applies when the active claim says `clarification_transport: local` (the feature's checkpoint froze
`clarification.transport: local` at Scope start). Nothing about the clarifications is posted to or
synced with GitHub; `clarification.py inspect` and `publish` refuse with
`CLARIFICATION_TRANSPORT_LOCAL`. Skip the GitHub steps of this skill and do this instead.

## Ask in the conversation

1. Read `specs/<feature>/spec.md` and `specs/<feature>/clarifications.md` when it exists.
   Questions keep the GitHub ids: round `<r>`, question `<n>` is `C<r>Q<n>`; `C1Q1` is the first.
   Decision questions raised with `decisions.py ask` live in the same file as `SD<n>`.
2. Ask every material question in this conversation, each with its options and a justified
   recommendation, and wait for the user's answer. Never answer for the user.
3. Record each question and the user's own reply in `specs/<feature>/clarifications.md`:

   ```markdown
   ## C1Q1: What should happen if the request fails?

   - [ ] **A.** Retry **(Recommended)**
   - [ ] **B.** Start again

   C1Q1: B - keep what was typed
   ```

   The answer line is `<ID>: <letter>` (`<ID>: A, C` for several; `<ID>: <text>` when the
   question has no options), followed by the user's wording after ` - ` when they gave any.
   The runtime reads the file with the same tolerant grammar as GitHub replies (`C1Q1: B.`,
   `C1Q1 - B`, `C1Q1 = B`) and reports every line that names an id but is not an answer. Never
   tick a box or write an answer line the user did not give; a reply recorded here is
   self-attested (no GitHub record vouches for it) and is labelled so in the receipt and the gate.
4. Apply the answers to the spec as [analysis-json.md](analysis-json.md) says for `spec_edits`,
   and re-evaluate the spec quality checklist.
5. Create the file even when no question was needed (the header and a line saying so): the
   Clarify receipt must list `specs/<feature>/clarifications.md` under `inputs`, with
   `unresolved: 0` and `answers_applied: true`. `complete` refuses a receipt that omits the file
   (`CLARIFICATION_FILE_INPUT_REQUIRED`) or leaves a `C<r>Q<n>` without a reply
   (`CLARIFICATION_UNRESOLVED`).
6. Do not move the board; Plan's gate (`clarification.py plan-gate`) passes on the passed Clarify
   receipt, and Project Sync moves the issue at its usual points. `workflow.py status` shows
   `questions.answered_in` and the ids still waiting.
