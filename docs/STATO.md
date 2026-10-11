# ArchieBet — Stato del progetto

Ultimo aggiornamento: 2026-10-11

## Da fare al PC (Giuse)

Le attività manuali sono raccolte qui, da fare tutte insieme quando sei al computer.

Nessuna attività in sospeso. (Account API-Football creato il 2026-10-11, chiave salvata in `backend/.env`.)

## Fase 1 – Partite (in corso)

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

Nota: con il piano gratuito il criterio "calendario Serie C" della Fase 1 resta aperto; tutto il resto della fase è fatto. Proposta: considerare la Fase 1 chiusa "per il piano gratuito" e passare alla Fase 2 (giocate), che non dipende dai dati in diretta.

## Fase 0 – Setup: CONCLUSA (2026-10-11)

App con login e menu delle sezioni; repository GitHub privato `giuseppecorso/archiebet`; frontend su porta fissa 4280, backend su 8000.

## Rimandato (consapevolmente)

- Pagina di amministrazione del registro consumi (sezione 14.7): il registro si sta già riempiendo (ogni download è registrato); la pagina arriva quando ci saranno costi veri (API-Football, AI).
- Limite ai tentativi di login: obbligatorio prima di andare online.
- Penalizzazioni in classifica: con i dati della Serie C.

## Da decidere più avanti

- **Fase 3:** riferimento di mercato per CLV e verdetto sulla cassaforte 2025/26, visto che Pinnacle copre solo metà di quella stagione (dettagli in DECISIONI.md).
