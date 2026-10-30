# Prerequisites

Install only the tools your [adoption level](../reference/glossary.md#adoption-level) needs. The
"Needed by" column tells you which ones. "Tested" is the version Sanduq's CI or maintainers ran.
"Unverified" means nobody has recorded a test yet.

## Tools

| Tool | Needed by | Tested |
| --- | --- | --- |
| Spec Kit (`specify` CLI) | Every extension | 1.1.3, commit `0282d03` |
| Python 3.11 or later | Every extension; Illustrate export; User Manual builds; Workflow's guard hook (`python3`, or `python` on Windows, on `PATH`) | 3.13 in CI; 3.11 for the Linux regression suites |
| Node.js and npm | `npx skills`; Delegate Task (18 or later); Illustrate's hand-drawn generator | `skills` 1.7.2 in CI; Node unverified |
| Git | Workflow, Memory, Scope (required); others (optional) | Unverified |
| GitHub CLI (`gh`) with Project scopes | Workflow, Scope (required); Project, PR (optional) | Unverified |
| GitHub Project (v2) board with seven statuses | Managed Workflow ([board setup](../scenarios/managed-workflow.md#board)) | Live runs on Claude Code |
| Playwright and Chromium | Illustrate PNG export; User Manual screenshots | Playwright 1.63.0 |
| PyYAML; MkDocs, Material for MkDocs and the PDF libraries only for the MkDocs renderer | User Manual builds (`markdown` and `command` renderers need only PyYAML and your own tool) | Material 9.7.6, `mkdocs-to-pdf` 0.10.1 |
| `age` | User Manual previews in a public repository | Unverified |
| SuperSpec | Workflow, optional task generator and executor | 1.0.2, commit `c20ac6c` |
| Superpowers Bridge | Optional; Workflow routes around an existing Bridge run | Unverified |
| Superpowers | Required by Superpowers Bridge | Unverified |

## Spec Kit

Install the tested revision. Progress needs Spec Kit 1.1.1 or later; Workflow's installer refuses
Progress on an older Spec Kit. The command uses `uv`; the
[Spec Kit installation guide](https://github.com/github/spec-kit#installation) explains how to get it.

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@0282d03eb6fc3091b3deaa3a855d4030dc40cd6c
specify --version
```

To track the latest Spec Kit instead, drop the `@<commit>` suffix. A newer Spec Kit is allowed by the
manifests but is not a tested combination. The same commit is pinned in
[CI](../../.github/workflows/ci.yml) and in Workflow's
[`dependencies.json`](../../extensions/workflow/dependencies.json).

Each package declares its own Spec Kit range. This is information, not a problem to fix:

| Package | Spec Kit range |
| --- | --- |
| Assure, Illustrate, PR, Project, User Manual | `>=0.2.0` |
| Scope | `>=1.0.0` |
| Memory, Workflow, `workflow` preset | `>=1.0.0,<2.0.0` |
| Progress | `>=1.1.1.dev0,<2.0.0` |
| `scope-gate`, `scope-brainstorm` presets | `>=1.0.0` |

## Python

Every package declares Python 3.11 or later (Illustrate as optional, for its export scripts). Memory
and Progress read TOML with the standard library, which 3.11 added. CI runs the Linux regression
suites on 3.11 and everything else, including the Windows suites, on 3.13.

<details>
<summary>Install Python</summary>

| OS | Command |
| --- | --- |
| Windows | `winget install Python.Python.3.13` |
| macOS | `brew install python@3.13` |
| Linux (Debian, Ubuntu) | `sudo apt-get install python3 python3-venv python3-pip` |

</details>

## Node.js

You need Node.js for `npx skills`, for Delegate Task (Node 18 or later), and for Illustrate's
hand-drawn generator. The generator needs its own packages: run `npm install` in the installed
Illustrate `skill/` directory, then `npm run generate:hand`.

<details>
<summary>Install Node.js</summary>

| OS | Command |
| --- | --- |
| Windows | `winget install OpenJS.NodeJS.LTS` |
| macOS | `brew install node` |
| Linux (Debian, Ubuntu) | `sudo apt-get install nodejs npm` |

</details>

## Git and the GitHub CLI

Workflow and Scope read and write GitHub issues and Projects. Project and PR use `gh` when it is
available and skip remote work when it is not.

<details>
<summary>Install Git and the GitHub CLI</summary>

| OS | Command |
| --- | --- |
| Windows | `winget install Git.Git GitHub.cli` |
| macOS | `brew install git gh` |
| Linux (Debian, Ubuntu) | `sudo apt-get install git gh` |

</details>

Sign in, then add the Project scopes:

```bash
gh auth login
gh auth refresh -h github.com -s project,read:project
gh auth status
```

## Playwright and Chromium

Illustrate needs these for PNG export. User Manual screenshots use your project's own Playwright runner.

```bash
python -m pip install playwright==1.63.0
python -m playwright install chromium
```

On Linux, add `--with-deps` to the second command to install Chromium's system libraries.

## User Manual renderers, MkDocs and PDF libraries

User Manual Init writes three install files. Install the one your `renderer.kind` in
`User-Manual/manual.yml` needs:

| File | Pins | For |
| --- | --- | --- |
| `requirements.lock` | `PyYAML` | Every build; enough for the `markdown` (default) and `command` renderers |
| `requirements-mkdocs.lock` | adds `mkdocs` (1.6 or later, below 2) and `mkdocs-material` 9.7.6 | The `mkdocs` renderer's HTML site |
| `requirements-pdf.lock` | adds `mkdocs-to-pdf` 0.10.1 | `--pdf` with the `mkdocs` renderer |

```bash
python -m pip install -r User-Manual/requirements.lock
```

A `command` renderer runs your own tool (for example Pandoc or Quarto); install it on the build
machine or the CI runner. PDF builds with the `mkdocs` renderer also need native text-layout
libraries:

| OS | Command |
| --- | --- |
| Linux (Debian, Ubuntu) | `sudo apt-get install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libharfbuzz-subset0 fonts-hosny-amiri` |
| macOS | `brew install pango` |
| Windows | Unverified. Install the Pango libraries for your Python, or build PDFs in CI on Linux. |

Arabic PDFs use the Amiri font (`fonts-hosny-amiri` above). On macOS, install Amiri from
[Google Fonts](https://fonts.google.com/specimen/Amiri); without it the PDF falls back to Noto Naskh Arabic
or another Arabic font the system has.

Public repositories publish encrypted previews and need `age` in CI. See
[the docs pack](install-by-host.md#docs-pack).

## SuperSpec

SuperSpec is an optional Spec Kit extension. When it is installed and enabled, Workflow uses its
Brainstorm, Tasks and Execute commands instead of the core ones. Install the tested commit:

```bash
git clone https://github.com/WangX0111/superspec.git
git -C superspec checkout c20ac6c1ba069cc9a72dacb8044b7b193d3dde81
specify extension add --dev ./superspec
```

## Superpowers Bridge and Superpowers

[Superpowers Bridge](https://github.com/lihan3238/speckit-superpowers-bridge) is an optional Spec Kit
extension that hands Spec Kit tasks to [Superpowers](https://github.com/obra/superpowers). Bridge 1.3.0
requires Superpowers 5.1 or later. Follow each project's README to install it on your host. In a managed
project, run `python .specify/extensions/workflow/scripts/install.py --apply --with-aliases` after adding
the Bridge; it clears the doctor findings the Bridge install leaves. Workflow's overlays route Bridge
commands to the current owner so two executors never run.

## Who enforces dependencies

An extension's manifest lists hard dependencies under `requires.extensions`. **Spec Kit records these
but does not install or check them.** Two Sanduq mechanisms do:

- **Workflow's installer** (`install.py`) installs Scope, Project, PR, Illustrate and the selected
  Assure or User Manual at the versions pinned in `dependencies.json`.
- **`deps.py ensure`** runs inside Assure, PR and User Manual before they need Illustrate. It follows
  `.specify/extension-dependencies.yml`: `prompt` (the default) asks you, `auto` installs, and `manual`
  stops with a message.

If you install Scope by itself, nothing installs Workflow for you. Install Workflow instead.

## Limits

- Most tool versions are unverified. Host and platform results are in [compatibility](../reference/compatibility.md).
- PDF builds on Windows are unverified.
- Sanduq does not test every Spec Kit version a manifest range allows.
