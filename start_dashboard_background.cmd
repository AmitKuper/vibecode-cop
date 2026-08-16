@echo off
rem Start the GUI dashboard DETACHED (no console window stays open).
rem Use start_dashboard.cmd instead if you want to see its log / stop it easily.
rem To stop a detached dashboard: taskkill /f /im python.exe is too blunt - use
rem stop_dashboard.cmd, which kills only the process listening on port 8780.

cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -WorkingDirectory '%~dp0' -FilePath 'uv' -ArgumentList 'run','python','scripts/gui_dashboard.py'"
echo Dashboard starting detached at http://127.0.0.1:8780
ping -n 4 127.0.0.1 >nul
start http://127.0.0.1:8780
