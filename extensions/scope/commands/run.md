---
description: "Scopes a GitHub issue as a senior solution analyst: checks prerequisites, sizes effort, asks for the preferred number of sub-issues and publishes only an approved decomposition. Use when asked to scope, size, estimate or split an issue by number or exact title."
---

# Speckit Scope

Input: $ARGUMENTS

Read and execute `.specify/extensions/scope/skills/scope-analyst/SKILL.md`.
Pass the user's issue number or exact title. Missing input is an error, never an
invitation to choose an issue from the active editor, branch, or recent conversation.
In a managed project, return the completed scope evidence to the workflow dispatcher,
which automatically invokes Specify when no unresolved decision remains. Existing
keep-together policy settles decomposition inside its configured effort band.
In an unmanaged project, use the analyst skill as the authority and leave the
enriched Specify prompt ready for the next step.
