#!/usr/bin/env pwsh
<#
.SYNOPSIS
  One-time setup for the 'project' extension: discover a GitHub Project (v2), map the Spec
  Kit lifecycle phases to that board's Status columns (hybrid: exact -> fuzzy -> prompt ->
  optional auto-create), and write .specify/extensions/project/config.json. A rerun keeps the
  existing parentIssue, subIssues and stateFile settings.

.PARAMETER Owner        Project owner login (user or org). Default: the authenticated user.
.PARAMETER Number       Project number. If 0/omitted, lists the owner's projects to choose from.
.PARAMETER OwnerType    'user' or 'org'. Auto-detected if omitted.
.PARAMETER HooksMode    'optional' offers sync as a manual hook; 'required' marks it automatic.
.PARAMETER AutoCreateColumns  Create any lifecycle column missing from the board without prompting.
.PARAMETER NonInteractive     Never prompt; map exact+fuzzy only, warn on unmatched (unless -AutoCreateColumns).
.PARAMETER AllowStatusReset   Change columns even when the board's item statuses cannot be read; they are then cleared.
.PARAMETER DryRun       Show what would be written/created without mutating anything.
.PARAMETER Json         Emit a JSON summary as the last line.
#>
[CmdletBinding()]
param(
    [string]$Owner,
    [long]$Number = 0,
    [ValidateSet('user', 'org')][string]$OwnerType,
    [ValidateSet('optional', 'required')][string]$HooksMode,
    [switch]$AutoCreateColumns,
    [switch]$NonInteractive,
    [switch]$AllowStatusReset,
    [switch]$DryRun,
    [switch]$Json
)
$ErrorActionPreference = 'Stop'
function Info { param($m) Write-Host "[project-init] $m" }
function Warn { param($m) Write-Host "[project-init][warn] $m" }
function Die  { param($m) Write-Host "[project-init][error] $m"; exit 1 }

function Set-ProjectHookMode {
    param([string]$Mode)
    $extensionsPath = Join-Path $repoRoot '.specify/extensions.yml'
    if (-not (Test-Path $extensionsPath)) {
        Die '.specify/extensions.yml not found - install the extension with `specify extension add project` before running init'
    }

    $optionalValue = if ($Mode -eq 'optional') { 'true' } else { 'false' }
    $lines = @(Get-Content -Path $extensionsPath)
    $inProjectHook = $false
    $updated = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*-\s+extension:\s+project\s*$') {
            $inProjectHook = $true
            continue
        }
        if ($lines[$i] -match '^\s*-\s+extension:\s+') {
            $inProjectHook = $false
        }
        if ($inProjectHook -and $lines[$i] -match '^(\s*optional:\s*)(?:true|false)\s*$') {
            $lines[$i] = "$($matches[1])$optionalValue"
            $updated++
            $inProjectHook = $false
        }
    }
    if ($updated -eq 0) {
        Die 'no project sync hooks found in .specify/extensions.yml - reinstall the project extension and retry'
    }
    if ($DryRun) {
        Info "DRYRUN would set $updated project sync hook(s) to $Mode"
    }
    else {
        $lines | Set-Content -Path $extensionsPath -Encoding utf8
        Info "set $updated project sync hook(s) to $Mode"
    }
}

# ---- repo + config paths ----
$repoRoot = (git rev-parse --show-toplevel 2>$null); if (-not $repoRoot) { Die 'not inside a git repository' }
$repoRoot = $repoRoot.Trim(); Set-Location $repoRoot
$extDir = Join-Path $repoRoot '.specify/extensions/project'
$defaultCfgPath = Join-Path $PSScriptRoot '../../config.default.json' | Resolve-Path -ErrorAction SilentlyContinue
if (-not $defaultCfgPath) { $defaultCfgPath = Join-Path $extDir 'config.default.json' }
if (-not (Test-Path $defaultCfgPath)) { Die "config.default.json not found (looked near the script and in $extDir)" }
$def = Get-Content $defaultCfgPath -Raw | ConvertFrom-Json
# A rerun keeps the existing sub-issue, parent and state settings; defaults apply on the first run only.
$existingCfgPath = Join-Path $extDir 'config.json'
$existing = $null
if (Test-Path $existingCfgPath) {
    try { $existing = Get-Content $existingCfgPath -Raw | ConvertFrom-Json } catch { Die "$existingCfgPath is not valid JSON - fix or delete it, then rerun" }
}
function Keep { param($Key) if ($existing -and $existing.PSObject.Properties.Name -contains $Key) { $existing.$Key } else { $def.$Key } }
$managedWorkflow = Test-Path (Join-Path $repoRoot '.specify/workflow.yml')
$required = @()   # managed: the exact column names Workflow's doctor requires
if ($managedWorkflow) {
    $managedJson = & python (Join-Path $repoRoot '.specify/extensions/workflow/scripts/workflow.py') project-defaults
    if ($LASTEXITCODE -ne 0) { Die 'cannot read managed workflow phase defaults; run workflow doctor' }
    $managed = $managedJson | ConvertFrom-Json
    $def.phaseToStatus = $managed.phaseToStatus
    if ($managed.statuses) { $required = @($managed.statuses) }
}

# ---- gh preconditions ----
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Die 'gh CLI not installed' }
$auth = & gh auth status 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Die 'gh not authenticated - run: gh auth login' }
# 'project' as a whole scope: 'read:project' alone cannot write the board
if ($auth -notmatch '(^|[^:\w-])project([^:\w-]|$)') { Die "gh token lacks 'project' scope - run: gh auth refresh -h github.com -s project,read:project" }

# ---- resolve owner ----
if (-not $Owner) { $Owner = (gh api user --jq .login 2>$null); if (-not $Owner) { Die 'could not resolve owner - pass -Owner' } }
$Owner = $Owner.Trim()
if (-not $OwnerType) {
    # 'gh project list' accepts org logins too, so only the account type tells the two apart
    $kind = & gh api "users/$Owner" --jq .type 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $kind) { Die "cannot tell whether $Owner is a user or an organization - pass -OwnerType user|org" }
    $OwnerType = if ("$kind".Trim() -eq 'Organization') { 'org' } else { 'user' }
}
Info "owner: $Owner ($OwnerType)"

# ---- resolve project number ----
if ($Number -le 0) {
    $listJson = & gh project list --owner $Owner --format json 2>&1
    if ($LASTEXITCODE -ne 0) { Die "could not list projects for $Owner : $listJson" }
    $projects = ($listJson | ConvertFrom-Json).projects
    if (-not $projects -or $projects.Count -eq 0) { Die "no projects found for $Owner - create one or pass -Number" }
    if ($NonInteractive -and $projects.Count -gt 1) {
        Die ("multiple projects for $Owner" + ': ' + (($projects | ForEach-Object { '#{0} {1}' -f $_.number, $_.title }) -join ', ') + ' - ask which one and rerun with -Number <n>')
    }
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
foreach ($name in $boardOptions.Keys) { $statusOptions[$name] = $boardOptions[$name] }
$toCreate = [System.Collections.Generic.List[hashtable]]::new()   # @{ name; color; from; phases }, one per name

function Map-Column {
    param($Phase, $Wanted, $Color)
    $label = if ($Phase) { "phase '$Phase'" } else { "status '$Wanted'" }
    # managed: doctor and Scope compare exact names, so only an exact (case-sensitive) column matches
    $match = ($boardOptions.Keys | Where-Object { $_ -ceq $Wanted } | Select-Object -First 1)
    if (-not $match -and -not $managedWorkflow) {
        $match = ($boardOptions.Keys | Where-Object { $_ -ieq $Wanted } | Select-Object -First 1)
        if (-not $match) {
            # fuzzy: normalized equality or contains
            $nw = Normalize $Wanted
            $match = ($boardOptions.Keys | Where-Object { (Normalize $_) -eq $nw -or (Normalize $_).Contains($nw) -or $nw.Contains((Normalize $_)) } | Select-Object -First 1)
        }
    }
    if ($match) {
        if ($Phase) { $phaseToStatus[$Phase] = $match }
        Info ("  {0,-16} -> {1}" -f $(if ($Phase) { $Phase } else { 'status' }), $match)
        return
    }
    $pending = $toCreate | Where-Object { $_.name -ceq $Wanted } | Select-Object -First 1
    if ($pending) { if ($Phase) { $pending.phases.Add($Phase) }; return }   # one column per name
    # managed: a column that differs only in case or spacing is renamed rather than duplicated
    $variant = if ($managedWorkflow) { $boardOptions.Keys | Where-Object { (Normalize $_) -eq (Normalize $Wanted) } | Select-Object -First 1 }
    $verb = if ($variant) { "Rename column '$variant' to '$Wanted'" } else { "Create column '$Wanted'" }
    $create = $AutoCreateColumns
    if (-not $create -and -not $NonInteractive) {
        $ans = Read-Host ("  no column matches $label (wanted '$Wanted'). $verb? [y/N]")
        $create = ($ans -match '^[yY]')
    }
    if ($create) {
        $entry = @{ name = $Wanted; color = $Color; from = $variant; phases = [System.Collections.Generic.List[string]]::new() }
        if ($Phase) { $entry.phases.Add($Phase) }
        $toCreate.Add($entry)
    }
    else { Warn "$label has no column (wanted '$Wanted') - the transition is a no-op until mapped; rerun with -AutoCreateColumns to create it, or add the column on the board and rerun" }
}

foreach ($i in 0..($phases.Count - 1)) { Map-Column $phases[$i] $def.phaseToStatus.($phases[$i]) $palette[$i % $palette.Count] }
foreach ($name in $required) { Map-Column $null $name 'GRAY' }

# ---- create missing columns via GraphQL (replaces the full option set) ----
if ($toCreate.Count -gt 0) {
    if ($DryRun) {
        foreach ($c in $toCreate) { Info $(if ($c.from) { "DRYRUN rename column '$($c.from)' to '$($c.name)'" } else { "DRYRUN create column '$($c.name)' ($($c.color))" }) }
    }
    else {
        # build full option set = existing (preserve, renamed where asked) + new
        $opts = @()
        foreach ($o in $statusField.options) {
            $renamed = $toCreate | Where-Object { $_.from -ceq $o.name } | Select-Object -First 1
            $name = if ($renamed) { $renamed.name } else { $o.name }
            $opts += "{name:$(ConvertTo-Json $name),color:$(if($o.color){$o.color.ToUpper()}else{'GRAY'}),description:`"`"}"
        }
        foreach ($c in $toCreate) { if (-not $c.from) { $opts += "{name:$(ConvertTo-Json $c.name),color:$($c.color),description:`"`"}" } }
        $optsStr = $opts -join ','
        # The update replaces every option id, which clears every item's Status: save each by name first.
        # GraphQL, not `gh project item-list`, which leaves archived items out.
        $saved = @(); $cursor = $null; $readError = $null
        do {
            $after = if ($cursor) { ",after:`"$cursor`"" } else { '' }
            $iq = "query{node(id:`"$projectId`"){... on ProjectV2{items(first:100$after,archivedStates:[ARCHIVED,NOT_ARCHIVED]){pageInfo{hasNextPage endCursor} nodes{id isArchived fieldValueByName(name:`"Status`"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}"
            $page = & gh api graphql -f query="$iq" 2>&1
            $items = if ($LASTEXITCODE -eq 0) { ($page | ConvertFrom-Json).data.node.items } else { $null }
            if (-not $items) { $readError = "$page"; break }
            foreach ($n in $items.nodes) {
                if ($n.fieldValueByName.name) { $saved += @{ id = $n.id; status = $n.fieldValueByName.name; archived = [bool]$n.isArchived } }
            }
            $cursor = if ($items.pageInfo.hasNextPage) { $items.pageInfo.endCursor } else { $null }
        } while ($cursor)
        if ($readError -and $AllowStatusReset) { $saved = @(); Warn "cannot read the board's items ($readError); -AllowStatusReset: their Status will be cleared" }
        elseif ($readError) { Die "cannot read the board's items, so their Status could not be restored after the column change: $readError - fix access and rerun, or pass -AllowStatusReset to accept that every item loses its Status" }
        $q = "mutation{updateProjectV2Field(input:{fieldId:`"$statusFieldId`",singleSelectOptions:[$optsStr]}){projectV2Field{... on ProjectV2SingleSelectField{options{id name}}}}}"
        $res = & gh api graphql -f query="$q" 2>&1
        if ($LASTEXITCODE -ne 0) { Warn "column creation failed: $res"; }
        else {
            # The update replaces every option, so every option id is new: rebuild the whole map.
            $newOpts = ($res | ConvertFrom-Json).data.updateProjectV2Field.projectV2Field.options
            $statusOptions = [ordered]@{}
            foreach ($no in $newOpts) { $statusOptions[$no.name] = $no.id }
            $restoreFailed = @()
            foreach ($item in $saved) {
                $renamed = $toCreate | Where-Object { $_.from -ceq $item.status } | Select-Object -First 1
                $name = if ($renamed) { $renamed.name } else { $item.status }
                $optionId = ($newOpts | Where-Object { $_.name -ceq $name } | Select-Object -First 1).id
                if (-not $optionId) { $restoreFailed += "$($item.id) was '$($item.status)': no such column after the update"; continue }
                # GitHub refuses to update an archived item: unarchive it, set the Status, archive it again.
                $pair = "projectId:`"$projectId`",itemId:`"$($item.id)`""
                if ($item.archived) {
                    $out = & gh api graphql -f query="mutation{unarchiveProjectV2Item(input:{$pair}){item{id}}}" 2>&1
                    if ($LASTEXITCODE -ne 0) { $restoreFailed += "$($item.id) (archived) was '$($item.status)': $out"; continue }
                }
                $out = & gh project item-edit --id $item.id --project-id $projectId --field-id $statusFieldId --single-select-option-id $optionId 2>&1
                $ok = $LASTEXITCODE -eq 0
                if ($item.archived) {
                    $again = & gh api graphql -f query="mutation{archiveProjectV2Item(input:{$pair}){item{id}}}" 2>&1
                    if ($LASTEXITCODE -ne 0) { $ok = $false; $out = "$out; left unarchived: $again" }
                }
                if (-not $ok) { $restoreFailed += "$($item.id)$(if ($item.archived) { ' (archived)' }) was '$($item.status)': $out" }
            }
            Info "restored Status on $($saved.Count - $restoreFailed.Count) of $($saved.Count) item(s)"
            foreach ($f in $restoreFailed) { Warn "item Status not restored, set it by hand: $f" }
            foreach ($c in $toCreate) {
                if ($statusOptions.Contains($c.name)) {
                    foreach ($p in $c.phases) { $phaseToStatus[$p] = $c.name }
                    Info ("  created & mapped {0,-16} -> {1}" -f (($c.phases -join ',') + ''), $c.name)
                }
            }
        }
    }
}

# ---- choose whether lifecycle hooks are manual or automatic ----
if ($managedWorkflow) { $HooksMode = 'required' }
if (-not $HooksMode) {
    if ($NonInteractive) {
        if ($existing) { $HooksMode = $existing.hookMode }
        if ($HooksMode -notin @('optional', 'required')) { $HooksMode = 'optional' }
        Info "hook mode not supplied in non-interactive mode; using $HooksMode (rerun with -HooksMode optional|required to choose)"
    }
    else {
        do {
            $choice = Read-Host "Project sync hooks: 'required' runs sync automatically; 'optional' offers manual execution [optional]"
            if (-not $choice) { $choice = 'optional' }
            $choice = $choice.Trim().ToLowerInvariant()
            if ($choice -notin @('optional', 'required')) { Warn "enter 'optional' or 'required'" }
        } while ($choice -notin @('optional', 'required'))
        $HooksMode = $choice
    }
}
if ($managedWorkflow) {
    Info 'Sanduq workflow owns lifecycle dispatch; preserving reconciled hook entries'
} else {
    Set-ProjectHookMode -Mode $HooksMode
}

# statusOrder = the mapped column names in phase order (kept for no-regress ordering)
$statusOrder = @(); foreach ($p in $phases) { if ($phaseToStatus.$p -and ($statusOrder -notcontains $phaseToStatus.$p)) { $statusOrder += $phaseToStatus.$p } }

# ---- assemble + write config.json ----
$config = [ordered]@{
    owner         = $Owner
    ownerType     = $OwnerType
    hookMode      = $HooksMode
    projectNumber = [int]$Number
    projectId     = $projectId
    projectUrl    = $projectUrl
    statusFieldId = $statusFieldId
    statusOptions = $statusOptions
    phaseToStatus = $phaseToStatus
    statusOrder   = $statusOrder
    parentIssue   = Keep 'parentIssue'
    subIssues     = Keep 'subIssues'
    stateFile     = Keep 'stateFile'
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
Info '  python .specify/extensions/project/scripts/project_sync.py --phase open --dry-run'
if ($Json) { $config | ConvertTo-Json -Depth 10 -Compress }
if ($restoreFailed) { exit 1 }
