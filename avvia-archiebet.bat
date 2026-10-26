@echo off
rem Avvia ArchieBet: backend (porta 8000), frontend (porta 4280) e apre il browser.
cd /d "%~dp0"

rem Applica eventuali nuove migrazioni del database prima di partire
backend\.venv\Scripts\alembic.exe -c backend\alembic.ini upgrade head >nul 2>&1

start "ArchieBet - backend (non chiudere)" /min cmd /k "cd /d "%~dp0backend" && .venv\Scripts\uvicorn.exe app.main:app --port 8000"
start "ArchieBet - frontend (non chiudere)" /min cmd /k "cd /d "%~dp0frontend" && npm start"

echo Avvio di ArchieBet in corso: il browser si apre appena e' pronto...
powershell -NoProfile -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4280 -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"
if errorlevel 1 (
  echo ArchieBet non risponde dopo 3 minuti: guarda le finestre "backend" e "frontend" per l'errore.
  pause
  exit /b 1
)
start "" http://127.0.0.1:4280
