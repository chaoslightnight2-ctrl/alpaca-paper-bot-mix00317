$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $Root

function Start-IfMissing {
    param(
        [string]$Match,
        [string]$Arguments
    )
    $existing = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
        Where-Object { $_.CommandLine -like "*$Match*" }
    if (-not $existing) {
        Start-Process -FilePath "python" -ArgumentList $Arguments -WorkingDirectory $Root -WindowStyle Hidden
    }
}

Start-IfMissing -Match "dashboard.py" -Arguments ".\dashboard.py"
Start-Sleep -Seconds 1
Start-IfMissing -Match "paper_bot.py --execute --loop" -Arguments ".\paper_bot.py --execute --loop"
Start-Sleep -Seconds 1
Start-Process "http://127.0.0.1:8765"
