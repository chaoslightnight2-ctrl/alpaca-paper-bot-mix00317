param(
    [ValidateSet("dry_run", "execute")]
    [string]$Mode = "execute",
    [string]$RepoRoot = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

$repo = Resolve-Path -LiteralPath $RepoRoot
$guard = Join-Path $repo "run_local_guard.ps1"
if (-not (Test-Path -LiteralPath $guard)) {
    throw "Missing guard script: $guard"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "python was not found in PATH. Install Python or add it to PATH before installing the task."
}

$taskPrefix = "AlpacaPaperBot"
$tasks = @(
    @{
        Name = "$taskPrefix-MainSessionGuard"
        At = "16:15"
        MaxMinutes = 430
        Description = "Runs the Alpaca paper bot local auto-window guard across the US market session."
    },
    @{
        Name = "$taskPrefix-CloseBackupGuard"
        At = "21:10"
        MaxMinutes = 135
        Description = "Backup close guard in case the main local guard was missed or interrupted."
    }
)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8)

foreach ($item in $tasks) {
    $taskName = $item.Name
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$guard`" -Mode $Mode -MaxMinutes $($item.MaxMinutes) -RepoRoot `"$repo`""
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $item.At
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $item.Description `
        -Force | Out-Null

    Write-Host "Installed $taskName at $($item.At) Europe/Istanbul, mode=$Mode, max_minutes=$($item.MaxMinutes)"
}

Write-Host "Done. Keep Windows awake and connected to the internet during trading hours."
