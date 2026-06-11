@echo off
echo ============================================
echo  Damen Pipe Routing Tool
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on this machine.
    echo Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

:: Move to the folder this .bat file lives in
cd /d "%~dp0"

:: Check if streamlit is installed
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Streamlit is not installed.
    echo Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

echo Starting the tool... the browser will open automatically.
echo Keep this window open while using the tool.
echo Close this window to stop the tool.
echo.

streamlit run app.py
