# Resal Engineering Standards

The canonical, multi-stack engineering standards for Resal. **Read [`core.md`](core.md) first** (the cross-cutting spine every project inherits), then the file for your stack.

## The documents

| File | Scope | Baseline exemplar |
|---|---|---|
| [`core.md`](core.md) | Cross-cutting principles for **all** stacks: layering, naming, config & secrets, error handling, logging/observability, resilience, security, testing, API design, docs, commits, CI/CD, **and the severity rubric** | — |
| [`python.md`](python.md) | Python / FastAPI services | OrderMs (+ fleet) |
| [`dotnet.md`](dotnet.md) | .NET (C#) services | ResalPay |
| [`react-web.md`](react-web.md) | React web apps (Next.js / Nx) | resal-admin-frontend + resal-frontend |
| [`react-native.md`](react-native.md) | React Native (Expo) apps | resal-mobile |

Each per-stack file is the **concrete expression** of `core.md` in that ecosystem and follows the same section structure (structure, naming, layering, config, contracts/validation, API, persistence, errors, logging/observability, async/eventing, caching, auth/security, resilience, testing, tooling, build/deploy, anti-patterns, capability matrix, checklists). Rules are tagged **[STANDARD]** / **[GOOD-TO-HAVE]** / **[NICE-TO-HAVE]**; deviations are flagged **⚠️**.

## Which file applies to my project? (detection map)

| If the project has… | It's | Read |
|---|---|---|
| `*.csproj` / `*.sln` | **.NET** | `core.md` + `dotnet.md` |
| `package.json` with `react-native`/`expo` | **React Native** | `core.md` + `react-native.md` |
| `package.json` with `react`/`next`/`@nx/react` (no RN) | **React web** | `core.md` + `react-web.md` |
| `pyproject.toml` / `app/` + FastAPI | **Python** | `core.md` + `python.md` |
| more than one of the above (monorepo) | **multi** | `core.md` + each detected stack's file |

This is the same detection the **`resal-standards-review`** skill uses to auto-pick which rules to audit a project against.

## How to use

- **Engineers:** read `core.md` + your stack file during onboarding; use the checklists at the bottom of each stack file when creating a service or a feature.
- **Reviewers / AI assistants:** invoke the `resal-standards-review` skill (or ask to "review &lt;project&gt; against the Resal standards"). It detects the stack, produces a severity-rated **Compliance & Gaps Report**, and — in full mode — asks which severity tiers to fix before writing a **Remedy Plan**. Add "report only" for report-only mode.

## Golden rule

**Match the project's real, in-use stack — never flag a capability the project legitimately doesn't use.** The standards describe how Resal's best code looks; not every project uses every capability, and that's fine (each stack file has a capability matrix showing what's optional).

## Provenance

Derived from analysis of Resal's strongest project per stack plus mainstream industry best practice. The legacy single-file Python standard at `D:\Resal-Coding-Standards.md` now points here; its content lives in `core.md` + `python.md`.
