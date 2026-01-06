@echo off
echo =============================================
echo Multilogin Window Manager - Build Script
echo =============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

echo Python found!
echo.

REM Install PyInstaller
echo Installing PyInstaller...
pip install pyinstaller
echo.

REM Build the executable
echo Building executable...
pyinstaller --onefile --windowed --name "MLM_Window_Manager" mlm_window_manager.py

echo.
echo =============================================
if exist "dist\MLM_Window_Manager.exe" (
    echo BUILD SUCCESSFUL!
    echo.
    echo Your executable is located at:
    echo   dist\MLM_Window_Manager.exe
    echo.
    echo You can copy this file anywhere and run it.
) else (
    echo BUILD FAILED! Check errors above.
)
echo =============================================
echo.
pause
