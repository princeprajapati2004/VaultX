@echo off
REM VaultX Build Script - Creates standalone Windows executable
REM Run this file to build VaultX.exe
REM Requires: pip install pyinstaller

echo ================================
echo VaultX Executable Builder
echo ================================
echo.

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Error: PyInstaller not installed
    echo Install with: pip install pyinstaller
    pause
    exit /b 1
)

echo Cleaning previous builds...
if exist "dist\" rmdir /s /q dist >nul 2>&1
if exist "build\" rmdir /s /q build >nul 2>&1
if exist "*.spec" del *.spec >nul 2>&1

echo.
echo Building VaultX.exe...
echo.

REM Build executable
pyinstaller --onefile ^
  --windowed ^
  --name VaultX ^
  --add-data "data:data" ^
  --distpath ".\dist" ^
  --buildpath ".\build" ^
  main.py

if errorlevel 1 (
    echo.
    echo Error: Build failed!
    pause
    exit /b 1
)

echo.
echo ================================
echo Build Complete!
echo ================================
echo.
echo VaultX.exe created in: dist\VaultX.exe
echo.
echo Next steps:
echo 1. Copy dist\VaultX.exe to desired location
echo 2. Run VaultX.exe to launch the application
echo 3. (Optional) Register context menu:
echo    python context_menu_setup.py --register "full_path_to_VaultX.exe"
echo.
pause
