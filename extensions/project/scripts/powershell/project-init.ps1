#!/usr/bin/env pwsh
# Deprecated stub, removed in the next release: Project init is scripts/project_init.py. Every argument
# (PowerShell or bash spelling) passes through unchanged; no param block, so $args holds them all.
Write-Host '[project-init][warn] project-init.ps1 is deprecated; run: python .specify/extensions/project/scripts/project_init.py [flags]'
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) { Write-Host '[project-init][error] python not found'; exit 1 }
& $py.Source (Join-Path $PSScriptRoot '../project_init.py') @args
exit $LASTEXITCODE
