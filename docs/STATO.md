# ArchieBet — Stato del progetto

Ultimo aggiornamento: 2026-10-11

## Fase attuale: 0 – Setup (quasi conclusa)

Criterio di fine fase: l'app si apre con il menu delle sezioni. → **Verificato** con utente di prova (login, menu, 5 sezioni, desktop e telefono).

- [x] Controllo programmi sul PC: Python 3.14.2, Node 24.21, npm 11.19, Git 2.52, GitHub CLI 2.102 (loggato), Docker 29.8, Angular CLI 22.1.8
- [x] Repository Git, `.gitignore`, `.gitattributes`, documenti STATO / DECISIONI / IDEE
- [~] Repository GitHub privato creato (`giuseppecorso/archiebet`), **push bloccato**: i primi 2 commit hanno l'email Gmail e GitHub li rifiuta (protezione privacy email). Da decidere con Giuse come sistemarli.
- [x] Backend: FastAPI, SQLAlchemy + Alembic, login con cookie di sessione, config da `.env`, adapter base con cache, gateway AI con tetto di spesa, registro consumi — 17 test verdi
- [x] Frontend: Angular 22 in stile tabellone LED, login, menu delle sezioni, pagine provvisorie — 3 test verdi, build pulita
- [ ] Giuse crea il suo utente e prova l'app (istruzioni nel README)

## Cosa c'è

| Parte | Dove | Note |
|-------|------|------|
| API | `backend/app/` | `/api/health`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me` |
| Tabelle | `users`, `user_sessions`, `usage_events` | migrazione `157fb30e21e8` |
| Pagine | `/login`, `/partite`, `/schedine`, `/statistiche`, `/gioca`, `/impostazioni` | le sezioni sono segnaposto con la fase in cui arrivano |

## Rimandato (consapevolmente)

- Pagina di amministrazione del registro consumi (sezione 14.7): il registro esiste già nel DB; la pagina arriva quando ci saranno consumi da mostrare (Fase 1, con la prima fonte dati).
- Limite ai tentativi di login: non serve finché l'app gira solo sul PC; obbligatorio prima di andare online.

## Prossimo passo: Fase 1 – Partite

Dati Serie A, B e C (storico e calendario), elenco partite con filtri, pagina partita con statistiche vere.
Prima decisione da prendere: fonti per storico (football-data.co.uk) e calendario Serie C (API-Football, piano gratuito → serve creare l'account e la chiave).
