@echo off
rem Spegne ArchieBet: chiude i programmi in ascolto sulle porte 8000 (backend) e 4280 (frontend).
powershell -NoProfile -Command "foreach ($port in 8000, 4280) { foreach ($c in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } }"
taskkill /fi "WINDOWTITLE eq ArchieBet - backend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq ArchieBet - frontend*" /t /f >nul 2>&1
echo ArchieBet spento.
timeout /t 2 >nul
