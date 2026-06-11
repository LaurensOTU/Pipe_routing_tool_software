@echo off
echo ============================================
echo  Damen Pipe Routing Tool - Setup
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on this machine.
    echo.
    echo Please install Python from https://www.python.org/downloads/
    echo IMPORTANT: During installation, tick "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.
echo Installing required packages...
echo.

pip install -r requirements.txt

echo.
if errorlevel 1 (
    echo ERROR: Something went wrong during installation.
    echo Please check the messages above and try again.
) else (
    echo ============================================
    echo  Setup complete. You can now run the tool
    echo  by double-clicking run_tool.bat
    echo ============================================
)

echo.
pause
