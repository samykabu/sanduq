# Workflow compatibility and upgrade contract

The original installation baseline was Spec Kit `1.0.6.dev0` at commit
`f21acc4a25ce3aa53ff8653357b49b9aafcf8026`. The isolated native scheduling
prototype now validates on Spec Kit `1.0.11` at commit
`92b7cf7658a177cc417b7ddbeaa4c0a941a5f41b`; its mocked Claude/Codex
dispatch probes do not certify live agent execution or native production
scheduling. See [the result](native-workflow-prototype-results.md). SuperSpec `1.0.2` was checked at
`c20ac6c1ba069cc9a72dacb8044b7b193d3dde81`. These are tested snapshots, not
certification of every version allowed by a manifest range.

| Combination | Local evidence | CI coverage added |
| --- | --- | --- |
| Windows, Codex, SuperSpec | Clean install, four process choices, command composition, reinstall passed | Ubuntu clean installation |
| Windows, Claude, core | Same checks passed; internal command symlinks preserved | Ubuntu clean installation |
| Codex core / Claude SuperSpec | Not rerun in this batch | Separate Ubuntu installation jobs |
| Runtime and Scope | Windows Python regression suites | Windows and Ubuntu, separate jobs |
| PR 4.0.2 to staged 4.1.0 | Published old asset, native upgrade, injected failure and exact rollback checked | Separate Ubuntu upgrade job |
| Live feature and private PR | Pending explicit pilot issue | Requires actual GitHub and browser evidence |

CI definitions are not CI passes. Check the actual run before release.

Implementation commit `6e8223d1c0fc26644ca893d38b31aeae5894e197` passed all 13 jobs
in [run 35372199271](https://github.com/samykabu/sanduq/actions/runs/35372199271),
including all four host/provider installation combinations, Windows/Linux regressions,
upgrade rollback and both real Project Init scripts against a fake custom-column board.

The source boundary is deliberate: upstream commands stay upstream; Sanduq owns
the dispatcher and prepend presets; consumer policy and run state live outside
replaceable packages. This uses public installation/composition APIs and avoids
editing generated upstream command bodies. Sanduq's short Scope alias has an
explicit owner and only replaces a recognized previous alias.

One dispatcher owns stage transitions. Overlapping lifecycle hooks are reconciled
with a reversible journal. Project sync owns board updates; the task adapter owns
native task sub-issues. The core Tasks-to-Issues command remains the semantic entry.
An active legacy Bridge owner blocks a second executor.

The installer records `.specify/workflow/install-lock.json` with installed versions,
manifest hashes, source provenance, preset registration, host and tested baseline.
Local development installs remain labelled local; a constructed release URL is
not evidence that the asset exists. Runtime package digests detect source and
registration drift. A newer compatible dependency is retained, never downgraded
silently. Review stage contract changes before migrating active runs.

Policy and checkpoint schemas are versioned separately from package versions.
The JSON schemas under `extensions/workflow/schemas/` describe the v1 contracts;
runtime checks additionally enforce identity, filesystem containment, current
evidence, context conditions and stage ordering. A schema pass alone is not
semantic acceptance. Migration preserves historical command/digest provenance.

Dependency/preset installation has transactional backups and failure rollback.
`upgrade.py` wraps the workflow package itself and the new package's integration
installer in an outer transaction. Active claims and competing installs are blocked.
Its staged synthetic-version test is distinct from a published-version upgrade;
consult the current upgrade receipt before claiming coverage. Never silently apply
an unsupported state-schema downgrade.

Private PR acceptance requires real authenticated image loading. Inline Markdown
is necessary but insufficient: private raw-file URLs may fail. Use an authorized
attachment mechanism and verify each image. Never expose private assets publicly
to make a rendering check pass.
