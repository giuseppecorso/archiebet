# ArchieBet — Stato del progetto

Ultimo aggiornamento: 2026-10-21

## Fase 8 – Coppe, altri campionati, formazioni, piano live: CONCLUSA (2026-10-21)

- [x] Coppe europee già attive da D85 (calendario, risultati, quote).
- [x] **Altri campionati** (D106): prova sulle 23 serie minori con l'archivio finora scaricato (2.009 partite): **non passa** (Occasioni con CLV −1/−3%); restano fuori dalle Occasioni. Da ripetere con `minor-test` quando l'archivio è completo.
- [x] **Formazioni** nella pagina partita (D123): previste = ultima formazione senza gli assenti delle notizie (provato su 2.700 formazioni: 8 titolari su 11, meglio del metodo pesato); ufficiali da API-Football circa un'ora prima (Serie A e B).
- [x] **Piano partita live** (D124, sperimentale): per 11 situazioni tipiche quota giusta e quota minima da giocare (soglia D72), stesso motore del termometro.
- Test: 418 backend + 24 frontend, tutti verdi.

## Fase 7 – Apprendimento: CONCLUSA (2026-10-21)

Rivista con Giuse (D117): le strategie le trova Archie da solo; tolti il Laboratorio strategie (regole scritte a mano) e il fiuto come fattore.
- [x] **Archie cerca le strategie** (D118, `strategy-search`): 1.650 strategie su ~205.000 giocate possibili (bet365 d'apertura contro Pinnacle di chiusura), taratura 2012/13–2019/20, conferma dal 2020/21. **Nessuna passa**; le Occasioni restano sulla regola D72. Se un giorno una passa, entra da sola nelle Occasioni con l'etichetta "strategia di Archie" (`radar_signals.strategy`, API e lavoro radar).
- [x] **Quando giocare** (D119, `timing-test`): sulle quote ora per ora di Sisal ed Eurobet (archivio OddsPapi, ~3.700 partite) l'orario sposta meno di mezzo punto di CLV: è indifferente. Il margine pesa 7-10%.
- [x] **Autocorrezione** (D120): controllo settimanale della taratura sulle 2.000 partite più recenti per gruppo e mercato; una fascia fuori fa partire una prova, non una correzione. Prima segnalazione (Over 2.5 in A e B sotto il 40%) provata su dati indipendenti (D122): era caso.
- [x] **Partite gemelle** nella pagina partita e **mappa del valore** (D121).
- [x] Scheda **Laboratorio · Cosa impara Archie** con tutti i risultati; lavoro settimanale "learning" (`learning-refresh`) che rifà le prove da solo; archivio quote settimanale esteso a A, B ed estero (13 richieste a settimana).
- [x] Simulatore: elenco a tendina leggibile, partite per campionato, spiegazione "a cosa serve". Quote 1X2 nelle righe delle partite in arrivo (media dei bookmaker italiani).
- Nota dati: football-data non dà più Pinnacle da metà 2025/26; le prove storiche crescono ora con l'archivio OddsPapi.
- [ ] **Serie minori** (D106): archivio in corso (`odds-archive --minor`); poi risultati da API-Football e prova. Già si vede che Sisal ed Eurobet hanno ~10% di margine nelle serie minori (D119).
- Test: 406 backend + 24 frontend, tutti verdi.

## Battere il mercato in Serie C + Claude API (2026-10-21)

- [x] **Claude API attiva** (D97): Sonnet 5.5, chiave nel `.env` (`ANTHROPIC_API_KEY`), tetto 10 €/mese (`ai_monthly_budget_eur`, gateway AI della Fase 0, D103), credito prepagato 5 $ senza ricarica. Chiamata di prova riuscita. Il modulo `app/ai` e il controllo della spesa nel codice sono ancora da scrivere (Fase 6).
- [x] **Prova D98** (`seriec-edge`, 374 partite di Serie C): il consenso dei bookmaker italiani in chiusura è più preciso dell'apertura (il mercato impara in settimana) e non si batte con formazioni, Archie, ricalibrazione o quote fuori linea.
- [x] **Prova D99**: Archie non aggiunge niente nemmeno in apertura; le quote "sopra Archie" hanno CLV −6/−7% → etichetta tolta (D100).
- [x] Archivio settimanale delle quote di Serie C (`archive_job`): la prova D98 si ripete a fine stagione con più partite.
- [x] **Archie tifoso** (D101-D103): notizie della Serie C ogni 2 ore (TuttoC.com + Google News per chi gioca nei 3 giorni), fatti estratti con Haiku 5.5, giudizio sulla partita con Opus 5.5, consenso dei bookmaker salvato a ogni giudizio e in chiusura; riquadro "Cosa sa il tifoso" (in prova) nella pagina partita; stato della prova in `/api/fan/test`. Costo misurato ~3 $/mese. Prova D101: verdetto a 150 segnali (spostamento delle quote verso il lato indicato).
- [x] **Archie tifoso su Serie A, B e C** (D105): Google News mirata per chi gioca nei 7 giorni; giudizi solo con le quote (D104); prove separate C (D101) e A-B.
- [x] **Pagina partita completa** (D107-D111): due pronostici (il più sicuro e il più spinto), analisi scritta da Opus su richiesta (~0,025 €), tiri/angoli/cartellini attesi con quote giuste (modello D108-D109) e confronto con le quote dei bookmaker, tiri dei giocatori con quote giuste e assenti dalle notizie (modello D110, verificato e calibrato).
- [x] Prova stili D108: gli incastri di stile non aggiungono niente al modello "fatti × subiti".
- [x] **Fase 6 – AI e Gioca: CONCLUSA (2026-10-21)**: Chiedi ad Archie con strumenti sui dati (D112), sfortuna o errore? (D113), regolamento personale con suggerimenti e stile di gioco (D114), simulatore partita con "E se..." (D115), sfida contro Archie a crediti finti (D116), notizie (D101-D105). Icona unica "ArchieBet (avvia o riavvia)".
- [ ] **Serie minori di tutto il mondo** (D106): archivio quote di 23 campionati in corso (`odds-archive --minor`), poi risultati da API-Football e prova.
- [ ] Da verificare dopo il riavvio: quote italiane collegate alle partite di Serie C (l'app accesa usava ancora il codice vecchio) e primi giudizi con il consenso registrato.
- [ ] Poi: "Chiedi ad Archie" e il resto della Fase 6; Blocco 4 (valutazione dei giocatori) solo se servirà.
- Test: 353 backend + 22 frontend, tutti verdi.

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

## Prossima sessione: API-Football Pro e Fase 5

Deciso con Giuse il 2026-10-18: **piano Pro (19 $/mese, 7.500 richieste/giorno, mensile)**, da attivare all'inizio della prossima sessione (Giuse lo compra dalla dashboard, Claude verifica con `/status` che è gratuito). Il Pro basta: i piani cambiano solo il numero di richieste; stima di punta ~1.100/giorno.

Blocchi, in ordine (Giuse interessato anche ai **mercati secondari** cartellini/angoli, vedi IDEE 2026-10-20):
1. ~~Risultati aggiornati~~ fatto il 2026-10-20 (D80): Pro attivo fino al 2026-11-20; tutti i campionati per la stagione in corso + Serie C 2025/26, nessun doppione (prova su copia). Meteo e shock climatico: non passano (D81).
2. ~~Seconde divisioni~~ fatte il 2026-10-20 (D75). ~~Coppe europee~~ fatte il 2026-10-20 (D85).
   Fatti anche il 2026-10-20: multipla con Domani / 2-3 giorni / date scelte (D83); grafica più viva con stemmi, loghi, bandiere, luci da stadio, barra Dati che scorre (D84); aggiornamento più veloce e robusto (football-data salta le stagioni concluse, OddsPapi non si blocca su 404, 429 e timeout, cache degli storici ripulita dopo 2 giorni).
   **Mercati secondari: fatti il 2026-10-21 (D82 → D94).** Prova sullo storico superata da angoli e cartellini; ora nella simulazione dal vivo del radar con conteggio separato e etichetta "in prova" nelle Occasioni. Serie C: il modello di Archie perde contro la media di Sisal/Eurobet/Snai (D95, 374 partite): in Serie C la stima migliore è ora quella media, con l'etichetta "sopra la media" (D96). Da ripetere a fine stagione.
3. **Fattori con API-Football Pro: fatti il 2026-10-20 (D89 → D91: nessuno passa; nuovo allenatore passa la taratura ma non la conferma).** Storico in cache (`python -m app.cli af-history`, `d89-test`).
   Vecchia nota: Gruppo di prove D78 (taratura fino al 2024/25 + conferma 2025/26): (6) "tifo" dei bookmaker provato, non confermato (D79: bet365 tiene più margine su entrambe le squadre nelle partite delle big); (3) shock climatico dell'ospite in corso (`python -m app.cli weather-test --patient`, sulla copia del DB: scarica il meteo grezzo in `data/cache/weather/raw.json` aspettando i limiti di Open-Meteo, poi prova D76 completo e D78). Prima di usarlo sul DB vero serve l'avvio di ArchieBet (migrazione stadi) e `python -m app.cli venues`.
   Fattori della sezione 8 con prova del nove: ~~meteo~~ provato il 2026-10-20, non passa (D77; completare il download con `python -m app.cli weather-test` e ripetere); infortuni e squalifiche, formazioni ufficiali, allenatori, stanchezza da coppe e viaggi, campi sintetici. Storico formazioni/infortuni: ~10-15 mila richieste, ~2 giorni in sottofondo. Livello high.
4. **Fase 5 – Live: fatta il 2026-10-21 (D92-D93).** Tabella `match_live` (migrazione fd842ab9d186, applicata all'avvio), lavoro ogni minuto solo con partite in corso (`/fixtures?live=`), risultato finale e schedine chiuse a fine partita; termometro della speranza (Poisson dai gol attesi del mercato, verificato all'intervallo su 5 stagioni, `python -m app.cli live-check`); scheda **Live** in dashboard, minuto e punteggio in ambra, termometro e "Segui live" (ogni 30 s) nelle schedine. Effetto del punteggio (D93) provato: migliora la calibrazione ma non passa la conferma, da riprovare a fine 2026/27.
   Pagina partita con minuto, punteggio e probabilità 1X2 di adesso (aggiornata ogni 30 s). Il termometro della Multipla del giorno si vede registrandola come schedina (reale o simulata): la multipla proposta si ricalcola solo con partite non iniziate.

La simulazione dal vivo del radar (D59, 300 giocate) continua da sola a ogni aggiornamento, con la regola D72/D73 dal 2026-10-18 (Shin, quota ≤ 4, soglia che cresce con la quota), misurata su 8 bookmaker italiani (D74); a Giuse si mostrano solo le occasioni su Sisal ed Eurobet. Ripartita da zero.

## Fase 4 – Pronostici e valore: CONCLUSA (2026-10-15)

- [x] Modello uscito dalla prova (D59): tolta l'etichetta "in prova" dalla pagina partita, resta la nota sul mercato più preciso
- [x] Motore del radar (`app/forecast/radar.py`): probabilità giusta Pinnacle/Betfair contro la quota migliore giocabile, segnali ≥ 2%, "sospetto" sopra il 15%
- [x] **Simulazione dal vivo partita** (D60): tabella `radar_signals`, segnali rilevati prima del calcio d'inizio a ogni aggiornamento, CLV con la chiusura; per ora bookmaker giocabile = bet365 (quote football-data)
- [x] Piani quote verificati (D61): OddsPapi gratuito come primo passo
- [x] Account gratuito OddsPapi creato da Giuse, chiave in `backend/.env` (`ODDSPAPI_KEY`): piano free, 250 richieste/mese, **348 bookmaker inclusi**, tra cui Pinnacle, Betfair Exchange e i principali italiani (sisal.it, snai.it, eurobet.it, goldbet.it, lottomatica.it, bet365.it, betflag.it, planetwin365.it, ...)
- [x] Adapter OddsPapi (`app/adapters/oddspapi.py`) e import (`app/ingest/oddspapi.py`) nell'aggiornamento automatico (D62): Pinnacle + 9 bookmaker italiani, chiusura Pinnacle dallo storico gratuito, riserva mensile; radar solo su Sisal ed Eurobet, dove Giuse ha un conto (D66). Provato dal vivo su una copia del DB: 2 richieste, 30 partite trovate, nessuna ancora nel nostro calendario (football-data arriva fino al 12/10)
- [x] Pagina **Radar** nel menu (`/radar`, API `/api/radar`): segnali sulle prossime partite con dove giocarla, quota giusta, valore, "sospetto" sopra il 15%, quota di adesso; ultimi segnali con CLV; riepilogo della simulazione verso le 300 giocate
- [x] **Campionati maggiori europei** (D64-D65): Premier League, LaLiga, Bundesliga, Ligue 1 con storico dal 2005/06 (football-data, ~30.000 partite, prima importazione ~1 minuto), quote OddsPapi, tendina dei paesi in dashboard. Modello solo italiano; modelli esteri e coppe in Fase 8
- [x] **Pronostici** (D67, menu "Pronostici", API `/api/picks`): per ogni partita dei prossimi 7 giorni la stima migliore (Pinnacle → Betfair → media mercato → modello di Archie), pronostico secco, quote di Sisal ed Eurobet con etichetta valore / nella norma / paga poco, altri mercati (doppia chance, Under/Over 2.5). Il radar è diventato la scheda **Occasioni** della stessa pagina (/radar porta lì)
- [x] **Multipla del giorno** in dashboard (D68, API `/api/picks/multiple`): una per Sisal e una per Eurobet, Oggi / Settimana, prima con valore, altrimenti nella norma dichiarata; quota, vincita, 1 volta su N, vivo all'ultima, valore atteso
- [x] Mercati doppia chance e Goal/NoGoal da OddsPapi (pronostici, multipla, radar per il Goal/NoGoal)
- [x] Generatore "Archie, fammi una multipla" (D69): scheda "Fammi una multipla" in Pronostici, profili tranquilla/equilibrata/coraggiosa, 2–6 partite, mercati, campionati, importo
- [x] **Io contro Archie** (Le mie statistiche, API `/api/bets/versus`): con le probabilità che Archie aveva al momento della giocata (fotografia), il tuo fiuto (vinte − attese ± errore) e il rendimento quando Archie era d'accordo o contrario
- [x] **Quote fuori linea oggi** in dashboard (D70, API `/api/picks/off-line`): quote di Sisal ed Eurobet ≥ 8% sopra il giusto, "sospetta" sopra il 15% con l'avviso sugli errori palesi
- [x] Il CLV delle occasioni si misura subito dopo il calcio d'inizio (quota di chiusura), senza aspettare il risultato di football-data
- In prova (continua da solo): radar / Occasioni fino a 300 giocate misurate (D59)
- Tolto: "Dove conviene giocarla" (D67)

Test: 274 backend + 17 frontend.

## Fase 3 – Modello: CONCLUSA (2026-10-12)

- [x] Dixon-Coles (risultati esatti) con correzione dei punteggi bassi, pesi nel tempo, ridge; gradiente esatto verificato
- [x] Mercati dalla matrice dei risultati: 1X2, doppia chance, Under/Over 0.5-4.5, Goal/NoGoal; quota giusta e valore
- [x] Rating Elo su A, B e C collegate da promozioni/retrocessioni (anche le matricole hanno un rating)
- [x] Backtest walk-forward (ristima settimanale, solo partite precedenti) con log loss, Brier, RPS, calibrazione e confronto col mercato di chiusura: `python -m app.cli backtest` (dalla cartella `backend`)
- [x] Cassaforte 2025/26 (e successive) bloccata nel codice; si apre solo con `python -m app.cli open-vault`
- [x] Prova del nove con confronto a coppie: **Elo come punto di partenza superata** (D51), ora nel modello
- [x] CLV delle giocate di valore (bet365 apertura contro chiusura Pinnacle/Betfair, D52)
- [x] Previsioni salvate per ogni partita in programma (tabella `match_predictions`), ricalcolate solo con dati nuovi dopo ogni aggiornamento automatico (anche a mano: `python -m app.cli predict`)
- [x] Pagina partita: "Probabilità di Archie · in prova" (1/X/2 con quota giusta e mercato a confronto) e "Tutti i mercati"
- [x] Stato dei dati nella dashboard: aggiornamento di ogni fonte, risultati fino al…, previsioni; pulsante **Aggiorna ora**
- [x] Prova del nove contro il mercato (`python -m app.cli factor-test`): riposo, motivazione e modello non battono l'apertura Pinnacle (D56)
- [x] **Radar confermato** come motore in A e B: CLV +3,2% (bet365) e +4,1% (quota migliore), positivo quasi in ogni stagione (D57)
- [x] Comando del verdetto con criteri fissati in anticipo (D58): `python -m app.cli verdict`, funziona solo a cassaforte aperta
- [x] **Verdetto sulla cassaforte 2025/26** (aperta da Giuse il 2026-10-12): modello SUPERATO (calibrazione 2,9%, distanza dal mercato +0,026), radar NON superato per campione troppo piccolo (45 giocate, CLV +2,4% ± 3,1%) → resta in prova fino alla verifica dal vivo in Fase 4 (D59)

**Dove siamo:** il modello è ben calibrato (errore 1-2%) ma in A e B non batte il mercato; il valore misurato sta nel radar (quote dei bookmaker contro la quota giusta di Pinnacle). Fattori "da esperto" (formazioni, assenze, notizie) da provare quando avremo lo storico di API-Football a pagamento.

Test: 202 backend + 13 frontend.

Avvio: icone **Avvia ArchieBet** / **Spegni ArchieBet** sul Desktop (file `avvia-archiebet.bat` / `spegni-archiebet.bat`). Icone LED e collegamenti su Desktop e menu Start si ricreano con `powershell -ExecutionPolicy Bypass -File tools\crea-icone.ps1`.

## Da fare al PC (Giuse)

Le attività manuali sono raccolte qui, da fare tutte insieme quando sei al computer.

Nessuna attività in sospeso.

(La Serie C 2025/26 si valuterà con il piano a pagamento di API-Football.)

(Account API-Football creato il 2026-10-11, chiave salvata in `backend/.env`.)

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
