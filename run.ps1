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

# Prefer the RVC-enabled Python 3.10 venv if it exists, else system Python.
$venvPy = Join-Path $PSScriptRoot ".venv310\Scripts\python.exe"
$py = if (Test-Path $venvPy) { $venvPy } else { "python" }
Write-Host "  python: $py" -ForegroundColor DarkGray

# Hide AMD ROCm from PyTorch: its hipcc on PATH makes torch.utils.cpp_extension
# raise on Windows, which would otherwise break the RVC (fairseq) import.
$env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notmatch 'AMD\\ROCm' }) -join ';'
Remove-Item env:ROCM_HOME -ErrorAction SilentlyContinue
Remove-Item env:ROCM_PATH -ErrorAction SilentlyContinue
Remove-Item env:HIP_PATH  -ErrorAction SilentlyContinue

# Open the browser a moment after the server starts.
Start-Process powershell -WindowStyle Hidden -ArgumentList `
  "-NoProfile","-Command","Start-Sleep 2; Start-Process '$url'"

& $py -m uvicorn backend.app:app --host 127.0.0.1 --port $port
