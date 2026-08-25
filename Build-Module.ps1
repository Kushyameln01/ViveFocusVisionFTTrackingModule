$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host 'Building VIVE Focus Vision Hybrid v1.0.1...'
python "$Root\tools\build_module.py"

$Dist = Join-Path $Root 'dist'
Write-Host ''
Write-Host 'Build complete.'
Write-Host 'In VRCFaceTracking open: Module Registry -> Install Module from .zip'
Write-Host "Select: $Dist\VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip"

if (Test-Path $Dist) {
    Start-Process explorer.exe $Dist
}
