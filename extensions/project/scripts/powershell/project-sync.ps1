#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Mirror a Spec Kit feature onto a GitHub Project (v2): keep a parent "feature" issue's
  Status column in step with the Spec Kit lifecycle, create one native sub-issue per task,
  and close sub-issues as their tasks are checked off.

.DESCRIPTION
  Idempotent and no-regress. Re-running any phase is safe; the card is never moved to an
  earlier status than it already has (unless -Force). Feature -> issue mappings are
  persisted in the configured state file (committed, so every assistant and checkout stays
  in sync). Board ids/columns come from .specify/extensions/project/config.json, written by
  `project-init.ps1`. If that config is missing, this script tells you to run init and exits 0.

  Requires the 'gh' CLI authenticated with the 'project' scope
  (gh auth refresh -h github.com -s project,read:project). If gh is missing, unauthenticated,
  lacks scope, or the remote is not GitHub, the script logs the skip and exits 0 (graceful
  degradation) so it never blocks a Spec Kit hook.

.PARAMETER Phase
  open | analysis | engineer-review | ready | in-progress | in-review | done | auto
  'auto' (default) infers the phase from which artifacts exist and the board status.

.PARAMETER Feature   Feature slug. Defaults to .specify/feature.json, else the current branch.
.PARAMETER DryRun    Print intended actions without mutating GitHub.
.PARAMETER NoSubIssues  On the 'ready' phase, do not create task sub-issues.
.PARAMETER Force     Allow moving the card to an earlier status (override no-regress).
.PARAMETER Json      Emit a machine-readable JSON summary as the last line.
#>
[CmdletBinding()]
param(
    [ValidateSet('open', 'analysis', 'engineer-review', 'ready', 'in-progress', 'in-review', 'done', 'auto')]
    [string]$Phase = 'auto',
    [string]$Feature,
    [switch]$DryRun,
    [switch]$NoSubIssues,
    [switch]$Force,
    [switch]$Json
)
$ErrorActionPreference = 'Stop'

function Write-Log { param([string]$Msg, [string]$Level = 'info')
    $prefix = switch ($Level) { 'warn' { '[project][warn]' } 'error' { '[project][error]' } default { '[project]' } }
    Write-Host "$prefix $Msg"
}
function Skip { param([string]$Reason)
    Write-Log "skipped: $Reason" 'warn'
    if ($Json) { [pscustomobject]@{ skipped = $true; reason = $Reason } | ConvertTo-Json -Compress }
    exit 0
}
function Get-RepoRoot {
    $r = (git rev-parse --show-toplevel 2>$null)
    if (-not $r) { throw 'Not inside a git repository.' }
    return $r.Trim()
}
function Invoke-Gh { param([string[]]$GhArgs, [switch]$AllowFail)
    if ($DryRun) { Write-Log "DRYRUN gh $($GhArgs -join ' ')"; return $null }
    $out = & gh @GhArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        if ($AllowFail) { return $null }
        throw "gh $($GhArgs -join ' ') failed: $out"
    }
    return ($out -join "`n")
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot
$configPath = Join-Path $repoRoot '.specify/extensions/project/config.json'
if (-not (Test-Path $configPath)) { Skip "not configured - run project-init.ps1 (or `/speckit-project-init`) first" }
$cfg = Get-Content $configPath -Raw | ConvertFrom-Json
if (-not $cfg.projectId -or -not $cfg.statusFieldId) { Skip "config.json is missing projectId/statusFieldId - re-run project-init.ps1" }

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Skip 'gh CLI not installed' }
$authStatus = & gh auth status 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Skip 'gh not authenticated' }
if ($authStatus -notmatch 'project') { Skip "gh token lacks 'project' scope - run: gh auth refresh -h github.com -s project,read:project" }
$remote = (git config --get remote.origin.url 2>$null)
if ($remote -notmatch 'github\.com') { Skip "remote is not GitHub ($remote)" }
if ($remote -match 'github\.com[:/]+([^/]+)/([^/.]+)') { $repoSlug = "$($matches[1])/$($matches[2])" } else { Skip "cannot parse repo from remote $remote" }

if (-not $Feature) {
    $featureJson = Join-Path $repoRoot '.specify/feature.json'
    if (Test-Path $featureJson) {
        $fj = Get-Content $featureJson -Raw | ConvertFrom-Json
        if ($fj.feature_directory) { $Feature = Split-Path $fj.feature_directory -Leaf }
    }
}
if (-not $Feature) { $Feature = (git rev-parse --abbrev-ref HEAD 2>$null).Trim() }
if (-not $Feature) { Skip 'could not resolve feature slug' }
$slug = $Feature
$branch = (git rev-parse --abbrev-ref HEAD 2>$null).Trim()
$featureDir = Join-Path $repoRoot "specs/$slug"
$specFile = Join-Path $featureDir 'spec.md'
$planFile = Join-Path $featureDir 'plan.md'
$tasksFile = Join-Path $featureDir 'tasks.md'

$title = $slug
if (Test-Path $specFile) {
    $h1 = Select-String -Path $specFile -Pattern '^\#\s+(.+?)\s*$' | Select-Object -First 1
    if ($h1) { $title = ($h1.Matches[0].Groups[1].Value -replace '^(Feature Specification|Spec):\s*', '').Trim() }
}

$statePath = Join-Path $repoRoot $cfg.stateFile
$state = @{}
if (Test-Path $statePath) {
    try { $state = Get-Content $statePath -Raw | ConvertFrom-Json -AsHashtable } catch { $state = @{} }
    if (-not $state) { $state = @{} }
}
if (-not $state.ContainsKey($slug)) { $state[$slug] = @{ issue = 0; issueNodeId = ''; itemId = ''; status = ''; subIssues = @{} } }
$fs = $state[$slug]
if ($fs -isnot [hashtable]) { $fs = @{ issue = 0; issueNodeId = ''; itemId = ''; status = ''; subIssues = @{} }; $state[$slug] = $fs }
if (-not $fs.ContainsKey('subIssues') -or $fs.subIssues -isnot [hashtable]) { $fs.subIssues = @{} }
function Save-State { if ($DryRun) { return }; ($state | ConvertTo-Json -Depth 10) | Set-Content -Path $statePath -Encoding utf8 }

$order = @($cfg.statusOrder)
function Status-Index { param([string]$s) $i = $order.IndexOf($s); if ($i -lt 0) { 0 } else { $i } }
function Set-CardStatus {
    param([string]$Status)
    if (-not $cfg.statusOptions.$Status) { Write-Log "status column '$Status' not on this board (phase unmapped); skipping" 'warn'; return }
    $current = $fs.status
    if ($current -and -not $Force -and (Status-Index $Status) -lt (Status-Index $current)) { Write-Log "no-regress: card is '$current'; not moving back to '$Status'"; return }
    if ($current -eq $Status) { Write-Log "status already '$Status'"; return }
    if (-not $fs.itemId) { Write-Log 'no project item id yet; cannot set status' 'warn'; return }
    Invoke-Gh @('project', 'item-edit', '--id', $fs.itemId, '--project-id', $cfg.projectId, '--field-id', $cfg.statusFieldId, '--single-select-option-id', $cfg.statusOptions.$Status) | Out-Null
    $fs.status = $Status
    Write-Log "status -> $Status"
}

function Ensure-ParentIssue {
    if ($fs.issue -and $fs.issue -gt 0) { return }
    $found = Invoke-Gh @('issue', 'list', '--repo', $repoSlug, '--state', 'all', '--label', ($cfg.parentIssue.labels -join ','), '--search', "in:title $slug", '--json', 'number,title,id', '--limit', '20') -AllowFail
    if ($found) {
        $match = ($found | ConvertFrom-Json) | Where-Object { $_.title -match [regex]::Escape($slug) } | Select-Object -First 1
        if ($match) { $fs.issue = $match.number; $fs.issueNodeId = $match.id; Write-Log "found existing parent issue #$($match.number)"; return }
    }
    if ($DryRun) { Write-Log "DRYRUN create parent issue for $slug"; $fs.issue = -1; return }
    $body = "Tracking issue for Spec Kit feature ``$slug``.`n`nSpec: ``specs/$slug/``  Branch: ``$branch``.`n`nManaged by the sanduq ``project`` extension (project-sync). Sub-issues below track individual tasks."
    $issueTitle = ($cfg.parentIssue.titleTemplate -replace '\{slug\}', $slug) -replace '\{title\}', $title
    $labelArgs = @(); foreach ($l in $cfg.parentIssue.labels) { $labelArgs += @('--label', $l) }
    foreach ($l in $cfg.parentIssue.labels) { Invoke-Gh @('label', 'create', $l, '--repo', $repoSlug, '--color', 'BFD4F2', '--force') -AllowFail | Out-Null }
    $url = Invoke-Gh (@('issue', 'create', '--repo', $repoSlug, '--title', $issueTitle, '--body', $body) + $labelArgs)
    if ($url -match '/issues/(\d+)') { $fs.issue = [int]$matches[1] }
    $node = Invoke-Gh @('issue', 'view', $fs.issue, '--repo', $repoSlug, '--json', 'id') -AllowFail
    if ($node) { $fs.issueNodeId = ($node | ConvertFrom-Json).id }
    Write-Log "created parent issue #$($fs.issue)"
}

function Ensure-InProject {
    if (-not $fs.issue -or $fs.issue -le 0) { return }
    if ($fs.itemId) { return }
    $issueUrl = "https://github.com/$repoSlug/issues/$($fs.issue)"
    $res = Invoke-Gh @('project', 'item-add', "$($cfg.projectNumber)", '--owner', $cfg.owner, '--url', $issueUrl, '--format', 'json') -AllowFail
    if ($res) { try { $fs.itemId = ($res | ConvertFrom-Json).id } catch {} }
    if (-not $fs.itemId) {
        $items = Invoke-Gh @('project', 'item-list', "$($cfg.projectNumber)", '--owner', $cfg.owner, '--format', 'json', '--limit', '200') -AllowFail
        if ($items) {
            $it = ($items | ConvertFrom-Json).items | Where-Object { $_.content.number -eq $fs.issue } | Select-Object -First 1
            if ($it) { $fs.itemId = $it.id }
        }
    }
    if ($fs.itemId) { Write-Log "issue #$($fs.issue) on Project #$($cfg.projectNumber)" }
}

function Get-Tasks {
    if (-not (Test-Path $tasksFile)) { return @() }
    $tasks = @()
    foreach ($line in Get-Content $tasksFile) {
        if ($line -match '^\s*-\s*\[([ xX])\]\s*\**(T\d+)\**\s*(.*)$') {
            $desc = ($matches[3] -replace '\*\*', '' -replace '\s*\[[Pp]\]\s*', ' ').Trim()
            if ($desc.Length -gt 90) { $desc = $desc.Substring(0, 90).TrimEnd() + '…' }
            $tasks += [pscustomobject]@{ id = $matches[2]; done = ($matches[1] -match '[xX]'); desc = $desc }
        }
    }
    return $tasks
}

function Sync-SubIssues {
    if (-not $cfg.subIssues.enabled -or $NoSubIssues) { return }
    if (-not $fs.issueNodeId) { Write-Log 'no parent node id; skipping sub-issues' 'warn'; return }
    $tasks = Get-Tasks
    if ($tasks.Count -eq 0) { Write-Log 'no tasks found in tasks.md' 'warn'; return }
    $toCreate = @($tasks | Where-Object { -not $fs.subIssues.ContainsKey($_.id) })
    if ($cfg.subIssues.warnAboveCount -gt 0 -and $toCreate.Count -gt $cfg.subIssues.warnAboveCount) {
        Write-Log "$($toCreate.Count) sub-issues to create for $slug (adds that many issues to $repoSlug)" 'warn'
    }
    $cap = [int]$cfg.subIssues.maxCount
    $created = 0
    foreach ($l in $cfg.subIssues.labels) { Invoke-Gh @('label', 'create', $l, '--repo', $repoSlug, '--color', 'D4C5F9', '--force') -AllowFail | Out-Null }
    foreach ($t in $toCreate) {
        if ($cap -gt 0 -and $created -ge $cap) { Write-Log "reached maxCount=$cap; $($toCreate.Count - $created) tasks left WITHOUT sub-issues" 'warn'; break }
        $stitle = (($cfg.subIssues.titleTemplate -replace '\{slug\}', $slug) -replace '\{taskId\}', $t.id) -replace '\{desc\}', $t.desc
        $labelArgs = @(); foreach ($l in $cfg.subIssues.labels) { $labelArgs += @('--label', $l) }
        if ($DryRun) { Write-Log "DRYRUN create sub-issue '$stitle' (parent #$($fs.issue))"; $created++; continue }
        $surl = Invoke-Gh (@('issue', 'create', '--repo', $repoSlug, '--title', $stitle, '--body', "Task ``$($t.id)`` of feature ``$slug`` (parent #$($fs.issue)).") + $labelArgs) -AllowFail
        if (-not $surl -or $surl -notmatch '/issues/(\d+)') { Write-Log "failed to create sub-issue for $($t.id)" 'warn'; continue }
        $snum = [int]$matches[1]
        $snode = (Invoke-Gh @('issue', 'view', $snum, '--repo', $repoSlug, '--json', 'id') -AllowFail | ConvertFrom-Json).id
        $q = 'mutation($p:ID!,$c:ID!){addSubIssue(input:{issueId:$p,subIssueId:$c}){subIssue{number}}}'
        Invoke-Gh @('api', 'graphql', '-H', 'GraphQL-Features: sub_issues', '-f', "query=$q", '-f', "p=$($fs.issueNodeId)", '-f', "c=$snode") -AllowFail | Out-Null
        $fs.subIssues[$t.id] = @{ number = $snum; nodeId = $snode; closed = $false }
        $created++
    }
    if ($created -gt 0) { Write-Log "created $created sub-issue(s)" }
}

function Sync-Progress {
    if ($fs.subIssues.Count -eq 0) { return $null }
    $doneIds = @((Get-Tasks) | Where-Object { $_.done } | ForEach-Object { $_.id })
    $closed = 0
    foreach ($id in @($fs.subIssues.Keys)) {
        $si = $fs.subIssues[$id]
        if ($doneIds -contains $id -and -not $si.closed) {
            Invoke-Gh @('issue', 'close', "$($si.number)", '--repo', $repoSlug, '--reason', 'completed') -AllowFail | Out-Null
            $si.closed = $true; $closed++
        }
    }
    if ($closed -gt 0) { Write-Log "closed $closed completed sub-issue(s)" }
    $total = $fs.subIssues.Count
    $done = @($fs.subIssues.Values | Where-Object { $_.closed }).Count
    if ($total -gt 0) { Write-Log "sub-issue progress: $done/$total" }
    return @{ total = $total; done = $done }
}

function Test-OpenPr {
    $pr = Invoke-Gh @('pr', 'list', '--repo', $repoSlug, '--head', $branch, '--state', 'open', '--json', 'number', '--limit', '1') -AllowFail
    if ($pr) { try { return (($pr | ConvertFrom-Json).Count -gt 0) } catch { return $false } }
    return $false
}

function Resolve-AutoStatus {
    $tasks = Get-Tasks
    if ($tasks.Count -gt 0) {
        $done = @($tasks | Where-Object { $_.done }).Count
        if ($done -eq 0) { return $cfg.phaseToStatus.'ready' }
        if ($done -lt $tasks.Count) { return $cfg.phaseToStatus.'in-progress' }
        return $cfg.phaseToStatus.'in-review'
    }
    if (Test-Path $planFile) { return $cfg.phaseToStatus.'analysis' }
    return $cfg.phaseToStatus.'open'
}

Write-Log "feature '$slug' -> repo $repoSlug, Project #$($cfg.projectNumber), phase '$Phase'"
Ensure-ParentIssue
Ensure-InProject

$targetStatus = if ($Phase -eq 'auto') { Resolve-AutoStatus } else { $cfg.phaseToStatus.$Phase }

if ($Phase -eq 'ready' -or ($Phase -eq 'auto' -and $targetStatus -eq $cfg.phaseToStatus.'ready')) { Sync-SubIssues }
$progress = $null
if ($Phase -in @('in-progress', 'in-review', 'done', 'auto')) { $progress = Sync-Progress }

# self-contained In review: if an open PR exists for the branch, advance to the in-review column
if ($Phase -in @('in-progress', 'auto', 'in-review')) {
    $irStatus = $cfg.phaseToStatus.'in-review'
    if ($irStatus -and (Status-Index $targetStatus) -lt (Status-Index $irStatus) -and (Test-OpenPr)) {
        Write-Log "open PR detected for '$branch' -> advancing to in-review"
        $targetStatus = $irStatus
    }
}
if ($Phase -eq 'done' -and $progress -and $progress.total -gt 0 -and $progress.done -eq $progress.total) { $targetStatus = $cfg.phaseToStatus.'done' }

Set-CardStatus -Status $targetStatus
Save-State

$summary = [pscustomobject]@{ feature = $slug; repo = $repoSlug; issue = $fs.issue; project = $cfg.projectNumber; status = $fs.status; phase = $Phase; subIssues = $fs.subIssues.Count; dryRun = [bool]$DryRun }
Write-Log "done: issue #$($fs.issue), status '$($fs.status)', $($fs.subIssues.Count) sub-issue(s)"
if ($Json) { $summary | ConvertTo-Json -Compress }
