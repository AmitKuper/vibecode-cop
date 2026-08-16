@echo off
rem Stop a detached dashboard: kills ONLY the process listening on port 8780.

powershell -NoProfile -Command ^
  "$c = Get-NetTCPConnection -LocalPort 8780 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { Stop-Process -Id $c.OwningProcess -Force; 'dashboard stopped (pid ' + $c.OwningProcess + ')' } else { 'no dashboard listening on 8780' }"
pause
