# =====================================================================
#  setup_rvc.ps1  -  one-shot installer for the optional RVC stage
#
#  Builds the Python 3.10 venv (.venv310) with the full app + RVC stack.
#  Encodes every Windows-specific fix this machine needed:
#    * Python 3.10 (rvc-python pins numpy<=1.23.5 -> needs 3.10)
#    * setuptools<81 (restores pkg_resources that torch 2.1.2 imports)
#    * One-sixth/fairseq fork 0.12.3 (the real fairseq has no Windows wheels)
#    * MSVC env via vcvars64 (+ DISTUTILS_USE_SDK=1 for torch's ABI check)
#    * AMD ROCm hidden from torch (hipcc on PATH breaks cpp_extension on Win)
#    * fairseq/examples pre-created (avoids a privileged symlink)
#    * rvc-python installed --no-deps (don't drag in wheel-less fairseq==0.12.2)
#
#  Run from the project root:   .\setup_rvc.ps1
# =====================================================================
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv310"
$vpy  = Join-Path $venv "Scripts\python.exe"

function Section($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }

# --- locate Python 3.10 ---
Section "Python 3.10"
try { py -3.10 --version } catch { throw "Python 3.10 is required (install it, then re-run). 'py -3.10' not found." }

# --- locate MSVC (vcvars64.bat) ---
Section "Visual C++ build tools"
$vcvars = $null
$known = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if (Test-Path $known) { $vcvars = $known }
else {
  $vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
  if (Test-Path $vswhere) {
    $inst = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($inst) { $vcvars = Join-Path $inst "VC\Auxiliary\Build\vcvars64.bat" }
  }
}
if (-not $vcvars -or -not (Test-Path $vcvars)) {
  throw "MSVC not found. Install 'Desktop development with C++' (VS 2022 Build Tools), then re-run."
}
Write-Host "vcvars: $vcvars"

# --- create venv + core app deps ---
Section "venv + core app deps"
if (-not (Test-Path $vpy)) { py -3.10 -m venv $venv }
& $vpy -m pip install --upgrade pip wheel | Out-Null
& $vpy -m pip install "setuptools<81" | Out-Null
& $vpy -m pip install "fastapi==0.115.6" "uvicorn[standard]==0.34.0" "edge-tts>=7.2.8" "python-multipart==0.0.20" "aiofiles==24.1.0"

# --- build prerequisites + CPU torch ---
Section "build prereqs + torch (CPU)"
& $vpy -m pip install "cython" "numpy==1.23.5"
& $vpy -m pip install torch==2.1.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cpu

# --- build the fairseq fork ---
Section "fairseq fork (MSVC build)"
# import the MSVC x64 environment
cmd /c "`"$vcvars`" && set" | ForEach-Object {
  if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "env:$($matches[1])" -Value $matches[2] }
}
# hide ROCm + satisfy torch's VC ABI check
$env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notmatch 'AMD\\ROCm' }) -join ';'
Remove-Item env:ROCM_HOME -ErrorAction SilentlyContinue
Remove-Item env:ROCM_PATH -ErrorAction SilentlyContinue
Remove-Item env:HIP_PATH  -ErrorAction SilentlyContinue
$env:DISTUTILS_USE_SDK = "1"

& $vpy -c "import fairseq" 2>$null
if ($LASTEXITCODE -ne 0) {
  $work = Join-Path $env:TEMP "fairseq_build"
  if (Test-Path $work) { Remove-Item $work -Recurse -Force }
  New-Item -ItemType Directory -Force $work | Out-Null
  $zip = Join-Path $work "fairseq.zip"
  Invoke-WebRequest "https://github.com/One-sixth/fairseq/archive/main.zip" -OutFile $zip
  Expand-Archive $zip -DestinationPath $work -Force
  $src = Join-Path $work "fairseq-main"
  New-Item -ItemType Directory -Force (Join-Path $src "fairseq\examples") | Out-Null  # avoid privileged symlink
  & $vpy -m pip install --no-build-isolation $src
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
} else { Write-Host "fairseq already installed." }

# --- rvc-python + runtime deps ---
Section "rvc-python"
& $vpy -m pip install "faiss-cpu==1.7.3" "praat-parselmouth>=0.4.2" pyworld torchcrepe soundfile av ffmpeg-python loguru
& $vpy -m pip install --no-deps rvc-python

# --- verify ---
Section "verify"
& $vpy -c "import fairseq; from rvc_python.infer import RVCInference; print('RVC stack OK - fairseq', fairseq.__version__)"

Write-Host "`nDone. Start the app with .\run.ps1 (it auto-uses .venv310)." -ForegroundColor Green
Write-Host "First generation with RVC downloads ~500MB of base models (one time)." -ForegroundColor DarkGray
