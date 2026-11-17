# Builds a fully self-contained YouTubeDownloader.exe:
#  - finds the FFmpeg you already installed (via winget) and copies it into
#    the project so PyInstaller bundles it INSIDE the exe (no separate
#    FFmpeg install needed on any machine that runs the exe afterwards)
#  - installs/upgrades PyInstaller in the project's virtual environment
#  - builds using build.spec (which also picks up assets\app_icon.ico)
#
# Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "== Locating FFmpeg ==" -ForegroundColor Cyan
$ffmpegSrcDir = $null

$ffmpegCmd = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if ($ffmpegCmd) {
    $target = $ffmpegCmd.Source
    # winget's PATH entry is often a tiny shim/symlink -- resolve the real file if so.
    $size = (Get-Item $target).Length
    if ($size -lt 1MB) {
        $resolved = (Get-Item $target).Target
        if ($resolved) { $target = $resolved }
    }
    if (Test-Path $target) {
        $ffmpegSrcDir = Split-Path $target -Parent
    }
}

if (-not $ffmpegSrcDir) {
    $wingetPkg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Directory -Filter "Gyan.FFmpeg*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetPkg) {
        $found = Get-ChildItem $wingetPkg.FullName -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $ffmpegSrcDir = $found.DirectoryName }
    }
}

if (-not $ffmpegSrcDir) {
    Write-Host "Could not locate FFmpeg automatically." -ForegroundColor Yellow
    Write-Host "The .exe will still build, but it will rely on FFmpeg being installed/on PATH" -ForegroundColor Yellow
    Write-Host "on whatever machine runs it. Run 'winget install ffmpeg' first if you want it" -ForegroundColor Yellow
    Write-Host "fully bundled, then re-run this script." -ForegroundColor Yellow
} else {
    Write-Host "Found FFmpeg at: $ffmpegSrcDir" -ForegroundColor Green
    New-Item -ItemType Directory -Force -Path "$projectRoot\ffmpeg" | Out-Null
    Copy-Item (Join-Path $ffmpegSrcDir "ffmpeg.exe") "$projectRoot\ffmpeg\ffmpeg.exe" -Force
    Copy-Item (Join-Path $ffmpegSrcDir "ffprobe.exe") "$projectRoot\ffmpeg\ffprobe.exe" -Force
    Write-Host "Copied ffmpeg.exe and ffprobe.exe into the project -- they will be bundled into the .exe." -ForegroundColor Green
}

Write-Host ""
Write-Host "== Installing app dependencies + PyInstaller into the venv ==" -ForegroundColor Cyan
& "$projectRoot\.venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip install failed -- see the error above. Aborting." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "== Verifying PySide6 is importable in the venv ==" -ForegroundColor Cyan
& "$projectRoot\.venv\Scripts\python.exe" -c "import PySide6; print('PySide6 OK:', PySide6.__version__)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "PySide6 did not import correctly in the venv -- aborting before building a broken exe." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "== Cleaning previous build ==" -ForegroundColor Cyan
Remove-Item -Recurse -Force "$projectRoot\build" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$projectRoot\dist" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "== Building YouTubeDownloader.exe ==" -ForegroundColor Cyan
# Invoked as "python -m PyInstaller" (rather than pyinstaller.exe) to guarantee
# this exact venv's interpreter -- and therefore its installed packages -- is
# the one PyInstaller's dependency analysis sees.
& "$projectRoot\.venv\Scripts\python.exe" -m PyInstaller build.spec

Write-Host ""
$exePath = "$projectRoot\dist\YouTubeDownloader\YouTubeDownloader.exe"
if (Test-Path $exePath) {
    Write-Host "SUCCESS -- your app is ready at:" -ForegroundColor Green
    Write-Host $exePath -ForegroundColor Green
    if ($ffmpegSrcDir) {
        Write-Host "FFmpeg is bundled inside it, so it will run on any Windows PC without extra setup." -ForegroundColor Green
    }
} else {
    Write-Host "The build finished but the .exe was not found -- scroll up for the PyInstaller error." -ForegroundColor Red
}

Read-Host "Press Enter to close"
