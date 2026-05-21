$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
python .\paper_bot.py --execute --loop
