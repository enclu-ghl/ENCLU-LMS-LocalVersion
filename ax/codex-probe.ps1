# Cheap check whether Codex can be used right now (run at the start of each task while in fallback mode).
# Usage: powershell -File ax\codex-probe.ps1
# Exit: 0 = available, 3 = usage limit reached, other = other failure.
# (Keep this file ASCII-only: Windows PowerShell 5.1 misreads BOM-less UTF-8 scripts.)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'lib.ps1')
$out = Join-Path ([IO.Path]::GetTempPath()) 'codex-probe.md'
Invoke-Codex 'Reply with exactly: OK. Do not run any commands.' $out $repo
Write-Host "CODEX_AVAILABLE: $((Get-Content $out -Raw).Trim())"
