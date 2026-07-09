#!/usr/bin/env pwsh
<#
.SYNOPSIS
  One-time setup for the 'project' extension: discover a GitHub Project (v2), map the Spec
  Kit lifecycle phases to that board's Status columns (hybrid: exact -> fuzzy -> prompt ->
  optional auto-create), and write .specify/extensions/project/config.json.

.PARAMETER Owner        Project owner login (user or org). Default: the authenticated user.
.PARAMETER Number       Project number. If 0/omitted, lists the owner's projects to choose from.
.PARAMETER OwnerType    'user' or 'org'. Auto-detected if omitted.
.PARAMETER AutoCreateColumns  Create any lifecycle column missing from the board without prompting.
.PARAMETER NonInteractive     Never prompt; map exact+fuzzy only, warn on unmatched (unless -AutoCreateColumns).
.PARAMETER DryRun       Show what would be written/created without mutating anything.
.PARAMETER Json         Emit a JSON summary as the last line.
#>
[CmdletBinding()]
param(
    [string]$Owner,
    [long]$Number = 0,
    [ValidateSet('user', 'org')][string]$OwnerType,
    [switch]$AutoCreateColumns,
    [switch]$NonInteractive,
    [switch]$DryRun,
    [switch]$Json
)
$ErrorActionPreference = 'Stop'
function Info { param($m) Write-Host "[project-init] $m" }
function Warn { param($m) Write-Host "[project-init][warn] $m" }
function Die  { param($m) Write-Host "[project-init][error] $m"; exit 1 }

# ---- repo + config paths ----
$repoRoot = (git rev-parse --show-toplevel 2>$null); if (-not $repoRoot) { Die 'not inside a git repository' }
$repoRoot = $repoRoot.Trim(); Set-Location $repoRoot
$extDir = Join-Path $repoRoot '.specify/extensions/project'
$defaultCfgPath = Join-Path $PSScriptRoot '../../config.default.json' | Resolve-Path -ErrorAction SilentlyContinue
if (-not $defaultCfgPath) { $defaultCfgPath = Join-Path $extDir 'config.default.json' }
if (-not (Test-Path $defaultCfgPath)) { Die "config.default.json not found (looked near the script and in $extDir)" }
$def = Get-Content $defaultCfgPath -Raw | ConvertFrom-Json

# ---- gh preconditions ----
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Die 'gh CLI not installed' }
$auth = & gh auth status 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Die 'gh not authenticated - run: gh auth login' }
if ($auth -notmatch 'project') { Die "gh token lacks 'project' scope - run: gh auth refresh -h github.com -s project,read:project" }

# ---- resolve owner ----
if (-not $Owner) { $Owner = (gh api user --jq .login 2>$null); if (-not $Owner) { Die 'could not resolve owner - pass -Owner' } }
$Owner = $Owner.Trim()
if (-not $OwnerType) {
    # user projects list succeeds for a user login; fall back to org
    $probe = & gh project list --owner $Owner --limit 1 --format json 2>&1
    $OwnerType = if ($LASTEXITCODE -eq 0) { 'user' } else { 'org' }
}
Info "owner: $Owner ($OwnerType)"

# ---- resolve project number ----
if ($Number -le 0) {
    $listJson = & gh project list --owner $Owner --format json 2>&1
    if ($LASTEXITCODE -ne 0) { Die "could not list projects for $Owner : $listJson" }
    $projects = ($listJson | ConvertFrom-Json).projects
    if (-not $projects -or $projects.Count -eq 0) { Die "no projects found for $Owner - create one or pass -Number" }
    if ($NonInteractive -and $projects.Count -gt 1) { Die 'multiple projects found; pass -Number in non-interactive mode' }
    if ($projects.Count -eq 1) { $Number = $projects[0].number }
    else {
        Info 'Select a project:'
        for ($i = 0; $i -lt $projects.Count; $i++) { Write-Host ("  [{0}] #{1}  {2}" -f $i, $projects[$i].number, $projects[$i].title) }
        $pick = Read-Host 'index'
        $Number = $projects[[int]$pick].number
    }
}
Info "project #$Number"

# ---- discover project id + Status field + options ----
$pv = & gh project view $Number --owner $Owner --format json 2>&1
if ($LASTEXITCODE -ne 0) { Die "cannot view project #$Number : $pv" }
$projView = $pv | ConvertFrom-Json
$projectId = $projView.id
$projectUrl = $projView.url

$fieldsJson = & gh project field-list $Number --owner $Owner --format json 2>&1
if ($LASTEXITCODE -ne 0) { Die "cannot list fields: $fieldsJson" }
$statusField = ($fieldsJson | ConvertFrom-Json).fields | Where-Object { $_.name -eq 'Status' -and $_.options } | Select-Object -First 1
if (-not $statusField) { Die "no single-select 'Status' field on project #$Number" }
$statusFieldId = $statusField.id
$boardOptions = @{}   # name -> id
foreach ($o in $statusField.options) { $boardOptions[$o.name] = $o.id }
Info ("board Status columns: " + (($boardOptions.Keys) -join ', '))

# ---- hybrid mapping: phase -> board column ----
function Normalize { param($s) ($s -replace '[^a-z0-9]', '').ToLower() }
$phases = @('open', 'analysis', 'engineer-review', 'ready', 'in-progress', 'in-review', 'done')
$palette = @('GRAY', 'BLUE', 'PURPLE', 'GREEN', 'YELLOW', 'ORANGE', 'PINK')
$phaseToStatus = [ordered]@{}
$statusOptions = [ordered]@{}
$toCreate = @()   # @{ phase; name; color }

foreach ($i in 0..($phases.Count - 1)) {
    $phase = $phases[$i]
    $wanted = $def.phaseToStatus.$phase
    $match = $null
    # exact (case-insensitive)
    $match = ($boardOptions.Keys | Where-Object { $_ -ieq $wanted } | Select-Object -First 1)
    if (-not $match) {
        # fuzzy: normalized equality or contains
        $nw = Normalize $wanted
        $match = ($boardOptions.Keys | Where-Object { (Normalize $_) -eq $nw -or (Normalize $_).Contains($nw) -or $nw.Contains((Normalize $_)) } | Select-Object -First 1)
    }
    if ($match) {
        $phaseToStatus[$phase] = $match
        $statusOptions[$match] = $boardOptions[$match]
        Info ("  {0,-16} -> {1}" -f $phase, $match)
    }
    else {
        $create = $AutoCreateColumns
        if (-not $create -and -not $NonInteractive) {
            $ans = Read-Host ("  no column matches phase '$phase' (wanted '$wanted'). Create column '$wanted'? [y/N]")
            $create = ($ans -match '^[yY]')
        }
        if ($create) { $toCreate += @{ phase = $phase; name = $wanted; color = $palette[$i % $palette.Count] } }
        else { Warn "phase '$phase' has no column - the '$phase' transition will be a no-op until you map it" }
    }
}

# ---- create missing columns via GraphQL (replaces the full option set) ----
if ($toCreate.Count -gt 0) {
    if ($DryRun) {
        foreach ($c in $toCreate) { Info "DRYRUN create column '$($c.name)' ($($c.color))" }
    }
    else {
        # build full option set = existing (preserve) + new
        $opts = @()
        foreach ($o in $statusField.options) { $opts += "{name:$(ConvertTo-Json $o.name),color:$(if($o.color){$o.color.ToUpper()}else{'GRAY'}),description:`"`"}" }
        foreach ($c in $toCreate) { $opts += "{name:$(ConvertTo-Json $c.name),color:$($c.color),description:`"`"}" }
        $optsStr = $opts -join ','
        $q = "mutation{updateProjectV2Field(input:{fieldId:`"$statusFieldId`",singleSelectOptions:[$optsStr]}){projectV2Field{... on ProjectV2SingleSelectField{options{id name}}}}}"
        $res = & gh api graphql -f query="$q" 2>&1
        if ($LASTEXITCODE -ne 0) { Warn "column creation failed: $res"; }
        else {
            $newOpts = ($res | ConvertFrom-Json).data.updateProjectV2Field.projectV2Field.options
            foreach ($no in $newOpts) { $boardOptions[$no.name] = $no.id }
            foreach ($c in $toCreate) {
                if ($boardOptions.ContainsKey($c.name)) {
                    $phaseToStatus[$c.phase] = $c.name
                    $statusOptions[$c.name] = $boardOptions[$c.name]
                    Info ("  created & mapped {0,-16} -> {1}" -f $c.phase, $c.name)
                }
            }
        }
    }
}

# statusOrder = the mapped column names in phase order (kept for no-regress ordering)
$statusOrder = @(); foreach ($p in $phases) { if ($phaseToStatus.$p -and ($statusOrder -notcontains $phaseToStatus.$p)) { $statusOrder += $phaseToStatus.$p } }

# ---- assemble + write config.json ----
$config = [ordered]@{
    owner         = $Owner
    ownerType     = $OwnerType
    projectNumber = [int]$Number
    projectId     = $projectId
    projectUrl    = $projectUrl
    statusFieldId = $statusFieldId
    statusOptions = $statusOptions
    phaseToStatus = $phaseToStatus
    statusOrder   = $statusOrder
    parentIssue   = $def.parentIssue
    subIssues     = $def.subIssues
    stateFile     = $def.stateFile
}
$outPath = Join-Path $extDir 'config.json'
if ($DryRun) {
    Info "DRYRUN would write $outPath :"
    $config | ConvertTo-Json -Depth 10 | Write-Host
}
else {
    New-Item -ItemType Directory -Path $extDir -Force | Out-Null
    ($config | ConvertTo-Json -Depth 10) | Set-Content -Path $outPath -Encoding utf8
    Info "wrote $outPath"
}

Info 'done. Next: commit config.json, then run a dry-run sync:'
Info '  pwsh .specify/extensions/project/scripts/powershell/project-sync.ps1 -Phase open -DryRun'
if ($Json) { $config | ConvertTo-Json -Depth 10 -Compress }
