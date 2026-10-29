@echo off
rem Lanceur : double-cliquez sur ce fichier.
rem Premier lancement : cree un environnement Python et installe les dependances (2-5 min).
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Wakfu Optimizer
set "PY=.venv\Scripts\python.exe"
set "PYW=.venv\Scripts\pythonw.exe"

if exist "%PY%" goto deps
echo Premiere installation : creation de l'environnement Python...
py -3 -m venv .venv >nul 2>&1
if exist "%PY%" goto deps
python -m venv .venv
if exist "%PY%" goto deps
echo.
echo Python 3.12 ou plus recent est introuvable.
echo Installez-le depuis https://www.python.org/downloads/ en cochant "Add python.exe to PATH", puis relancez.
pause
exit /b 1

:deps
"%PY%" -c "import ortools, yaml, wakfu_optimizer.web" >nul 2>&1
if not errorlevel 1 goto shortcut
echo Installation des dependances, quelques minutes la premiere fois...
"%PY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%PY%" -m pip install --disable-pip-version-check -e .
if errorlevel 1 goto fail

:shortcut
if exist ".shortcut_done" goto run
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Wakfu Optimizer.lnk')); $s.TargetPath='%~dp0Lancer Wakfu Optimizer.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()" >nul 2>&1
echo ok> ".shortcut_done"

:run
start "" "%PYW%" -m wakfu_optimizer.web
exit /b 0

:fail
echo.
echo L'installation a echoue. Verifiez votre connexion internet puis relancez.
pause
exit /b 1
