#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Manual (non-catalog) installer: copy a sanduq extension into a target Spec Kit repo.
.DESCRIPTION
  Full hook-wiring + rendering of the command into every assistant target is done by the
  Spec Kit CLI (`speckit extension install <id>`). This script is the fallback: it stages
  the extension files and prints the exact next steps.
.EXAMPLE
  # from the TARGET repo root:
  pwsh C:\path\to\sanduq\install.ps1 -Extension project
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Extension,
    [string]$Target = '.'
)
$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot "extensions/$Extension"
if (-not (Test-Path $src)) { throw "no such extension: $Extension (looked in $src)" }
if (-not (Test-Path (Join-Path $Target '.specify'))) { throw "target '$Target' is not a Spec Kit repo (.specify/ missing)" }

$dest = Join-Path $Target ".specify/extensions/$Extension"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
Copy-Item -Path (Join-Path $src '*') -Destination $dest -Recurse -Force
Write-Host "[sanduq] copied extension '$Extension' -> $dest"

Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Finalise install (wire hooks + render the command into your assistant targets):'
Write-Host "       speckit extension install $Extension      # if you use the Spec Kit CLI"
Write-Host '     ...or add sanduq to .specify/extension-catalogs.yml and install from the catalog.'
Write-Host '  2. One-time board setup:'
Write-Host '       gh auth refresh -h github.com -s project,read:project'
Write-Host "       pwsh $dest/scripts/powershell/project-init.ps1"
Write-Host "  3. Commit .specify/extensions/$Extension and its config.json."
Write-Host ''
Write-Host "Declared hooks to merge into .specify/extensions.yml (see $dest/extension.yml 'hooks:')."
