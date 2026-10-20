# Install by host

Pick your [host](../reference/glossary.md#host). Each section covers
[portable skills](../reference/glossary.md#portable-skill), Spec Kit
[extensions](../reference/glossary.md#extension), and how you type commands. Install the
[prerequisites](prerequisites.md) first.

Supported hosts are Codex, Claude Code and Claude Desktop. Host support is unverified until the host
test phase records evidence; see [compatibility](../reference/compatibility.md).

## Hosts

<details>
<summary><strong>Codex</strong></summary>

**Skills.** Portable skills live in [sanduq-skills](https://github.com/samykabu/sanduq-skills).

```bash
npx skills add samykabu/sanduq-skills --list
npx skills add samykabu/sanduq-skills --skill user-manual -a codex
```

Add `-g` to install for your user instead of the project. Codex reads project skills from
`.agents/skills/`. Start a new session after installing.

**Plugin bundles.** Codex reads the Sanduq marketplace from `.agents/plugins/marketplace.json`. It
lists the same bundles, pinned to the same releases, as the Claude Code marketplace:

```bash
codex plugin marketplace add samykabu/sanduq
codex plugin add dev-tools@sanduq
codex plugin add illustration-tools@sanduq
codex plugin add agent-tools@sanduq
```

A Codex install of these bundles has not been exercised yet. Each bundle carries a root
`plugin.json` (Agent Plugins 1.0.0) next to its Claude Code manifest; report anything that fails.

**Extensions.** Initialize Spec Kit for Codex and register the catalog:

```bash
specify init --here --integration codex
specify extension catalog add --name sanduq --priority 1 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

Then add extensions. To add all nine extensions, use the [dependency-ordered block](#all-nine-extensions).

**Command syntax.** Skills: `$user-manual`. Extension commands: `$speckit-assure-analyze`.

</details>

<details>
<summary><strong>Claude Code</strong></summary>

**Skills.** Use the Sanduq plugin marketplace, which installs [plugin bundles](../reference/glossary.md#plugin-bundle)
from [sanduq-skills](https://github.com/samykabu/sanduq-skills):

```text
/plugin marketplace add samykabu/sanduq
/plugin install dev-tools@sanduq
/plugin install illustration-tools@sanduq
/plugin install agent-tools@sanduq
```

Or install single skills with `npx skills`:

```bash
npx skills add samykabu/sanduq-skills --skill illustrate -a claude-code
```

**Extensions.** Initialize Spec Kit for Claude Code and register the catalog:

```bash
specify init --here --integration claude
specify extension catalog add --name sanduq --priority 1 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

Then add extensions. To add all nine extensions, use the [dependency-ordered block](#all-nine-extensions).

**Command syntax.** Plugin skills: `/dev-tools:user-manual`. Skills from `npx skills`: `/user-manual`.
Extension commands: `/speckit-assure-analyze`.

</details>

<details>
<summary><strong>Claude Desktop</strong></summary>

**Skills only.** Extensions are not supported, because Claude Desktop does not run Spec Kit.

Install a bundle from the Sanduq plugin marketplace, or upload a skill as a zip file. The
[sanduq-skills README](https://github.com/samykabu/sanduq-skills) has the steps for both. Scripts
that need Python, Node.js or Playwright run only where Claude Desktop can run them.

**Command syntax.** Ask for the skill by name, for example "Use the illustrate skill to draw…".

</details>

## All nine extensions

Run these after registering the catalog. The order installs each dependency before the extension
that needs it.

```bash
specify extension add illustrate
specify extension add assure
specify extension add user-manual
specify extension add pr
specify extension add project
specify extension add progress
specify extension add workflow
specify extension add scope    # requires workflow; the community catalog uses the same ID
specify extension add memory   # the community catalog uses the same ID
```

The community catalog publishes unrelated `scope` and `memory` extensions. If you keep Spec Kit's
default catalogs, [register Sanduq's catalog ahead of them](install-speckit.md#if-you-keep-spec-kits-default-catalogs).

If you use Workflow, you do not need this block. Add `workflow` and run its init; its installer adds
Scope, Project, PR, Illustrate and your selected processes. That is the safest way to get Sanduq's
Scope.

## Set recipes

### QA pack

Illustrate and Assure. You get test-readiness analysis before implementation and a QA walkthrough
after it.

```bash
specify extension add illustrate
specify extension add assure
```

```text
$speckit-assure-init Configure required QA analysis and tester documentation for this project.
```

### Docs pack

Illustrate, User Manual and PR. You get an application manual that updates with each feature, and a
PR description with diagrams.

```bash
specify extension add illustrate
specify extension add user-manual
specify extension add pr
```

```text
$speckit-user-manual-init Discover our modules, interview me about audiences, and propose the module map.
```

Previews of the manual are built in CI for each PR:

- **Private repository.** The preview is a CI artifact. Anyone with read access to the repository can
  download it.
- **Public repository.** The preview is encrypted with `age`. Before the first PR, create an `age` key
  pair, keep the private key outside the repository and CI, and set the public key as the
  `USER_MANUAL_PREVIEW_AGE_RECIPIENT` Actions variable.
- **Hosted previews** need a provider your project has approved. Administrator and Technical
  editions need real access control on that host.

### Managed pack

Workflow only. Its installer adds the extensions it needs.

```bash
specify extension add workflow
```

```text
$speckit-workflow-init Enable QA and User Manual. Use our existing GitHub Project and an advisory managed-only evidence gate.
$speckit-workflow-doctor Verify project readiness and installed host commands.
```

Continue with the [managed-workflow scenario](../scenarios/managed-workflow.md).

## What the Workflow installer adds to each host

`install.py` and `reconcile` write these for every installed host, and rerunning either restores
them. A failed install rolls them back.

| File | Claude Code | Codex |
| --- | --- | --- |
| Guard hook (PreToolUse on `Bash`) | `.claude/settings.json` | `.codex/hooks.json` |
| Worker and reviewer role agents | `.claude/agents/sanduq-worker.md`, `sanduq-reviewer.md` | `.codex/agents/sanduq-worker.toml`, `sanduq-reviewer.toml` |

- **Guard hook.** It refuses `git add -A`, `git add .` and `git stash` in every session, with a
  one-line reason, unless `SANDUQ_ROLE=coordinator` is set. It refuses the coordinator-only
  `delegate_dispatch.py` commands (`trust-reset`, `accept`, `reassign`, `adopt`) only to a worker:
  a subagent session (the host sends `agent_id` or `agent_type`), a delegated run
  (`SANDUQ_DELEGATED_RUN` set) or `SANDUQ_ROLE=worker`. Your top-level session runs them as before.
  The installer merges its one entry into the hook file and keeps your other settings and hooks.
  Codex runs project hooks only in a trusted project after you approve them: open Codex in the
  project, run `/hooks` and approve the Sanduq guard. The installer writes `python` on Windows and
  `python3` elsewhere into the hook command, so that name must be on `PATH`; without the installed
  guard script the hook allows everything.
- **Role agents.** They hold the worker protocol, so a worker brief shrinks to a task card under
  1.5 KB. A role file without the `sanduq-role:v1` marker is yours and is left alone. The model is
  set only when delegation is enabled; otherwise the role uses the session's model.
- **Hook-only Scope skills.** On Claude Code, `speckit-scope-guard`, `-bind`, `-after-specify`,
  `-plan-guard` and `-reconcile` get `user-invocable: false`, so they leave the `/` menu but stay
  callable by Scope's hooks.
- **Short aliases.** `speckit-scope` and `speckit-superpowers-bridge` are installed only with
  `install.py --with-aliases`. A project that already has them keeps them until you run
  `--without-aliases`. A registered upstream Superpowers Bridge is always replaced, because it is an
  executor that would bypass the workflow.

## Standing instructions: AGENTS.md

Keep the project's standing agent instructions in `AGENTS.md`; Codex reads it directly. Claude Code
reads `CLAUDE.md`, so make `CLAUDE.md` import the shared file instead of copying it:

```markdown
@AGENTS.md
```

Add Claude-only notes below the import. Workflow `doctor` warns `INSTRUCTION_FILES_DUPLICATED` when
both files exist and `CLAUDE.md` does not import `@AGENTS.md`.

## Limits

- opencode is deferred. Copilot is outside the supported hosts.
- Claude Desktop cannot run extensions.
- Delegate Task can start several agent CLIs as [harnesses](../reference/glossary.md#harness). A
  harness is not a supported host.
