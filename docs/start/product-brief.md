# Product brief

This page says who Sanduq is for, what it does for them, and how we know it works. Use it to decide
what to build, fix or cut next.

## Who it is for

| User | Status |
| --- | --- |
| The maintainer, working alone with Codex and Claude Code on Windows, macOS and Linux | Primary user |
| Private consumer projects: a product repository run through the managed Workflow | Primary user; one consumer today, on Windows |
| Small teams adopting single extensions, and open-source users of the portable skills | Goal: public adoption. No evidenced users yet |

The primary users come first when a choice has to be made. Public adoption is a goal, so the
documentation stays usable by someone who has never met the maintainer.

## The three jobs

| Job | What the user gets | Products |
| --- | --- | --- |
| 1. Take one GitHub issue to a verified pull request | One command runs scope, specification, planning, implementation, checks and documentation, and resumes after an interruption | Workflow, Scope, Project, PR, Memory, Progress |
| 2. Add one delivery process to a Spec Kit project | QA analysis, a manual, a PR description, board sync, diagrams, project memory or a progress report, each installed on its own | Assure, User Manual, PR, Project, Illustrate, Memory, Progress |
| 3. Do one task in an agent without Spec Kit | A diagram, a manual, a progress report or a delegated task | Portable skills in [sanduq-skills](https://github.com/samykabu/sanduq-skills) |

Every extension serves at least one job. Some Workflow capabilities are in use by the maintainer but
have no live-run record yet: the host switch, CI waivers, the Superpowers Bridge route and SuperSpec.
[Compatibility](../reference/compatibility.md) lists them.

## How we measure it

| Outcome | Measure | Target |
| --- | --- | --- |
| An issue reaches a pull request without manual state repair | Share of managed issues that reach an open pull request with no hand edit of a checkpoint or receipt | Every issue |
| Accepted work is not thrown away | Accepted receipts lost after an administrative or storage-only change (a board status, line endings, an unused claim) | Zero |
| The consumer runs a current release | Release trains between the consumer's installed version and the latest | One at most |
| Support claims match evidence | "Tested" cells in [compatibility](../reference/compatibility.md) without a retained evidence record | Zero |
| The cost of a managed issue is known | Agent cost in USD and wall time per managed issue, by effort tier, recorded per release train | Recorded every train |

The last recorded lite-tier run cost USD 4.68 over about 20 minutes on Claude Code (round 5,
2026-10-21). Use it as the baseline until a later run replaces it.

## What this means for priorities

Consumer-reported data loss and broken workflows come before optimization work. The rule and the
release process are in [Contributing](../../CONTRIBUTING.md#priority-rule) and
[release process](release-process.md).
