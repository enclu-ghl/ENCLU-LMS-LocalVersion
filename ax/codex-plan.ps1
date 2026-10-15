# Codex "plan" step: writes a work order to reports/<TaskId>/plan.md (read-only sandbox).
# Usage: powershell -File ax\codex-plan.ps1 AX-20261014-01 -RequestFile reports\AX-20261014-01\request.md
#        powershell -File ax\codex-plan.ps1 AX-20261014-01 -Request "short one-line request"
#   Multi-line requests must use -RequestFile (UTF-8): "powershell -File" splits long arguments on spaces.
# (Keep this file ASCII-only: Windows PowerShell 5.1 misreads BOM-less UTF-8 scripts.)
param(
    [Parameter(Mandatory = $true)][string]$TaskId,
    [string]$Request,
    [string]$RequestFile
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $repo "reports\$TaskId"
New-Item -ItemType Directory -Force $outDir | Out-Null

if ($RequestFile) { $Request = Get-Content $RequestFile -Raw -Encoding UTF8 }
if (-not $Request) { Write-Error "give -Request or -RequestFile"; exit 1 }

$template = Get-Content (Join-Path $PSScriptRoot 'prompts\plan.md') -Raw -Encoding UTF8
$prompt = "$template`n`n[TaskId] $TaskId`n[Request]`n$Request`n"

$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
# --ignore-user-config: skip ~/.codex/config.toml (Codex desktop app's elevated sandbox + browser/computer-use plugins).
# Auth still works. Reviewer runs without external tools; unelevated restricted-token sandbox blocks writes.
$CodexArgs = @('--ignore-user-config', '-c', 'windows.sandbox=unelevated')
$prompt | codex exec @CodexArgs --sandbox read-only -C $repo -o (Join-Path $outDir 'plan.md') -
if ($LASTEXITCODE -ne 0) { Write-Error "codex exec failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
Write-Host "saved: reports\$TaskId\plan.md"
