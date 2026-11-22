@echo off
setlocal
set "PYEXE=C:\Users\harit\AppData\Local\Programs\Python\Python313\python.exe"
set "SCRIPT=H:\SentinelAI\scripts\cic_audit_and_split.py"
echo Checking syntax...
"%PYEXE%" -m py_compile "%SCRIPT%"
if %ERRORLEVEL%==0 (
    echo SYNTAX OK
) else (
    echo SYNTAX ERROR
    exit /b 1
)
