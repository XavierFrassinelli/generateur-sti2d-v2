@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  Generateur STI2D - One Click Beta Test
echo ========================================

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)

echo.
echo [1/4] Installation dependances Python...
%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [2/4] Installation dependances Node...
call npm install
if errorlevel 1 goto :fail

echo.
echo [3/4] Verification smoke test...
%PY_CMD% smoke_test.py
if errorlevel 1 goto :fail

echo.
echo [4/4] Lancement application...
%PY_CMD% main.py
goto :eof

:fail
echo.
echo [FAIL] Une etape a echoue. Corrigez les erreurs ci-dessus puis relancez.
pause
exit /b 1
