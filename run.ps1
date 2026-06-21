# Prosody TTS Studio launcher
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$port = 8765
$url  = "http://127.0.0.1:$port"

Write-Host ""
Write-Host "  PROSODY · TTS Studio" -ForegroundColor Cyan
Write-Host "  $url" -ForegroundColor DarkCyan
Write-Host "  (Ctrl+C to stop)" -ForegroundColor DarkGray
Write-Host ""

# Open the browser a moment after the server starts.
Start-Process powershell -WindowStyle Hidden -ArgumentList `
  "-NoProfile","-Command","Start-Sleep 2; Start-Process '$url'"

python -m uvicorn backend.app:app --host 127.0.0.1 --port $port
