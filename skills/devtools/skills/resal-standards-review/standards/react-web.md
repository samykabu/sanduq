# Resal React (Web) Standards

> **Inherits [`core.md`](core.md).** Read core first. Tags: **[STANDARD]** / **[GOOD-TO-HAVE]** / **[NICE-TO-HAVE]** / **⚠️**.
>
> **Baselines:** **`resal-admin-frontend`** (single Next 14 App-Router app: AntD, React Query v3, Orval REST codegen, axios, Zustand) and **`resal-frontend`** (Nx 16 monorepo: Next 13 Pages Router, React Query v4, GraphQL codegen, Tailwind, Zustand, RHF+zod, Storybook, Cypress). Where they differ, the standard picks the better and says why.
>
> **Golden rule (core):** match the app's real stack. A single product app needn't be an Nx monorepo; a monorepo needn't use every lib.

## Stack [STANDARD]

Next.js (App Router preferred for new apps) · React 18 · TypeScript 5 **strict** · **React Query** (server state) · **Zustand** (client state) · **react-hook-form + zod** (forms) · **codegen API clients** (Orval for REST, graphql-codegen for GraphQL) · Tailwind (+ AntD where a component kit is needed) · OpenFeature/Unleash (flags) · Sentry + OTel · Jest/Vitest + Testing Library + MSW · Husky + lint-staged + commitlint. Node pinned via `.nvmrc`.

**Monorepo vs single app [STANDARD]:** use the **Nx monorepo** when multiple deployable apps share `libs/{ui,stores,utils}` (enforced module boundaries, `affected` builds, remote cache). Use a **single Next App-Router app** for one self-contained product. Both ship via Dockerfile + Helm.

## 1. Structure [STANDARD]

- **App Router:** route groups `(auth)` / `(private)` organize without affecting URLs; **`_`-prefixed private folders** colocate a feature's `components/`, `graphql/`, `constants`, `hooks` and are excluded from routing — the **feature-module pattern to follow**.
- **Nx:** `apps/<app>` + `apps/<app>-e2e` + `libs/{ui,stores,utils}`; each project has `project.json` with `targets` and **`tags`** for boundary constraints.
- ⚠️ Populate Nx `tags` (`scope:*`, `type:ui`) and tighten `@nx/enforce-module-boundaries` (currently wide-open). ⚠️ Avoid flat 60+-folder `components/` with no feature grouping.

## 2. Naming [STANDARD]

- **Component files/folders: PascalCase** matching the exported component (`AddEditModal/AddEditModal.tsx`) — easier to grep. ⚠️ kebab-case component files are the other project's convention; standardize on PascalCase.
- Hooks `use*` camelCase. Codegen output `*.schemas.ts`/`*.generated.ts`. Shared libs barrel via `index.ts`. Pick **one** test suffix org-wide (`*.test.tsx` recommended).

## 3. Components [STANDARD]

Function components only; **default export only for routed entry points (`page.tsx`)**, named exports for everything reusable. Props typed with `type` (composes/unions; `interface` only for declaration-merging).
⚠️ Don't make the root `layout.tsx` `"use client"` — it forfeits RSC/streaming for the whole tree; keep layouts server and push `"use client"` islands down. ⚠️ Prefer composed children over config-array "mega-components" (a giant `FIELD_TYPE` switch pushes typing toward `any`).

## 4. State [STANDARD]

- **Server state → React Query**; **don't destructure the whole query object** — alias what you need (`const { mutate, isLoading, data } = useX()`).
- **Client state → Zustand** (`create()` + `combine`; `persist` only when it must survive reloads). State fields + actions colocated.

## 5. Data / API layer (codegen-first) [STANDARD]

**Never hand-write API calls.** Spec → codegen → typed React Query hooks. One shared **mutator/fetcher** injects base URL + bearer token + timeout + 401 redirect:

```ts
// app/api/mutator/mutator.ts (admin)
export const AXIOS_INSTANCE = Axios.create({ baseURL: process.env.NEXT_PUBLIC_BASE_URL });
export const axiosInstance = <T>(config) => {
  const user = getParsedObject(Cookies.get(USER_KEY) ?? "");
  const p = AXIOS_INSTANCE({ ...config, timeout: 30000, headers: { ...globalReqHeader,
    ...(user?.access_token ? { Authorization: `Bearer ${user.access_token}` } : {}), ...config.headers }})
    .then(({ data }) => data);
  p.catch((e) => { if (e?.response?.status === 401) { Cookies.remove(USER_KEY);
    if (e.config?.url !== "/api/v1/auth/login") location.href = `/login?next=${encodeURIComponent(location.pathname+location.search)}`; }});
  return p; };
```

**React Query client defaults [STANDARD]:** set explicit `staleTime` (per-domain, **not** `2000`), `retry`, `refetchOnWindowFocus:false`, **and** a Sentry error logger. ⚠️ Neither baseline does both — do both. **[GOOD-TO-HAVE]** proactive token-refresh gate before requests.

## 6. Forms & validation [STANDARD]

**react-hook-form + zod**, schema-per-form, i18n-aware messages, single source for runtime + TS types (`z.infer`). Where AntD `Form` is used, still derive rules from zod. ⚠️ Avoid string-heavy imperative AntD validators duplicated per EN/AR.

## 7. Styling [STANDARD]

Tailwind utility-first; **single design-token source** feeding both the Tailwind theme and (if used) the AntD `ConfigProvider`. ⚠️ Don't define the same brand color in 3 places. **RTL/Arabic:** logical CSS properties (`tailwindcss-logical`/`postcss-logical`) + one Arabic font var (`--arabic-font`). ⚠️ Global Tailwind `important:true` to beat AntD is a smell — scope it.

## 8. Routing & auth [STANDARD]

A **central `ROUTES` table** (`{path,name,label,isAuth}`) feeds both the sidebar and `middleware.ts` guarding. Middleware redirects unauthenticated users to `/login?next=…` and authenticated users off public routes. Client RBAC via a `PermissionGuard` component.
⚠️ **Auth token in a JS-readable (non-httpOnly) cookie is XSS-exposed** — prefer an httpOnly, secure cookie set by the BFF/proxy. ⚠️ Remove `console.log` from `middleware.ts` (leaks auth decisions in prod).

## 9. TypeScript [STANDARD]

`strict: true`, `moduleResolution: "bundler"`, `@/*` path alias. `tsc --noEmit` in pre-commit + CI. ⚠️ Eliminate pervasive `any` (validators, `handleApiError(error: any)`, codegen `errorType`). Be consistent on `type` vs `interface` and the `I`-prefix (recommend dropping `I`).

## 10. i18n / RTL [STANDARD for user-facing apps]

Two layers: **bilingual data fields** (`name_ar`/`name_en`) + a **UI i18n framework** (react-intl/FormatJS) with `Accept-Language` and SAR currency formatting. ⚠️ Hardcoded English strings on user-facing Arabic screens is a gap.

## 11. Error handling [STANDARD]

- **Error boundaries are required** — App Router `app/error.tsx` + `app/global-error.tsx`; a React error boundary at the estore root; report to Sentry. ⚠️ Both baselines lack these — add them.
- **Centralized API-error formatter** (`handleApiError`) unwraps the backend error shape → toast; wired into every mutation `onError`.
- ⚠️ No silent `catch {}` — log or surface.
- One toast utility per app; route-level `loading.tsx`/skeletons for loading states.

## 12. Reusable abstractions [GOOD-TO-HAVE]

Shared **`libs/ui`** package (barrel `index.ts`, each component with `.stories.tsx` + test) is the model. `SafeHtml` + **DOMPurify** as the only sanctioned HTML render (standardize on DOMPurify, not `xss`). Generic token-store factory. `cn()` helper (consider `clsx`+`tailwind-merge`). ⚠️ Don't accumulate a 1,750-line `utils.ts` — split by concern.

## 13. Auth handling [STANDARD]

Token via httpOnly secure cookie (preferred) or `tokenStore`; protected routes via `ROUTES.isAuth` + middleware; the shared mutator handles `401 → clear + redirect`; FE RBAC via `PermissionGuard`. **[GOOD-TO-HAVE]** proactive `assertFreshTokens()` refresh; device-fingerprint headers.

## 14. Testing [STANDARD]

Testing Library + **MSW** (Orval generates `*.msw.ts` handlers) + **Storybook** for shared UI + **Cypress** for critical e2e. Wrap renders in `QueryClientProvider` + `OpenFeatureProvider`. **Enforce a coverage floor.** ⚠️ "one test total" (admin) and no Storybook/e2e there is a gap.

## 15. Tooling [STANDARD]

ESLint extends `next/core-web-vitals` + **`eslint-plugin-simple-import-sort`** (8-group order) + `unicorn`. Prettier: double quotes, semicolons, `printWidth:100`, `trailingComma:"all"`. Husky + lint-staged (prettier → lint → typecheck) + **commitlint** (conventional). Nx: `cacheableOperations`, `affected.defaultBase`, raise `parallel` above 1. `next.config`: `output:"standalone"`, `X-Robots-Tag:noindex` for internal tools.

## Capability matrix

| Capability | resal-admin-frontend | resal-frontend (estore) |
|---|:--:|:--:|
| Router | Next 14 App Router | Next 13 Pages + Nx |
| API codegen | Orval (REST) | graphql-codegen |
| Server/client state | RQ v3 + Zustand | RQ v4 + Zustand |
| Forms | AntD Form (⚠️ no zod) | RHF + zod |
| UI i18n framework | ⚠️ none (data-only) | react-intl/FormatJS |
| Error boundaries | ⚠️ none | ⚠️ none |
| Tests | ⚠️ 1 test | Vitest/Jest + Storybook + Cypress |
| Shared UI lib | app-local | `libs/ui` package |

## React-web anti-patterns (+ core §15)

⚠️ no error boundaries · near-zero tests (admin) · JS-readable auth cookie + `console.log` in middleware · pervasive `any` · duplicated date libs (`dayjs`+`moment`) & duplicated design tokens · 1,750-line `utils.ts` · `"use client"` root layout · `staleTime:2000` (cache near-useless) · global `important:true` Tailwind · silent `catch {}` · tooling drift between apps (quotes, RQ v3/v4, intl vs hardcoded, kebab vs Pascal, `*.spec` vs `*.test`, empty Nx tags, `parallel:1`).

## Checklists

**New app:** App Router (or Nx if multi-app) · strict tsconfig + `@/*` · React Query (explicit defaults + Sentry logger) + Zustand · Orval/graphql codegen + one shared mutator (token+401+timeout) · RHF+zod · Tailwind + single token source + logical-property RTL + react-intl · central `ROUTES` + middleware guard + `PermissionGuard` · `app/error.tsx`+`global-error.tsx` + Sentry · DOMPurify `SafeHtml` · Testing Library + MSW + Storybook + Cypress + coverage floor · ESLint(simple-import-sort+unicorn)+Prettier(100/double)+husky/lint-staged/commitlint · httpOnly auth cookie · Dockerfile+Helm.

**New feature:** `_/`-private folder (components/graphql/hooks/constants) · codegen hooks (don't hand-write) · zod schemas · PascalCase components, named exports · loading + error states · tests + MSW handlers.
