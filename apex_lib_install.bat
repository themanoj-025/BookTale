@echo off
setlocal enabledelayedexpansion
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║     📚 Library Management System            ║
echo  ║     🔧 apex_lib Global Installer            ║
echo  ╚══════════════════════════════════════════════╝
echo.
echo  This will register the 'apex_lib' command globally
echo  so you can launch the server from any CMD terminal
echo  by simply typing:  apex_lib
echo.

:: Project directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: Check if the apex_lib.bat exists in this folder
if not exist "%SCRIPT_DIR%\apex_lib.bat" (
    echo  ❌ ERROR: apex_lib.bat not found in this folder.
    echo     Make sure this installer is in the same folder
    echo     as apex_lib.bat
    echo.
    pause
    exit /b 1
)

echo  1. Copy apex_lib.bat to a PATH folder (e.g. System32)
echo  2. Add the project folder to your USER PATH
echo.
set /p "CHOICE=  Choose [1] or [2] (default: 2): "
if "%CHOICE%"=="" set "CHOICE=2"

if "%CHOICE%"=="1" goto :copy_system
if "%CHOICE%"=="2" goto :add_path
echo  ❌ Invalid choice.
pause
exit /b 1

:copy_system
:: Check for admin rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ⚠️  Administrator privileges required for this option!
    echo     Right-click this file and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

copy /y "%SCRIPT_DIR%\apex_lib.bat" "%windir%\System32\apex_lib.bat" >nul
if %errorlevel% equ 0 (
    echo  ✅ Installed to System32!
) else (
    echo  ❌ Failed to copy. Try running as Administrator.
    pause
    exit /b 1
)
goto :success

:add_path
:: Check if already in PATH
echo %PATH% | findstr /i "%SCRIPT_DIR%" >nul 2>&1
if %errorlevel% equ 0 (
    echo  ℹ️  Project folder is already in your PATH.
    goto :success
)

:: Add to user PATH using setx
setx PATH "%PATH%;%SCRIPT_DIR%" >nul
if %errorlevel% equ 0 (
    echo  ✅ Added to user PATH: %SCRIPT_DIR%
) else (
    echo  ❌ Failed to update PATH.
    pause
    exit /b 1
)
goto :success

:success
echo.
echo  🎉 Installation complete!
echo.
echo  You can now open any CMD terminal and type:
echo.
echo     apex_lib          → Web Dashboard (default)
echo     apex_lib web      → Web Dashboard
echo     apex_lib cli      → CLI Interface
echo     apex_lib both     → Web + CLI together
echo.
echo  ⚠️  You may need to restart any open terminals for
echo     the command to take effect.
echo.
pause
