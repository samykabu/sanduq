# Optional GitHub Brainstorm preset

The Workflow installer always applies this preset, and Workflow's doctor requires it. It replaces
`speckit.superspec.brainstorm` (`strategy: replace`) with a short pointer to the shared GitHub
clarification skill, which holds Brainstorm's coverage categories and answer rules. Spec Kit
scaffolds the command even without Superspec; automatic dispatch still picks Brainstorm only when
Superspec is installed and enabled, and uses Clarify otherwise.
