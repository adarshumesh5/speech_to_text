# Build Grogu.msi from source.
#
# Steps:
#   1. PyInstaller onedir -> dist\Grogu\Grogu.exe
#   2. WiX v3 (native exes, no .NET required) harvests the onedir
#   3. candle + light -> dist\Grogu-<version>.msi
#
# WiX v3 binaries are downloaded to tools\wix on first run.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# --- 1. PyInstaller --------------------------------------------------------
Write-Host "==> PyInstaller (onedir)"
& .venv\Scripts\python.exe -m PyInstaller --noconfirm grogu.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# --- 2. WiX v3 -------------------------------------------------------------
$wixDir = Join-Path $root "tools\wix"
if (-not (Test-Path (Join-Path $wixDir "light.exe"))) {
    Write-Host "==> Downloading WiX v3 binaries"
    $zip = Join-Path $root "tools\wix-binaries.zip"
    New-Item -ItemType Directory -Force -Path (Join-Path $root "tools") | Out-Null
    Invoke-WebRequest `
        -Uri "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip" `
        -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $wixDir -Force
}
$heat   = Join-Path $wixDir "heat.exe"
$candle = Join-Path $wixDir "candle.exe"
$light  = Join-Path $wixDir "light.exe"

# --- 3. harvest the onedir -------------------------------------------------
$dist  = Join-Path $root "dist\Grogu"
$wixOut = Join-Path $root "build\wix"
# clear stale .wixobj from earlier builds (e.g. pre-rename Sotto) so light
# doesn't link duplicate entry sections
Get-ChildItem $wixOut -Filter "*.wixobj" -ErrorAction SilentlyContinue | Remove-Item -Force
New-Item -ItemType Directory -Force -Path $wixOut | Out-Null

Write-Host "==> heat: harvesting $dist"
& $heat dir $dist `
    -cg GroguComponents `
    -srd `
    -dr INSTALLDIR `
    -gg `
    -g1 `
    -sfrag `
    -sreg `
    -out (Join-Path $wixOut "grogu-files.wxs")
if ($LASTEXITCODE -ne 0) { throw "heat failed" }

Write-Host "==> candle"
& $candle -arch x64 -ext WixUIExtension `
    (Join-Path $root "grogu.wxs") `
    -out (Join-Path $wixOut "grogu.wixobj")
if ($LASTEXITCODE -ne 0) { throw "candle (grogu.wxs) failed" }
& $candle -arch x64 -ext WixUIExtension `
    (Join-Path $wixOut "grogu-files.wxs") `
    -out (Join-Path $wixOut "grogu-files.wixobj")
if ($LASTEXITCODE -ne 0) { throw "candle (grogu-files.wxs) failed" }

Write-Host "==> light"
$version = "0.4.0"
$msi = Join-Path $root "dist\Grogu-$version.msi"
& $light -ext WixUIExtension -cultures:en-us `
    -b $dist `
    (Get-ChildItem $wixOut -Filter "*.wixobj" | ForEach-Object { $_.FullName }) `
    -out $msi
if ($LASTEXITCODE -ne 0) { throw "light failed" }

Write-Host ""
Write-Host "SUCCESS: $msi"
