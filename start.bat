@echo off
cd /d "%~dp0"

:: Check Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    echo.
    pause
    exit /b 1
)

:: Check Python version
python -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python 3.8+ required.
    python --version
    echo.
    pause
    exit /b 1
)

:: Check dependencies
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependencies...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

:: Launch via Python (handles server start, health check, browser, and shutdown)
python start.py --web
if %errorlevel% neq 0 (
    echo.
    echo Server exited with code %errorlevel%.
)

exit /b 0
