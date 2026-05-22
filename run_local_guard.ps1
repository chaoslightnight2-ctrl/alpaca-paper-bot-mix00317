param(
    [ValidateSet("dry_run", "execute")]
    [string]$Mode = "execute",
    [double]$MaxMinutes = 430,
    [string]$RepoRoot = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

$mutexName = "Global\AlpacaPaperBotLocalGuard"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$hasLock = $false

try {
    $hasLock = $mutex.WaitOne(0)
    if (-not $hasLock) {
        Write-Host "Another local guard is already running; exiting."
        exit 0
    }

    Set-Location -LiteralPath $RepoRoot
    New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "logs") | Out-Null

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $logPath = Join-Path $RepoRoot "logs\local_guard_$stamp.log"
    Start-Transcript -Path $logPath -Append | Out-Null

    try {
        $flag = if ($Mode -eq "execute") { "--execute" } else { "--dry-run" }
        Write-Host "Starting local guard: mode=$Mode max_minutes=$MaxMinutes repo=$RepoRoot"
        python paper_bot.py $flag --auto-window --loop --max-minutes $MaxMinutes
        Write-Host "Local guard finished cleanly."
    }
    finally {
        Stop-Transcript | Out-Null
    }
}
finally {
    if ($hasLock) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
