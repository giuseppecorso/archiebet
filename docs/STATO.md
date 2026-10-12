# ArchieBet — Stato del progetto

Ultimo aggiornamento: 2026-10-12

## Fase 1.5 – Laboratorio (base): CONCLUSA (2026-10-12)

- [x] Numeri di campionato calcolati e testati: 1/X/2, gol (casa/fuori), Over 2.5, Goal, 0-0, punti a partita in casa e fuori
- [x] Scheda **Campionati**: campionato + stagione → numeri sul tabellone, classifica finale, andamento in tutte le stagioni
- [x] Scheda **Squadre**: ricerca, storia stagione per stagione tra A, B e C, partite di ogni stagione
- [x] Stagioni "in corso" solo se hanno partite ancora da giocare; le annullate (es. Taranto e Turris 2024/25) sono segnalate a parte
- Test: 78 backend + 6 frontend, tutti verdi.

## Fase 2 – Giocate: CONCLUSA (2026-10-12)

- [x] Tabelle per utente: schedine, selezioni, fotografia al momento della giocata, impostazioni
- [x] Registra una giocata (reale o simulata): partite in programma, mercati 1X2 / doppia chance / Under-Over 2.5 / Goal-NoGoal, quote precompilate dalla media di mercato, anteprima di quota e vincita
- [x] Pulsante "Gioca questa partita" nella pagina partita
- [x] Chiusura automatica dopo ogni aggiornamento dati (e all'apertura delle schedine); partite annullate = rimborso
- [x] CLV per selezione rispetto alla quota giusta di chiusura (Serie A e B)
- [x] Le mie schedine (elenco + dettaglio), Le mie statistiche (prima versione), Impostazioni
- [x] Limiti: solo avvisi sulle giocate reali (D39)
- [x] "Dove vinci e dove perdi": per schedina (numero di partite, bookmaker) e per selezione (mercato, campionato, con rendimento "come singole" e CLV)
- [x] "Le tue abitudini": puntata e quota medie, % multiple, mercato e bookmaker preferiti, squadre più giocate
- Rimandati alle fasi giuste: "Tu contro Archie" (serve il modello, Fasi 3-4); stile di gioco e regolamento personale scritti da Archie (AI, Fase 6)

Test: 129 backend + 11 frontend, tutti verdi.

## Fase 3 – Modello: IN CORSO

- [x] Dixon-Coles (risultati esatti) con correzione dei punteggi bassi, pesi nel tempo, ridge; gradiente esatto verificato
- [x] Mercati dalla matrice dei risultati: 1X2, doppia chance, Under/Over 0.5-4.5, Goal/NoGoal; quota giusta e valore
- [x] Rating Elo su A, B e C collegate da promozioni/retrocessioni (anche le matricole hanno un rating)
- [x] Backtest walk-forward (ristima settimanale, solo partite precedenti) con log loss, Brier, RPS, calibrazione e confronto col mercato di chiusura: `python -m app.cli backtest` (dalla cartella `backend`)
- [x] Cassaforte 2025/26 (e successive) bloccata nel codice; si apre solo con `python -m app.cli open-vault`
- [x] Prova del nove con confronto a coppie: **Elo come punto di partenza superata** (D51), ora nel modello
- [x] CLV delle giocate di valore (bet365 apertura contro chiusura Pinnacle/Betfair, D52)
- [x] Previsioni salvate per ogni partita in programma (tabella `match_predictions`), ricalcolate solo con dati nuovi dopo ogni aggiornamento automatico (anche a mano: `python -m app.cli predict`)
- [x] Pagina partita: "Probabilità di Archie · in prova" (1/X/2 con quota giusta e mercato a confronto) e "Tutti i mercati"
- [ ] Altri fattori alla prova del nove (fattore campo per categoria, stagioni anomale, ecc.)

**Dove siamo:** il modello è ben calibrato (errore 1-2%) ma in A e B non batte il mercato (log loss 1,030 contro 1,008; CLV come giocare a caso). Dettagli in DECISIONI.md dopo D52.

Test: 185 backend + 12 frontend.

Avvio: icone **Avvia ArchieBet** / **Spegni ArchieBet** sul Desktop (file `avvia-archiebet.bat` / `spegni-archiebet.bat`).

## Da fare al PC (Giuse)

Le attività manuali sono raccolte qui, da fare tutte insieme quando sei al computer.

Nessuna attività in sospeso. (Account API-Football creato il 2026-10-11, chiave salvata in `backend/.env`.)

## Fase 1 – Partite: CONCLUSA per il piano gratuito (2026-10-11)

Criterio di fine fase: dati Serie A, B e C (storico e calendario), elenco partite con filtri, pagina partita con statistiche vere.

- [x] Tabelle per partita: campionati, squadre con nomi per fonte, partite con statistiche e xG, quote (apertura e chiusura)
- [x] Import football-data: Serie A e B dal 2005/06 → 17.108 partite, 412.190 quote (25 secondi la prima volta)
- [x] Statistiche calcolate dal codice e testate: forma, medie stagione e casa/trasferta, scontri diretti, classifica con avulsa — sempre "al calcio d'inizio"
- [x] API: elenco partite (prossime / risultati, filtro campionati), dettaglio partita
- [x] Aggiornamento automatico ogni 6 ore mentre il backend è acceso (anche a mano: `python -m app.cli sync`)
- [x] Dashboard: filtri Serie A/B, schede Tutte / Prossime / Risultati (Live in Fase 5), quote medie, stato "Risultato in arrivo"
- [x] Pagina partita: forma (V verde, N ambra, P rossa), statistiche a confronto, classifica, precedenti, ultime partite, quote apertura → chiusura, statistiche della partita, avviso "Dati incompleti"
- [x] API-Football collegato (piano gratuito): storico Serie C 2022/23-2024/25, 3 gironi → 3.420 partite con stadi e giornate
- [x] Squadre unite tra le due fonti (34 automaticamente, 3 rifondazioni a mano), nomi italiani per le seconde squadre
- [x] Serie C nella dashboard (filtri per girone) e nella pagina partita
- [ ] **Stagione in corso di Serie C e risultati aggiornati di A e B**: arrivano con il piano a pagamento di API-Football, da attivare quando tutto è pronto (decisione di Giuse). Basterà aggiungere `2025,2026` a `API_FOOTBALL_SEASONS` e `135,136` a `API_FOOTBALL_LEAGUES` in `backend/.env`.

Test: 66 backend + 6 frontend, tutti verdi.

Il criterio "calendario Serie C in corso" si completa attivando il piano a pagamento (vedi sopra); Giuse ha deciso di farlo quando tutto sarà pronto.

## Fase 0 – Setup: CONCLUSA (2026-10-11)

App con login e menu delle sezioni; repository GitHub privato `giuseppecorso/archiebet`; frontend su porta fissa 4280, backend su 8000.

## Rimandato (consapevolmente)

- Pagina di amministrazione del registro consumi (sezione 14.7): il registro si sta già riempiendo (ogni download è registrato); la pagina arriva quando ci saranno costi veri (API-Football, AI).
- Limite ai tentativi di login: obbligatorio prima di andare online.
- Penalizzazioni in classifica: con i dati della Serie C.

## Da decidere più avanti

Niente in sospeso (riferimento di mercato deciso: D48).
