@echo off
rem Avvia ArchieBet, oppure lo riavvia se e' gia' acceso (un solo tasto: chiude backend e frontend e li riapre).
cd /d "%~dp0"
rem Chiude tutti i processi di ArchieBet (anche il processo padre di uvicorn e di ng serve), poi chi resta sulle porte
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'archiebet' -and $_.CommandLine -match 'uvicorn|ng\.js|npm' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; foreach ($port in 8000, 4280) { foreach ($c in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } }"
taskkill /fi "WINDOWTITLE eq ArchieBet - backend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq ArchieBet - frontend*" /t /f >nul 2>&1
call "%~dp0avvia-archiebet.bat"
