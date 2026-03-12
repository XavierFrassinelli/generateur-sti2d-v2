@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  Build beta zip package
echo ========================================

set "PKG_NAME=Beta_Generateur_STI2D_V3"
set "TEMP_DIR=%TEMP%\%PKG_NAME%"
set "DEST=%~dp0..\%PKG_NAME%.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; " ^
  "$src = Get-Item -LiteralPath '%~dp0'; " ^
  "$tmp = '%TEMP_DIR%'; " ^
  "$destZip = '%DEST%'; " ^
  "if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }; " ^
  "if (Test-Path -LiteralPath $destZip) { Remove-Item -LiteralPath $destZip -Force }; " ^
  "$pkgRoot = Join-Path $tmp 'projet_sti2d'; " ^
  "New-Item -ItemType Directory -Path $pkgRoot -Force | Out-Null; " ^
  "$excludeDirs = @('node_modules','__pycache__','.git','.vscode'); " ^
  "Get-ChildItem -LiteralPath $src.FullName -Force | Where-Object { " ^
  "  $name = $_.Name; " ^
  "  if ($excludeDirs -contains $name) { return $false }; " ^
  "  if ($_.PSIsContainer) { return $true }; " ^
  "  return -not $name.EndsWith('.pyc'); " ^
  "} | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $pkgRoot -Recurse -Force }; " ^
  "Compress-Archive -Path $pkgRoot -DestinationPath $destZip -CompressionLevel Optimal; " ^
  "Remove-Item -LiteralPath $tmp -Recurse -Force"
if errorlevel 1 (
  echo [FAIL] Echec creation zip.
  pause
  exit /b 1
)

echo.
echo [OK] Archive creee: %DEST%
echo [OK] Arborescence conservee (dossier projet_sti2d inclus).
pause
exit /b 0
