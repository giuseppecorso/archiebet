@echo off
rem Spegne ArchieBet: chiude i programmi in ascolto sulle porte 8000 (backend) e 4280 (frontend).
rem Chiude tutti i processi di ArchieBet (anche il processo padre di uvicorn e di ng serve), poi chi resta sulle porte
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'archiebet' -and $_.CommandLine -match 'uvicorn|ng\.js|npm' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; foreach ($port in 8000, 4280) { foreach ($c in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } }"
taskkill /fi "WINDOWTITLE eq ArchieBet - backend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq ArchieBet - frontend*" /t /f >nul 2>&1
echo ArchieBet spento.
timeout /t 2 >nul
