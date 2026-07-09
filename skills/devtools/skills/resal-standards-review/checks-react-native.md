# Check Catalog — React Native

Stack-specific checks for **React Native** apps (Expo managed). **Run these `RN-*` checks AND all `CORE-*` checks** (`checks-core.md`). Enforces `./standards/react-native.md` + `core.md`.

> **No double-counting:** a concern matching a CORE check is recorded under the CORE id. `RN-*` are RN-specific concerns. Gate on the stack profile (Expo vs bare; React Navigation vs expo-router; GraphQL vs REST; twrnc vs NativeWind).
> ⚠️ Mobile security checks here are **high-stakes** — tokens, secrets, screen capture.

---

## RN-STRUCT — Structure & navigation

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-STRUCT-01` | always | Expo `app.config.js`; native `/ios`/`/android` gitignored + regenerated (`expo prebuild`). Committed native dirs (managed app) → finding. | Nice-to-have |
| `RN-NAV-01` | always | **Typed navigators**: `createNativeStackNavigator<XStackParams>()` with exported param unions; `NavigatorScreenParams<>` for nesting; centralized typed deep-link `LinkingOptions`. Untyped navigation → finding. | Medium |
| `RN-NAV-02` | has auth | **Conditional auth-stack / app-stack switch** keyed on `loggedIn()`, not auth+app in one stack with per-screen guards. | Medium |

## RN-COMP — Components & lists

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-COMP-01` | always | Function components; props via `interface XProps`; screen props typed from the nav stack. | Medium |
| `RN-COMP-02` | long lists | List callbacks (`renderItem`/`keyExtractor`/footers) memoized with `useCallback`; **`FlashList` for large lists**; `React.memo` on hot rows. All-`FlatList` + no memo on big lists → finding. | Nice-to-have |

## RN-STATE — State

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-STATE-01` | always | React Query (server) + Zustand (client); QueryClient configured once with a global auth-error logout; Zustand `persist` + narrow selectors + `_hydrated`. | Medium |
| `RN-STATE-02` | always | Global RQ `retry`/`networkMode` policy set (not just defaults). | Nice-to-have |

## RN-API — Data/API layer

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-API-01` | calls a backend | Single network client (`utils/fetcher.ts`): token from secure source, refresh-before-request, normalize errors, Sentry on failure, thread `AbortSignal`. Per-call hand-rolled clients → finding. | High |
| `RN-API-02` | calls a backend | Codegen (graphql-codegen/Orval) → typed RQ hooks wired to the one fetcher. | Medium |
| `RN-API-03` | always | **No `console.log` of queries/variables/responses in production** (PII leak). Grep `console.log` in `fetcher`/api → finding. | Medium |
| `RN-API-04` | always | Offline/NetInfo awareness in the data layer (NetInfo installed → used). | Nice-to-have |

## RN-FORM — Forms

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `RN-FORM-01` | has forms | react-hook-form + zod via `zodResolver`; schema as a function of `t` (localized messages); `Controller`-wrapped inputs. | Medium |

## RN-STYLE — Styling & RTL

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-STYLE-01` | always | Single styling system (twrnc) from one config; design tokens single-sourced; safe-area insets. | Nice-to-have |
| `RN-STYLE-02` | Arabic UI | **RTL via `I18nManager`** (true mirrored layout), not per-component `text-left` approximation. | Medium |
| `RN-STYLE-03` | declares dark mode | If `userInterfaceStyle:'automatic'`, a real dark theme exists. | Nice-to-have |

## RN-TS — TypeScript

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-TS-01` | always | `strict` + `strictNullChecks` + `noImplicitAny`; aliases synced in `tsconfig` + `babel.config`; `tsc --noEmit` in pre-commit + CI. | Medium |
| `RN-TS-02` | always | No pervasive `any` — prefer `unknown` + narrowing. Heavy `: any` → finding. | Medium |

## RN-I18N — Localization

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `RN-I18N-01` | bilingual app | Type-safe i18n (dotted-path keys) + locale from `expo-localization`; missing keys fail loudly, not silent placeholder. | Medium |

## RN-SEC — Secure storage & mobile security (high-stakes)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-SEC-01` | has auth | **Live `accessToken`/`refreshToken` (and PII-bearing RQ cache) NOT in plaintext AsyncStorage** — must be `expo-secure-store`/Keychain. Tokens persisted to AsyncStorage → **Critical**. | Critical |
| `RN-SEC-02` | always | **`.env*` not committed** (`react-native-dotenv` inlines into the JS bundle). Committed `.env`/`.env.staging`/`.env.production` with live tokens → **Critical**. *Cross-ref CORE-SEC-01/04 — record once here under RN-SEC-02, do not also raise a separate CORE-SEC finding.* | Critical |
| `RN-SEC-03` | biometric/sensitive | Sensitive ops gated by `expo-local-authentication` (`biometricsSecurityLevel:'strong'`, `disableDeviceFallback:true`). | Medium |
| `RN-SEC-04` | payment/card screens | `preventScreenCaptureAsync` on sensitive screens (not just screenshot detection); consider SSL pinning. | Nice-to-have |

## RN-ERR — Error handling & crash reporting (RN detail for CORE-ERR/CORE-LOG)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-ERR-01` | always | **React error boundary with fallback UI** (`Sentry.ErrorBoundary`) — not only `Sentry.wrap`. Missing → finding (record under **CORE-ERR-02**). | High |
| `RN-ERR-02` | always | Sentry init (`enabled:!__DEV__`, env+release+`dist`=update id, nav integration); explicit loading/empty states + RefreshControl. | Medium |

## RN-PERF — Performance

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-PERF-01` | always | Hermes on; Metro `inlineRequires`; narrow selectors. **[good-to-have]** `expo-image`, Android Proguard/R8 in release, lazy heavy screens. | Nice-to-have |

## RN-TEST — Testing (RN detail for CORE-TEST)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-TEST-01` | always | Jest + `@testing-library/react-native` (preset `jest-expo`) + MSW; co-located `*.spec.tsx`. Missing → finding. | High |
| `RN-TEST-02` | always | Coverage gate; Detox e2e for critical flows. | Nice-to-have |

## RN-TOOL — Tooling

| ID | Applies | Detection | Default |
|---|---|---|---|
| `RN-TOOL-01` | always | **ESLint present** (RN config), Prettier, **commitlint**, **lint-staged**, husky pre-commit (`typecheck` + lint). No ESLint at all → **High**. | High |
| `RN-TOOL-02` | always | EAS Build/Update profiles per env; pinned Node; `env.d.ts` types dotenv; `patch-package` in postinstall. | Nice-to-have |

---

## React-Native anti-patterns (also flag)
**live tokens in plaintext AsyncStorage** (RN-SEC-01, Critical) · **committed `.env*` + bundle-inlined secrets** (RN-SEC-02, Critical) · **no React error boundary** (RN-ERR-01/CORE-ERR-02) · **no ESLint/commitlint/lint-staged** (RN-TOOL-01) · `console.log` queries in prod (RN-API-03) · screenshot detected-not-prevented; no SSL pinning (RN-SEC-04) · auth+app in one stack (RN-NAV-02) · RTL per-component not I18nManager; dark mode declared-not-implemented (RN-STYLE-02/03) · no offline/NetInfo or RQ retry policy (RN-API-04/RN-STATE-02) · pervasive `any` (RN-TS-02) · all-FlatList/no FlashList/React.memo unused/partial expo-image/Proguard off/no Detox (RN-COMP-02/RN-PERF-01/RN-TEST-02) · inconsistent file casing.
