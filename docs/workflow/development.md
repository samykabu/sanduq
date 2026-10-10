# Workflow packaging and development

This page covers building the Workflow archive from a Sanduq checkout, installing a staged package for testing, and the tested Spec Kit baseline. You need it only when you change the extension itself or test an unpublished version.

Back to the [Workflow guide](../../extensions/workflow/README.md).

## Packaging and development

Build archives with `python extensions/scripts/package.py workflow` from Sanduq.
The archive bundles canonical presets from `presets/`, so consumer command edits
are unnecessary. Install a staged extracted package using
`specify extension add --dev <extracted/workflow>`; install its bundled presets
through `specify preset add --dev <preset-path> --priority 1` (workflow) and priority
2 (scope-gate/scope-brainstorm). The isolated native prototype was checked on
Spec Kit 1.0.11, commit 92b7cf7658a177cc417b7ddbeaa4c0a941a5f41b;
its command completion is insufficient for production receipt semantics.
Other versions require compatibility testing.

For a managed project run `workflow.py init --qa on|off --manual on|off --delegate
on|off`, configure
GitHub Project status mappings, run `install.py` preview/apply and run doctor. Only explicit
selections enable processes. The dependency lock records exact intended versions;
unpublished versions require a staged package until the catalog is promoted.

Scope's community catalog name is ambiguous. Always use the Sanduq archive URL or
verified staged package, never a bare `specify extension add scope` command.

The build script is [`extensions/scripts/package.py`](../../extensions/scripts/package.py). Exact intended dependency versions are in [`extensions/workflow/dependencies.json`](../../extensions/workflow/dependencies.json).
