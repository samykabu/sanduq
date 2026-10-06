# Portable skill source index

Seven portable skills work without Spec Kit. Use [Getting started](../docs/getting-started.md)
for installation and host namespaces, and [the skill guide](../docs/skills.md) for when to use each,
consistent refund examples, expected outputs, and prerequisites.

| Skill | Source |
| --- | --- |
| Illustrate | [illustrate](illustration-tools/skills/illustrate/SKILL.md) |
| User Manual | [user-manual](dev-tools/skills/user-manual/SKILL.md) |
| API documentation | [user-manual-api-docs](dev-tools/skills/user-manual-api-docs/SKILL.md) |
| Release documentation | [user-manual-release-docs](dev-tools/skills/user-manual-release-docs/SKILL.md) |
| UI screenshots | [user-manual-ui-screenshots](dev-tools/skills/user-manual-ui-screenshots/SKILL.md) |
| Preview publishing | [user-manual-preview-publishing](dev-tools/skills/user-manual-preview-publishing/SKILL.md) |
| Delegate Task | [delegate-task](agent-tools/skills/delegate-task/SKILL.md) |

## Claude Code bundles

| Bundle | Version | Skills |
| --- | --- | --- |
| [illustration-tools](illustration-tools/README.md) | 3.1.0 | Illustrate |
| [dev-tools](dev-tools/README.md) | 1.0.0 | Five manual skills |
| [agent-tools](agent-tools/README.md) | 1.1.1 | Delegate Task |

The [marketplace](../.claude-plugin/marketplace.json) and each plugin manifest own bundle versions.
Extension versions are independent. Contribute through the [owning source](../CONTRIBUTING.md#find-the-owning-source),
not an installed copy. Internal extension skills are listed [separately](../docs/extensions.md#internal-skills-and-overlays).
