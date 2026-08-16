@echo off
rem Start the persistent Cop/Thief GUI dashboard (history + replays + live panels).
rem Double-click to run in a console window; close the window (or Ctrl+C) to stop.
rem The dashboard is read-only and never affects a match - safe to leave running.
rem
rem   http://127.0.0.1:8780        the hub (game history, live status)
rem   http://127.0.0.1:8780/replay the replay viewer
rem
rem Requires uv on PATH (the same tool every other script in this repo uses).

cd /d "%~dp0"
title CopThief Dashboard - http://127.0.0.1:8780
echo Starting dashboard at http://127.0.0.1:8780  (close this window to stop)
uv run python scripts\gui_dashboard.py %*
pause
