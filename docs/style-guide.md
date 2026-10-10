# Documentation style guide

Write for a developer who is new to Sanduq. Most readers want to install one thing and see it work.

## Voice

- Address the reader as "you".
- Put one idea in each sentence.
- Use the active voice: "Workflow writes the receipt", not "the receipt is written".
- Prefer short, common words. Write "use", not "utilize".
- Give the command or example before the explanation when you can.

## Terms

- Define each term the first time a page uses it, and link it to the [glossary](reference/glossary.md).
- Use one name for one thing. For example, say "Workflow", not "the delivery workflow" on one page and
  "Sanduq Delivery" on the next.
- Name only the upstream tools users install: Spec Kit, SuperSpec, Superpowers Bridge, Superpowers,
  GitHub CLI, MkDocs and Playwright.

## Caveats

Put caveats in a short "Limits" list near the end of the page. Do not repeat a caveat in every
paragraph. A limit says what does not work and what to do instead.

## Commands and prompts

- Show Codex syntax (`$speckit-assure-analyze`) and say where Claude Code differs (`/speckit-assure-analyze`).
  The [command reference](reference/commands.md#command-names) has the full table.
- Use `<details>` blocks when a step differs by host.
- Use the shared example: the synthetic booking application, issue 412 and `specs/412-refund-approval/`.

## Links

- Use relative links inside `docs/`.
- Package READMEs ship inside their archives. They use absolute
  `https://github.com/samykabu/sanduq/blob/main/...` links for anything outside the package.
- User pages do not link to `docs/internal/`. Only `CONTRIBUTING.md` does.
- When you move a page, leave a one-line forwarding stub at the old path for one release cycle.

## Banned words

`check_docs.py` rejects these words in user-facing pages, outside code: `simply`, `just`,
`obviously`, `seamless`, `seamlessly`, `leverage`, `effortless`. They either hide a step the reader
finds hard or add nothing.

## Generated content

Do not edit text between `<!-- generated:... -->` markers by hand. Run
`python extensions/scripts/check_docs.py --write` instead.
