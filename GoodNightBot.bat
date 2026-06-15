@echo off
title GoodNightBot
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 ( start "" pythonw bootstrap.py & exit /b )
where python >nul 2>nul
if %errorlevel%==0 ( start "" python bootstrap.py & exit /b )
echo.
echo   Python ne nayden.
echo   Ustanovi Python 3.10+ s python.org i otmet' "Add Python to PATH".
echo.
start "" https://www.python.org/downloads/
pause
