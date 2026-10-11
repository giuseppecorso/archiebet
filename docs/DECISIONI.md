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
| D10 | Per i test del backend `httpx2` invece di `httpx` | Lo chiede Starlette stessa (avviso di deprecazione nella versione installata). |
| D11 | Email dei commit: la Gmail di Giuse (`giuseppecorso91@gmail.com`) | Scelta di Giuse. Ha tolto su GitHub il blocco dei push che espongono l'email; i commit fatti con l'indirizzo anonimo sono stati riportati alla Gmail prima del primo push. |
| D12 | Frontend Angular 22 zoneless, componenti standalone, test con Vitest | Sono i valori predefiniti attuali di Angular CLI: meno codice e meno dipendenze. |
| D13 | Il frontend chiama il backend tramite proxy (`/api` → porta 8000) | Stessa origine per il browser: il cookie di login funziona senza configurare CORS. |
| D14 | Porta fissa del frontend: 4280 (in `angular.json`) | Gli altri progetti Angular di Giuse usano la 4200: così non si scontrano. |
| D15 | Comando `set-password` per cambiare la password da terminale | Recupero semplice se la password si dimentica; chiude anche le sessioni aperte. |

## 2026-10-11 — Fase 1 (decise da Claude su mandato di Giuse: "scegli tu quasi tutto")

| # | Decisione | Perché |
|---|-----------|--------|
| D16 | Storico Serie A e B da football-data.co.uk dal 2005/06 | Gratis, senza account; 20 stagioni bastano per modello e backtest walk-forward. Formato verificato sui file reali. |
| D17 | Orari di football-data trattati come ora di Londra, salvati in UTC, mostrati in ora italiana | Verificato: Napoli–Frosinone delle 20:45 italiane risulta 19:45 nel file. |
| D18 | Quote salvate in formato "lungo" (una riga per partita × bookmaker × mercato × esito × apertura/chiusura) | Aggiungere bookmaker o mercati (OddsPapi in Fase 4) non cambia le tabelle. Salvati: Pinnacle, bet365, Betfair Exchange, massimo e media di mercato; mercati 1X2 e Over/Under 2.5. |
| D19 | Anagrafica squadre unica + tabella dei nomi per fonte (`team_aliases`) | Fonti diverse chiamano le squadre in modo diverso; così si uniscono senza doppioni. |
| D20 | Statistiche come funzioni pure con parametro `before` = calcio d'inizio | Principio 3: nessun dato dal futuro, nemmeno nelle schermate. Testate con valori calcolati a mano. |
| D21 | Classifica: punti → classifica avulsa (punti e differenza reti negli scontri diretti) → differenza reti → gol fatti | Regola dei campionati italiani. Penalizzazioni non gestite finché non avremo i dati (Serie C). |
| D22 | Aggiornamento automatico con APScheduler ogni 6 ore dentro il backend | Già previsto nello stack; niente servizi esterni. Stagioni concluse in cache per sempre: si scarica solo la stagione in corso. |
| D23 | Client HTTP `httpx2` e `tzdata` per i fusi orari su Windows | `httpx2` è il successore ufficiale di httpx (stesso autore, organizzazione Pydantic), già richiesto da Starlette. |
| D24 | Frontend: `httpResource` di Angular 22 per caricare i dati | API stabile dalla 22.0; meno codice e stati di caricamento/errore già pronti. |
| D25 | Quote nell'elenco partite: media di mercato (apertura per le prossime, chiusura per le giocate) | È il riferimento più neutro finché non avremo le quote dei bookmaker italiani (Fase 4). |
| D26 | Avviso "Dati incompleti" quando mancano risultati già giocati | Archie non mostra mai numeri incompleti come se fossero completi. |
| D27 | Budget stile per componente portato a 8 kB (avviso) | Le pagine dense di dati superano i 4 kB predefiniti; gli stili comuni delle tabelle sono stati spostati nello stile globale. |

| D28 | API-Football con piano **gratuito** finché tutto è pronto (decisione di Giuse) | Il piano Free dà solo le stagioni 2022-2024; la stagione in corso richiede il piano a pagamento, da attivare quando servono i dati in diretta. |
| D29 | Squadre di API-Football riconosciute dal loro id numerico, non dal nome | API-Football usa il nome attuale anche nelle stagioni vecchie (Monterosi Tuscia → "Guidonia Montecelio 1937"). |
| D30 | Unione delle squadre tra fonti con nomi "ripuliti" + regole esplicite per le rifondazioni (Vicenza, Siena, Carpi) e nomi italiani per le seconde squadre (Atalanta U23, Milan Futuro) | 34 squadre unite automaticamente tra Serie B e C; comando `tidy-teams` per riapplicare le regole. |
| D31 | Salvati stadio, città e giornata; tabella `match_sources` con l'id della partita su ogni fonte | Stadio e città servono per meteo, campi sintetici e distanze di trasferta (focus Serie C); l'id serve per formazioni e live. |
| D32 | Freni su API-Football: 6,5 secondi tra le chiamate, riserva di 10 richieste al giorno, errori mai salvati in cache | Rispetta i limiti del piano (10 al minuto, 100 al giorno) anche con l'aggiornamento automatico. |

| D33 | Nuova sezione **Laboratorio** (idea di Giuse): schede Campionati e Squadre subito (Fase 1.5), Strategie in Fase 7 | Serve a studiare i campionati (soprattutto la Serie C) prima di modellarli; perimetro piccolo per non rallentare modello e valore. |
| D34 | Fase 1 chiusa "per il piano gratuito": la stagione in corso arriva con il piano a pagamento di API-Football | Decisione di Giuse: si paga quando tutto è pronto. |

**Scoperte sui dati (da usare in Fase 3-4):**
- football-data aggiorna i risultati della stagione in corso con settimane di ritardo (ultimo aggiornamento al 21/09/2026). Il calendario delle prossime partite invece è fresco. Serve API-Football per risultati recenti e Serie C.
- Pinnacle sparisce a metà 2025/26 (200 partite su 380 in A, 90 in B) e manca nel 2026/27. Betfair Exchange copre ~95% delle partite dal 2024/25. **Da decidere in Fase 3:** riferimento di mercato e CLV per la cassaforte 2025/26 (proposta: Pinnacle dove c'è, altrimenti Betfair Exchange di chiusura).
- Gli xG di football-data esistono solo dal 2026/27.
- API-Football, Serie C: risultati, stadi, giornate, formazioni e classifiche sì; statistiche delle partite (tiri, corner) no. Codici: Serie A 135, Serie B 136, Serie C gironi A/B/C 138/942/943.
- La stagione 2025/26 della Serie C (cassaforte) non è nel piano gratuito: servirà il piano a pagamento almeno per un mese prima del verdetto.
