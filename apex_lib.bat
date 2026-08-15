@echo off
title 📚 Library Management System

:: ── AUTO-DETECT PROJECT PATH ──────────────────────────────────
:: This batch file detects its own location — no editing needed!
set "LIB_MS_PATH=%~dp0"
:: Remove trailing backslash if present
if "%LIB_MS_PATH:~-1%"=="\" set "LIB_MS_PATH=%LIB_MS_PATH:~0,-1%"

:: ── OPTIONS ───────────────────────────────────────────────────
:: Default mode: web | cli | both
set "DEFAULT_MODE=web"

:: ── DO NOT EDIT BELOW ─────────────────────────────────────────

:: Check Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ❌ ERROR: Python is not installed or not in PATH.
    echo     Please install Python 3.10+ from https://python.org
    echo     and make sure it's added to your PATH.
    echo.
    pause
    exit /b 1
)

:: Allow user to pass mode as argument
if not "%1"=="" (
    set "MODE=%1"
) else (
    set "MODE=%DEFAULT_MODE%"
)

:: Validate the project path exists
if not exist "%LIB_MS_PATH%\main.py" (
    echo.
    echo  ❌ ERROR: Could not find Library Management System at:
    echo     %LIB_MS_PATH%
    echo.
    echo  📝 Make sure this batch file is placed in the project folder
    echo     alongside main.py and web_app.py.
    echo.
    pause
    exit /b 1
)

:: Navigate to the project directory
cd /d "%LIB_MS_PATH%"

:: Launch based on mode
if /i "%MODE%"=="cli"   goto :launch_cli
if /i "%MODE%"=="both"  goto :launch_both
if /i "%MODE%"=="c"     goto :launch_cli
if /i "%MODE%"=="b"     goto :launch_both
if /i "%MODE%"=="web"   goto :launch_web
if /i "%MODE%"=="w"     goto :launch_web
goto :launch_web

:launch_web
cls
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║     📚 Library Management System v2.0       ║
echo  ║     🌐 Web Dashboard Mode                   ║
echo  ╚══════════════════════════════════════════════╝
echo.
echo  🔐 Login: ADMIN001 / admin123
echo  ⌨️  Press Ctrl+K to search books anywhere
echo.
timeout /t 2 /nobreak >nul
start http://localhost:5000
python web_app.py
goto :done

:launch_cli
cls
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║     📚 Library Management System v2.0       ║
echo  ║     🖥️  CLI Mode                            ║
echo  ╚══════════════════════════════════════════════╝
echo.
python main.py
goto :done

:launch_both
cls
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║     📚 Library Management System v2.0       ║
echo  ║     🌐 + 🖥️  Both Modes                     ║
echo  ╚══════════════════════════════════════════════╝
echo.
echo  🔐 Login: ADMIN001 / admin123
echo  🔄 Web server launching in a separate window...
echo.
:: Launch web in a new window
start "LibraryMS Web" cmd /c "cd /d \"%LIB_MS_PATH%\" && python web_app.py"
timeout /t 2 /nobreak >nul
start http://localhost:5000
:: Launch CLI in current window
python main.py
goto :done

:done
echo.
echo  Server stopped. Press any key to exit.
pause >nul
exit /b 0
