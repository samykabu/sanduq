# Theme Initialization

Use this when the user wants to initialize or refresh Illustrate colors from a local design system document, for example `design.md`, `system-design.md`, `system design.md`, `brand.md`, or `docs/design-system.md`.

This is the on-demand version of the first-run style guide gate. It does not create a second skill. It updates the single source of truth: [`style-guide.md`](style-guide.md).

---

## Invocation

Typical user prompts:

- "Initialize the diagrams theme from `design.md`."
- "Point the skill at `docs/system-design.md` and grab the theme colors."
- "Refresh Illustrate from our design system file."

If the user does not provide a path, look in this order from the project root:

1. `design.md`
2. `system-design.md`
3. `system design.md`
4. `docs/design.md`
5. `docs/system-design.md`
6. `docs/system design.md`
7. `docs/design-system.md`
8. `.agents/design.md`

If none exists, ask for the path.

---

## Step 1 - Read The Design Source

Read the whole markdown file. Prefer explicit token tables, CSS variables, JSON snippets, Tailwind config snippets, or sections named:

- Colors
- Palette
- Brand
- Theme
- Design tokens
- Typography

Accept common token shapes:

```md
| Token | Value |
|---|---|
| --color-background | #fbfaf7 |
| --color-foreground | #171717 |
| --color-primary | #0f766e |
```

```css
:root {
  --background: #fbfaf7;
  --foreground: #171717;
  --primary: #0f766e;
}
```

```json
{
  "colors": {
    "background": "#fbfaf7",
    "foreground": "#171717",
    "primary": "#0f766e"
  }
}
```

---

## Step 2 - Map To Diagram Roles

Illustrate has a small semantic palette. Map broad design-system tokens into these roles:

| Diagram role | Preferred source tokens |
|---|---|
| `paper` | background, canvas, page, surface, base, app-bg |
| `paper-2` | surface, card, panel, elevated, secondary-bg |
| `ink` | foreground, text, heading, content, primary-text |
| `muted` | muted, secondary-text, caption, subtle, slate |
| `soft` | tertiary-text, placeholder, disabled, hint |
| `rule` | border, divider, hairline, outline |
| `rule-solid` | border-strong, divider-strong, outline-strong |
| `accent` | primary, brand, action, cta, link if link is the only brand color |
| `accent-tint` | primary-container, accent-bg, primary at 8-12% opacity |
| `link` | link, info, blue, interactive |

When several candidates exist, pick the smallest useful set:

- One `paper`
- One `ink`
- One `muted`
- One `accent`
- One `link` only when the design source clearly distinguishes links from brand actions

Do not import a whole rainbow palette. Diagrams use color as editorial signal, not as taxonomy.

---

## Step 3 - Derive Missing Values

If the source lacks a role:

- `paper-2`: slightly darker/lighter than `paper` by 3-6%.
- `soft`: `muted` adjusted 10-18% closer to `paper`.
- `rule`: `ink` at 12% opacity.
- `rule-solid`: `muted` at 35-45% opacity or the explicit border token.
- `accent-tint`: `accent` at 8-12% opacity.
- `link`: use the explicit link/info token, otherwise derive a readable blue or reuse `accent` only if the product has no separate link color.

Keep rgba values in the style guide when opacity is semantically important.

---

## Step 4 - Validate

Before applying:

- `ink` on `paper` must meet WCAG AA for normal text.
- `muted` on `paper` should meet WCAG AA for 11px+ text.
- `accent` must be saturated enough to read as a focal color.
- `paper` should not be pure white unless the design source is intentionally clinical/product UI.
- The diagram should still have one obvious focal color.

If the design source fails contrast, propose a minimally adjusted value and mark it as derived.

---

## Step 5 - Preview And Apply

Show a compact diff of the `style-guide.md` token table before writing. Include provenance comments:

```md
> Theme source: `docs/system-design.md`, initialized 2026-07-09.
> Derived values: `paper-2`, `rule`, `accent-tint`.
```

After approval, update only [`style-guide.md`](style-guide.md). Do not rewrite every example HTML unless the user explicitly asks for regenerated examples.

Recommended smoke check:

1. Open `assets/index.html`.
2. View `Flowchart`, `Architecture`, and `Drawing` in minimal light.
3. View one dark example to confirm contrast.

---

## Reading Priorities

When a design document contains both application UI tokens and marketing/brand tokens:

1. Use app/UI tokens for `paper`, `ink`, `muted`, `rule`.
2. Use brand/action tokens for `accent`.
3. Use link/info tokens for `link`.
4. Ignore chart-series colors unless the user explicitly asks for chart-like diagrams.
