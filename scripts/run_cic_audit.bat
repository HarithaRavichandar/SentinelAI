@echo off
setlocal

REM CIC Audit & Split Runner
REM Usage: run_cic_audit.bat [--force]

REM Use Python 3.13 (available on this machine, no third-party packages needed)
set "PYEXE=C:\Users\harit\AppData\Local\Programs\Python\Python313\python.exe"
set "SCRIPT=H:\SentinelAI\scripts\cic_audit_and_split.py"

if not exist "%PYEXE%" (
    echo ERROR: Python 3.13 not found at %PYEXE%
    echo Please edit PYEXE in this batch file to point to a working Python 3.x interpreter.
    exit /b 1
)

echo Running CIC Audit and Split Pipeline...
echo Python: %PYEXE%
echo Script: %SCRIPT%
echo.

"%PYEXE%" "%SCRIPT%" %*

echo.
echo Exit code: %ERRORLEVEL%
endlocal
