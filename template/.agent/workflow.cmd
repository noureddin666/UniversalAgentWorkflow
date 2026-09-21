@echo off
setlocal
set SCRIPT=%~dp0workflow.py
if defined UAW_PYTHON ( "%UAW_PYTHON%" "%SCRIPT%" %* & exit /b %ERRORLEVEL% )
where python >nul 2>&1 && ( python "%SCRIPT%" %* & exit /b %ERRORLEVEL% )
where python3 >nul 2>&1 && ( python3 "%SCRIPT%" %* & exit /b %ERRORLEVEL% )
where py >nul 2>&1 && ( py "%SCRIPT%" %* & exit /b %ERRORLEVEL% )
echo No Python interpreter found; set UAW_PYTHON to one. 1>&2
exit /b 127
