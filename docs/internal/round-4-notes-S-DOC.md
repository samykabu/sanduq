# Round 4 notes: S-DOC

## X12 / D2 (C2): catalog priority and the community `scope` and `memory`

Verified at the Spec Kit pin `8147943` (read-only `git show`):

- `catalog add <url> --name --priority --install-allowed` (`extensions/catalog/command_add.py:17-30`, "lower = higher
  priority"; a second entry with the same name and other fields is refused, so the text removes first).
- `catalog remove <name>` and `catalog list` exist (`command_remove.py`, `command_list.py`).
- A project `.specify/extension-catalogs.yml` replaces the built-in stack; built-in default 1, community 2
  (`extensions/__init__.py:3848-3915`). Entries sort ascending (`catalogs.py:190`); the first catalog keeps an ID
  (`__init__.py:4126`).

Changes:

- `docs/start/install-speckit.md`: the command now uses `--priority 1`; the reversed sentence is replaced by the
  canonical subsection "If you keep Spec Kit's default catalogs" (the R6 §2 text, adapted to priority 1 as the
  default: re-register only if you used a higher number).
- `--priority 10` changed to `--priority 1` in `README.md`, `docs/start/install-by-host.md` (two places),
  `docs/workflow/delivery-policy.md`.
- Pointers to the subsection: `README.md` quick start, `docs/extensions/scope.md` (replaces the old two lines),
  `docs/extensions/memory.md` Setup, `docs/start/install-by-host.md` (all-nine block), `docs/start/upgrades.md`
  "One extension", `docs/start/troubleshooting.md` (new row), `docs/workflow/delivery-policy.md`,
  `extensions/README.md`.

## Docs drift

- C3: `docs/extensions/scope.md` Requires row now says Workflow 1.13.0 (manifest `>=1.13.0,<2.0.0`).
- `README.md` "Can I use this?": Progress was missing from the PolyForm row (manifest license PolyForm NC).
- `docs/extensions/project.md:4`: sub-issue per task now says "in standalone use" (R4 D1 table; true today).
- README counts: nine extensions, badge and tables match the nine manifests; `extensions/README.md` command counts
  match the manifests (3, 4, 7, 2, 5, 2, 7, 4, 13). Versions there are checked by `check_docs.py`; not touched.

Not done yet, waiting for other streams to land (my files, their facts):

- `docs/reference/hooks.md:17` "Memory's hooks ... stay as they are" -> "Memory's impact hook" once S-WF's D3 reconcile
  disables the two Memory hooks; then `check_docs.py --write`.
- `docs/extensions/progress.md:61` "existing prompts keep working" once S-WF's W16 removes the forwarder.
- The round-4 migration table: placeholder heading "Round 4 migration" added to `docs/start/upgrades.md`.

## Tests

- `check_docs.py`: fails only with "docs/reference/hooks.md is stale". I did not edit any manifest or hooks.md, so a
  manifest change by another stream causes it. I did not run `--write` mid-round; run it after the streams finish.

## Requests

- S-PM (`extensions/memory/README.md:15`), S-IL (`extensions/progress/README.md:28`), S-WF
  (`extensions/workflow/README.md:36`): change `--priority 10` to `--priority 1` and, if wanted, link
  `docs/start/install-speckit.md#if-you-keep-spec-kits-default-catalogs`.
- S-SC: if Scope's `requires` lower bounds change, `docs/extensions/scope.md:12` must follow (format "X.Y.Z or later").
- S-SH (X18 Requires rule): rows use "N.x" (Assure, PR, User Manual: Illustrate 2.x = `>=2.0.0`) and "X.Y.Z or later"
  (Scope); Memory and Progress rows name Python and Spec Kit, not extensions.
