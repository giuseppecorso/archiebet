# ArchieBet — Backend

FastAPI + SQLAlchemy (SQLite in locale). Comandi da lanciare dentro `backend/` (PowerShell).

## Prima volta

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m app.cli create-user giuse --admin
```

## Uso quotidiano

```powershell
.venv\Scripts\uvicorn app.main:app --reload --port 8000   # avvia il server
.venv\Scripts\python -m pytest                             # esegue i test
```

Documentazione interattiva delle API: http://localhost:8000/docs

## Database

Dopo aver cambiato un modello in `app/models/`:

```powershell
.venv\Scripts\alembic revision --autogenerate -m "descrizione della modifica"
.venv\Scripts\alembic upgrade head
```

## Struttura

| Cartella | Cosa contiene |
|----------|---------------|
| `app/models/` | Tabelle. Dati per utente sempre con `user_id`; dati per partita senza (sezione 14.2) |
| `app/auth/` | Login con cookie di sessione, password Argon2 |
| `app/adapters/` | Un modulo per ogni fonte dati, con cache su file (sezione 14.4) |
| `app/ai/gateway.py` | Unico punto di accesso all'AI, con tetto di spesa (sezione 14.3) |
| `app/usage.py` | Registro dei consumi di API e AI (sezione 14.7) |
| `migrations/` | Migrazioni Alembic |
