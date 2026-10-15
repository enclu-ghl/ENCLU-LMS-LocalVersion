# Shared helper for ax\codex-*.ps1 (dot-source it). Keep ASCII-only (Windows PowerShell 5.1).
#
# Invoke-Codex runs "codex exec" read-only and saves the last message to $OutFile.
# Exit codes for the calling script:
#   0 = ok
#   3 = Codex usage/rate limit reached (CODEX_QUOTA_EXHAUSTED) -> stop and ask the user (docs/AX_RULES.md 2-1)
#   other = Codex failed for another reason
# Full Codex output is kept next to $OutFile as *.log (ignored by git).

# Encoding for text piped to native programs. Must be set at script scope (this file is dot-sourced):
# assigning $OutputEncoding inside the function does NOT apply to the pipe in Windows PowerShell 5.1,
# and Korean prompts reached Codex as '?' (found 2026-10-15).
$global:OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Invoke-Codex([string]$Prompt, [string]$OutFile, [string]$WorkDir) {
    $log = [IO.Path]::ChangeExtension($OutFile, '.log')
    # --ignore-user-config: skip ~/.codex/config.toml (Codex desktop app's elevated sandbox + browser/computer-use plugins).
    # Auth still works. Reviewer runs without external tools; unelevated restricted-token sandbox blocks writes.
    $CodexArgs = @('--ignore-user-config', '-c', 'windows.sandbox=unelevated')

    # Native stderr must not become a terminating error while we capture it.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $Prompt | codex exec @CodexArgs --sandbox read-only -C $WorkDir -o $OutFile - 2>&1 |
        ForEach-Object { "$_" } | Tee-Object -FilePath $log | Out-Host
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev

    if ($code -ne 0) {
        # Look only at the CLI's own error lines near the end. The log also holds the prompt and model text,
        # which may legitimately mention "quota" etc. (e.g. while reviewing this very file).
        $errLines = Get-Content $log -Tail 30 -ErrorAction SilentlyContinue |
            Where-Object { $_ -match '^\s*(ERROR|Error|error)\b' }
        $limit = '(?i)usage limit|rate limit|rate_limit|quota|too many requests|\b429\b|limit reached|insufficient_quota|try again (in|later|at)'
        if ((@($errLines) -join "`n") -match $limit) {
            Write-Host "CODEX_QUOTA_EXHAUSTED: Codex usage limit reached (see $log)."
            Write-Host "Stop and ask the user before switching to the no-Codex fallback (docs/AX_RULES.md 2-1)."
            exit 3
        }
        # Write-Host, not Write-Error: with ErrorActionPreference=Stop the latter ends the script with exit 1.
        Write-Host "CODEX_FAILED: codex exec failed (exit $code, see $log)"
        exit $code
    }
}
