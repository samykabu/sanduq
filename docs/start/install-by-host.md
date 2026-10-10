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

**Extensions.** Initialize Spec Kit for Codex and register the catalog:

```bash
specify init --here --integration codex
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

Then add extensions. To add all eight, use the [dependency-ordered block](#all-eight-extensions).

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
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

Then add extensions. To add all eight, use the [dependency-ordered block](#all-eight-extensions).

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

## All eight extensions

Run these after registering the catalog. The order installs each dependency before the extension
that needs it.

```bash
specify extension add illustrate
specify extension add assure
specify extension add user-manual
specify extension add pr
specify extension add project
specify extension add workflow
specify extension add scope    # requires workflow; another catalog uses the same ID
specify extension add memory
```

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

## Limits

- opencode is deferred. Copilot is outside the supported hosts.
- Claude Desktop cannot run extensions.
- Delegate Task can start several agent CLIs as [harnesses](../reference/glossary.md#harness). A
  harness is not a supported host.
