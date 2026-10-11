# ArchieBet — Registro delle decisioni

Ogni decisione importante con data, scelta e motivo. Le decisioni di prodotto sono in `SPECIFICHE.md`; qui vanno quelle prese durante lo sviluppo.

## 2026-10-11 — Fase 0

| # | Decisione | Perché |
|---|-----------|--------|
| D1 | Python 3.14 (già installato) invece di installare 3.12 | Le specifiche chiedono 3.12+. Verificato che tutte le librerie previste (FastAPI, SQLAlchemy, numpy, scipy, scikit-learn, LightGBM, pandas) hanno pacchetti pronti per 3.14 su Windows. |
| D2 | Un solo repository con `backend/` e `frontend/` | Un solo posto per codice, documenti e commit; più semplice per un progetto personale. |
| D3 | Repository GitHub privato `giuseppecorso/archiebet` | Backup del lavoro; privato per il principio 6 (uso privato). |
| D4 | Login con cookie di sessione salvata nel database (non JWT) | Il cookie HttpOnly non è leggibile da JavaScript (più sicuro) e viene mandato in automatico anche dagli aggiornamenti live SSE. Sessione nel DB = si può chiudere da remoto. |
| D5 | Password con hash Argon2 tramite la libreria `pwdlib` | Argon2 è lo standard attuale raccomandato per le password; `pwdlib` è la libreria consigliata dalla documentazione FastAPI. |
| D6 | Migrazioni del database con Alembic | Ogni modifica alle tabelle è versionata: i dati personali non si perdono e il passaggio a PostgreSQL resta una configurazione. |
| D7 | Configurazione con `pydantic-settings` letta da `.env` | Nessun valore fisso nel codice (sezione 14.6); i valori vengono controllati all'avvio. |
| D8 | Utenti creati da riga di comando (`python -m app.cli create-user`) | Nessuna pagina di registrazione aperta: per ora l'utente è uno solo. |
| D9 | Font caricati da Google Fonts (Doto, Bebas Neue, Barlow) come nei mockup | Nessuna libreria in più; si potranno ospitare in locale quando si va online. |
