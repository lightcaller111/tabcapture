@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto installed
set "TABCAPTURE_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%TABCAPTURE_PY%" (
  "%TABCAPTURE_PY%" -m venv .venv
) else (
  py -3 -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo Install Python 3.10 or newer from python.org with the Python launcher.
  pause
  exit /b 1
)
:installed
if not exist .venv\installed.ok (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (
    pause
    exit /b 1
  )
  echo installed>.venv\installed.ok
)
.venv\Scripts\python.exe -m streamlit run app.py --global.developmentMode false --server.address 127.0.0.1 --server.maxUploadSize 2048 --browser.gatherUsageStats false
pause
