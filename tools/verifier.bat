@echo off
rem Verification : tests + interface. Resultat dans logs\verif.log
cd /d "%~dp0\.."
if not exist logs mkdir logs
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*gui_selftest*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
timeout /t 2 /nobreak >nul
set "PY=.venv\Scripts\python.exe"
> logs\verif.log 2>&1 (
  "%PY%" -m pip install --disable-pip-version-check -q -e ".[dev]"
  echo === tests
  "%PY%" -m pytest -q
  echo === test gui
  "%PY%" -m wakfu_optimizer.gui_selftest
  echo === FIN
)
