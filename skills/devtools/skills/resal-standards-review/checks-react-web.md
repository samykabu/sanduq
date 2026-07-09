# Check Catalog — React (Web)

Stack-specific checks for **React web** apps (Next.js App Router / Nx monorepo). **Run these `RW-*` checks AND all `CORE-*` checks** (`checks-core.md`). Enforces `./standards/react-web.md` + `core.md`.

> **No double-counting:** a concern matching a CORE check is recorded under the CORE id; the "React-web detection for CORE checks" notes just give JS/TS evidence patterns. `RW-*` are React-web-specific concerns.
> Gate every check on the stack profile (detect: App Router vs Pages vs Nx; AntD vs Tailwind-only; REST/Orval vs GraphQL codegen; react-intl vs none).

---

## RW-STRUCT — Structure

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-STRUCT-01` | App Router | Route groups `(auth)`/`(private)`; feature internals in `_`-prefixed folders. Flat 50+-folder `components/` with no feature grouping → finding. | Nice-to-have |
| `RW-STRUCT-02` | Nx | `project.json` `tags` populated and `@nx/enforce-module-boundaries` constrains deps. Empty `tags: []` / wide-open `*→*` → finding. | Medium |

## RW-COMP — Components

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-COMP-01` | always | Function components; **default export only for `page.tsx`/routed entry**; named exports elsewhere. | Medium |
| `RW-COMP-02` | App Router | Root `layout.tsx` is NOT `"use client"`; client islands pushed down. Grep `"use client"` at top of `app/layout.tsx` → finding. | Medium |
| `RW-COMP-03` | always | Composition over config-array mega-components (a giant `FIELD_TYPE` switch driving everything) that force `any`. | Nice-to-have |

## RW-STATE — State

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-STATE-01` | uses React Query | Server state via React Query; client state via Zustand. | Medium |
| `RW-STATE-02` | uses React Query | Query objects not fully destructured (alias needed fields). | Nice-to-have |

## RW-API — Data/API layer

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-API-01` | calls a backend | **Codegen-first** (Orval/graphql-codegen); no hand-written axios/fetch calls per feature. Hand-rolled clients → finding. | Medium |
| `RW-API-02` | calls a backend | **One shared mutator/fetcher** injects base URL + bearer token + timeout + 401 redirect. Token/base-URL logic duplicated across calls → finding. | High |
| `RW-API-03` | uses React Query | Explicit `QueryClient` defaults (`staleTime` per-domain, `retry`, `refetchOnWindowFocus:false`) **and** a Sentry error logger. `staleTime:2000`/no defaults → finding. | Medium |

## RW-FORM — Forms

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `RW-FORM-01` | has forms | **react-hook-form + zod** schema-per-form (single source for runtime + types). String-heavy imperative validators duplicated per EN/AR → finding. | Medium |

## RW-STYLE — Styling

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-STYLE-01` | always | **Single design-token source** feeding Tailwind theme + (if used) AntD `ConfigProvider`. Same color defined in multiple places → finding. | Nice-to-have |
| `RW-STYLE-02` | Arabic UI | RTL via logical CSS properties + one Arabic font var. | Medium |
| `RW-STYLE-03` | uses AntD+Tailwind | Global Tailwind `important:true` to beat AntD is scoped, not blanket. | Nice-to-have |

## RW-ROUTE — Routing & auth

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-ROUTE-01` | protected app | Central `ROUTES` table feeds sidebar + `middleware.ts` guard; `PermissionGuard` for FE RBAC. | Medium |
| `RW-ROUTE-02` | has auth | **No `console.log` in `middleware.ts`** (leaks auth decisions in prod). Grep → finding. | Medium |

> Auth-token storage → record under **CORE-SEC** (RW detection: token in a JS-readable non-httpOnly cookie / localStorage → High; prefer httpOnly secure cookie).

## RW-TS — TypeScript

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-TS-01` | always | `strict:true`, `moduleResolution:"bundler"`, `@/*` alias; `tsc --noEmit` in pre-commit + CI. | Medium |
| `RW-TS-02` | always | No pervasive `any` (validators, `handleApiError(error:any)`, codegen `errorType:"any"`). Heavy `: any` → finding. | Medium |

## RW-I18N — Localization

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `RW-I18N-01` | user-facing Arabic | UI i18n framework (react-intl/FormatJS) + bilingual data fields. Hardcoded English on user-facing screens → finding. | Medium |

## RW-ERR — Error handling (React-web detail for CORE-ERR)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-ERR-01` | always | **Error boundaries present** — App Router `app/error.tsx` + `app/global-error.tsx`, or a React error boundary at root, reporting to Sentry. Missing → finding (record under **CORE-ERR-02**). | High |
| `RW-ERR-02` | always | Centralized API-error formatter wired into mutation `onError`; one toast utility. | Medium |

> Silent `catch {}` → **CORE-ERR-01** (RW detection: grep `catch {}` / `catch (e) {}` with no body).

## RW-UI — Reusable abstractions

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-UI-01` | shared components | Shared UI as a `libs/ui` package (barrel + stories + tests), not duplicated app-local. | Nice-to-have |
| `RW-UI-02` | renders HTML | `SafeHtml` + **DOMPurify** is the only HTML render path; no raw `dangerouslySetInnerHTML`. | High |
| `RW-UI-03` | always | No monolithic catch-all `utils.ts` (route table + validators + CSV + payments in one 1000+-line file). | Nice-to-have |

## RW-TEST — Testing (React-web detail for CORE-TEST)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-TEST-01` | always | Testing Library + MSW (Orval `*.msw.ts`); Storybook for shared UI; Cypress for critical e2e. Near-zero tests → finding. | High |

## RW-TOOL — Tooling

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RW-TOOL-01` | always | ESLint `next/core-web-vitals` + `simple-import-sort` (+ unicorn); Prettier (double quotes, semi, printWidth 100); husky + lint-staged + commitlint. | Medium |
| `RW-TOOL-02` | always | Date lib not duplicated (`dayjs` + `moment` both present → finding). | Nice-to-have |
| `RW-TOOL-03` | Nx | `cacheableOperations` set; `parallel` > 1. | Nice-to-have |

---

## React-web anti-patterns (also flag)
no error boundaries (RW-ERR-01/CORE-ERR-02) · near-zero tests (RW-TEST-01/CORE-TEST-01) · JS-readable auth cookie + `console.log` in middleware (CORE-SEC/RW-ROUTE-02) · pervasive `any` (RW-TS-02) · duplicated date libs/tokens (RW-TOOL-02/RW-STYLE-01) · 1,750-line utils (RW-UI-03) · `"use client"` root layout (RW-COMP-02) · `staleTime:2000` (RW-API-03) · global `important:true` · silent `catch {}` (CORE-ERR-01).
