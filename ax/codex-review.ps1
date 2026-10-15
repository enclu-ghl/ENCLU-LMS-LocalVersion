# Codex "review" step: reviews the current changes and writes reports/<TaskId>/review.md (read-only sandbox).
# Usage: powershell -File ax\codex-review.ps1 AX-20261014-01 [-Base main] [-DiffRepo <path>]
#   -DiffRepo: review a different (e.g. nested) git repo's changes; reports still go to this repo.
#   Reviews: committed changes since <Base> + uncommitted changes + untracked file names.
# (Keep this file ASCII-only: Windows PowerShell 5.1 misreads BOM-less UTF-8 scripts.)
param(
    [Parameter(Mandatory = $true)][string]$TaskId,
    [string]$Base = 'main',
    [string]$DiffRepo
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $repo "reports\$TaskId"
New-Item -ItemType Directory -Force $outDir | Out-Null
$gitRepo = if ($DiffRepo) { (Resolve-Path $DiffRepo).Path } else { $repo }

# git emits UTF-8; the Korean-Windows console default (cp949) would garble it on capture.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Invoke-Git([string[]]$GitArgs) {
    $out = git -C $gitRepo @GitArgs
    if ($LASTEXITCODE -ne 0) { Write-Error "git $($GitArgs -join ' ') failed (exit $LASTEXITCODE)"; exit 1 }
    $out -join "`n"
}
$committed = Invoke-Git @('diff', "$Base...HEAD")
$working   = Invoke-Git @('diff', 'HEAD')
$untracked = Invoke-Git @('ls-files', '--others', '--exclude-standard')
if (-not ($committed + $working + $untracked).Trim()) { Write-Error "no changes to review"; exit 1 }

$template = Get-Content (Join-Path $PSScriptRoot 'prompts\review.md') -Raw -Encoding UTF8
$planPath = "reports/$TaskId/plan.md"
$prompt = @"
$template

[TaskId] $TaskId
[Diff repository] $gitRepo (paths in the diff are relative to it)
[Work order] $planPath (read it if it exists)
[Untracked files - open and read them directly]
$untracked

[Committed diff: $Base...HEAD]
$committed

[Uncommitted diff]
$working
"@

$OutputEncoding = New-Object System.Text.UTF8Encoding $false
# --ignore-user-config: skip ~/.codex/config.toml (Codex desktop app's elevated sandbox + browser/computer-use plugins).
# Auth still works. Reviewer runs without external tools; unelevated restricted-token sandbox blocks writes.
$CodexArgs = @('--ignore-user-config', '-c', 'windows.sandbox=unelevated')
$prompt | codex exec @CodexArgs --sandbox read-only -C $repo -o (Join-Path $outDir 'review.md') -
if ($LASTEXITCODE -ne 0) { Write-Error "codex exec failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
Write-Host "saved: reports\$TaskId\review.md"
