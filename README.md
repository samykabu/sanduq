# 🧰 sanduq

> **sanduq** (صندوق) — Arabic for *chest / toolbox*. A chest of shared AI-agent tooling:
> **Spec Kit extensions**, **Claude Code plugins**, and **skills** — reusable across all
> your projects and any assistant (Claude Code, Codex, Copilot, OpenCode).

One repo, two marketplaces:

- **Spec Kit extension catalog** → [`catalog.json`](catalog.json)
- **Claude Code plugin marketplace** → [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)

```
sanduq/
├── catalog.json                     # Spec Kit extension catalog (add its raw URL to a repo)
├── .claude-plugin/marketplace.json  # Claude Code plugin marketplace manifest
├── extensions/                      # Spec Kit extensions
│   └── project/                     # GitHub Project lifecycle sync
├── plugins/                         # Claude Code / MCP plugins
├── skills/                          # shareable agent skills
└── install.{ps1,sh}                 # copy an extension into a target Spec Kit repo
```

## Contents

### Spec Kit extensions

| id | what it does |
| --- | --- |
| [`project`](extensions/project/) | Mirrors each Spec Kit feature onto a GitHub Project (v2) — a parent feature issue whose Status advances through the lifecycle, plus one native sub-issue per task, closed as tasks are checked off. Board-agnostic, idempotent, no-regress. |

### Plugins / skills

_None yet — add Claude Code plugins under `plugins/` (and register them in
`.claude-plugin/marketplace.json`), and standalone skills under `skills/`._

## Use it in another project

### As a Spec Kit extension catalog

Add this catalog to the target repo's `.specify/extension-catalogs.yml`:

```yaml
catalogs:
  - name: sanduq
    url: https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
    priority: 10
    install_allowed: true
```

Then install an extension (the Spec Kit installer wires the hooks and renders the commands
into every assistant target you have — `.claude/`, `.github/`, `.agents/`, `.opencode/`):

```bash
speckit extension install project
```

No catalog / no Spec Kit CLI? Copy it in manually from a checkout of this repo:

```bash
# from the target repo root:
pwsh /path/to/sanduq/install.ps1 -Extension project        # Windows
/path/to/sanduq/install.sh --extension project             # macOS/Linux
```

### As a Claude Code plugin marketplace

```
/plugin marketplace add samykabu/sanduq
/plugin install <plugin>@sanduq
```

## The `project` extension in 30 seconds

```bash
gh auth refresh -h github.com -s project,read:project   # one-time scope
speckit extension install project                       # install + wire hooks
speckit project init                                    # discover board + map columns
# thereafter /speckit.specify, /plan, /tasks, /implement move the board automatically
```

See [`extensions/project/README.md`](extensions/project/README.md) for the full lifecycle,
column mapping, and safety notes.

## Publishing (maintainer)

Push a tag `<extension>-vX.Y.Z` (e.g. `project-v1.0.0`); the
[release workflow](.github/workflows/release.yml) packages `extensions/<id>/` into
`<id>.zip` and attaches it to the release, which `catalog.json`'s `download_url` points at.
Bump the version in both `extensions/<id>/extension.yml` and `catalog.json`.

## License

MIT © Samy K. Abushanab
