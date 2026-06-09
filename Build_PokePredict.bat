@echo off
setlocal

cd /d "%~dp0"

echo ======================================
echo   Poke Predict - Build Desktop EXE
echo ======================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found.
  echo Run Launch_PokePredict.bat once first to create it.
  pause
  exit /b 1
)

echo Installing build dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q pyinstaller
if errorlevel 1 (
  echo PyInstaller install failed.
  pause
  exit /b 1
)

echo.
echo Building PokePredict.exe (this can take several minutes)...
".venv\Scripts\pyinstaller.exe" ^
  --noconfirm ^
  --onedir ^
  --name PokePredict ^
  --collect-all streamlit ^
  --collect-all altair ^
  --hidden-import=sklearn.utils._cython_blas ^
  --hidden-import=sklearn.neighbors._partition_nodes ^
  run_app.py

if errorlevel 1 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)

copy /Y "Launch_PokePredict.bat" "dist\PokePredict\Launch_PokePredict.bat" >nul
copy /Y "app.py" "dist\PokePredict\app.py" >nul
copy /Y "requirements.txt" "dist\PokePredict\requirements.txt" >nul
xcopy /E /I /Y "src" "dist\PokePredict\src" >nul

(
echo @echo off
echo cd /d "%%~dp0"
echo start "" "PokePredict.exe"
) > "dist\PokePredict\Launch_PokePredict.bat"

echo.
echo Build complete.
echo Run: dist\PokePredict\PokePredict.exe
echo Or double-click: dist\PokePredict\Launch_PokePredict.bat
echo.
pause
