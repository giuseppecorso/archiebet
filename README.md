# ArchieBet

*Give me the odds, I'll move the world.*

Esperto personale di pronostici sul calcio: stima le probabilità, le confronta con le quote e cerca il valore. Uso privato.

- Specifiche: [docs/SPECIFICHE.md](docs/SPECIFICHE.md)
- Stato del lavoro: [docs/STATO.md](docs/STATO.md)
- Decisioni: [docs/DECISIONI.md](docs/DECISIONI.md)

## Avviare l'app

**Il modo semplice:** doppio clic sull'icona **Avvia ArchieBet** sul Desktop (o su `avvia-archiebet.bat`).
Si aprono due finestre ridotte a icona (backend e frontend: non chiuderle) e il browser su http://localhost:4280.
Per spegnere: **Spegni ArchieBet** (o `spegni-archiebet.bat`).

### A mano (PowerShell)

Servono due terminali aperti nella cartella del progetto.

**Terminale 1 – backend**

```powershell
cd backend
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

**Terminale 2 – frontend**

```powershell
cd frontend
npm start
```

Poi apri http://localhost:4280 (porta fissa di ArchieBet, per non scontrarsi con altri progetti Angular sulla 4200).

### Solo la prima volta: crea il tuo utente

```powershell
cd backend
.\.venv\Scripts\python -m app.cli create-user giuse --admin
```

La password (almeno 10 caratteri) non si vede mentre la scrivi: è normale.

Password dimenticata? Dalla cartella `backend`:

```powershell
.\.venv\Scripts\python -m app.cli set-password giuse
```

> In PowerShell i programmi con percorso relativo vanno scritti con `.\` davanti
> (`.\.venv\...`), altrimenti PowerShell risponde "Impossibile caricare il modulo".

Dettagli del backend: [backend/README.md](backend/README.md).
