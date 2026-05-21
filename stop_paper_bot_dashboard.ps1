$ErrorActionPreference = "SilentlyContinue"
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*paper_bot.py*" -or $_.CommandLine -like "*dashboard.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
