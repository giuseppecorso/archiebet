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


## 2026-10-12 — Fase 1.5 Laboratorio

| # | Decisione | Perché |
|---|-----------|--------|
| D35 | In ArchieBet commit e push li fa Claude (vale la regola del progetto, non quella personale "solo se chiedo") | Scelta di Giuse. |
| D36 | API del Laboratorio sotto `/api/lab/...`; stagioni negli indirizzi come "2024-25" | La barra di "2024/25" non va bene in un URL. |
| D37 | Stagione "in corso" = ha partite in programma o rinviate; le annullate si contano a parte | Le esclusioni (Taranto, Turris 2024/25) facevano sembrare in corso stagioni finite. |
| D38 | Funzioni condivise tra API rese pubbliche (`match_cards`, `competition_out`, `to_result`) | Non importare funzioni "private" (con `_`) da altri moduli. |

| D39 | Limiti di gioco: **nessun blocco**, solo avvisi quando le giocate REALI superano il budget settimanale/mensile impostato a mano; le simulate non contano | Decisione di Giuse (2026-10-12): l'uso è soprattutto virtuale. Principio 7 rispettato nella forma "limiti impostabili + avviso". |
| D40 | Caratteri ridotti del 10-20% in tutta l'app (testo base 14 px); testi piccoli (11-13 px) invariati per leggibilità | Richiesta di Giuse: l'app sembrava "enorme". |
| D41 | "Mostra tutte / Mostra meno" (componente ShowMore) per tutte le liste lunghe, stato tenuto in un signal del componente | I riferimenti nel template dichiarati dopo l'uso rompevano il primo disegno della pagina. |


## 2026-10-12 — Fase 2 Giocate

| # | Decisione | Perché |
|---|-----------|--------|
| D42 | Giocate registrabili solo PRIMA del calcio d'inizio; una selezione per partita | Niente dati dal futuro (principio 3); la correlazione tra mercati della stessa partita non è ancora calcolata. |
| D43 | CLV = quota presa / quota giusta di chiusura − 1; quota giusta = media di mercato di chiusura senza margine (metodo proporzionale); doppia chance ricavata dall'1X2 | Metodo standard; Goal/NoGoal senza CLV finché non avremo quelle quote. |
| D44 | Fotografia = il dettaglio partita completo (statistiche, classifica, quote) salvato in JSON al momento della giocata | Base dell'autopsia "sfortuna o errore?" (Fase 6) senza rischio di guardare dati successivi. |
| D45 | Cancellazione di una schedina solo se aperta e prima del primo calcio d'inizio | Serve a correggere errori di inserimento, non a cancellare le perdite. |
| D46 | Anteprima di quota e vincita nel frontend con lo stesso arrotondamento del backend (per eccesso dal 5), con test identici sui due lati | Trovato un caso (49,445 €) in cui la virgola mobile dava 49,44 invece di 49,45. |
| D47 | Avvio con file .bat e icone sul Desktop | Richiesta di Giuse: un "pulsante di accensione" senza aprire terminali. |

| D48 | Riferimento di mercato per CLV e verdetto: chiusura **Pinnacle** dove c'è, altrimenti **Betfair Exchange** di chiusura (opzione A) | Scelta di Giuse: Pinnacle copre solo metà della cassaforte 2025/26, Betfair Exchange ~95% ed è un mercato "intelligente". |

**Scoperte sui dati (da usare in Fase 3-4):**
- football-data aggiorna i risultati della stagione in corso con settimane di ritardo (ultimo aggiornamento al 21/09/2026). Il calendario delle prossime partite invece è fresco. Serve API-Football per risultati recenti e Serie C.
- Pinnacle sparisce a metà 2025/26 (200 partite su 380 in A, 90 in B) e manca nel 2026/27. Betfair Exchange copre ~95% delle partite dal 2024/25. **Da decidere in Fase 3:** riferimento di mercato e CLV per la cassaforte 2025/26 (proposta: Pinnacle dove c'è, altrimenti Betfair Exchange di chiusura).
- Gli xG di football-data esistono solo dal 2026/27.
- API-Football, Serie C: risultati, stadi, giornate, formazioni e classifiche sì; statistiche delle partite (tiri, corner) no. Codici: Serie A 135, Serie B 136, Serie C gironi A/B/C 138/942/943.
- Fattore campo in Serie A crollato nel 2020/21 (stadi vuoti): vittorie fuori al 34%. Da considerare nel modello (stagioni anomale).
- Serie C girone C: pareggi ~29% stabili nelle 3 stagioni; Serie A 2026/27 finora solo 18% (campione piccolo).
- La stagione 2025/26 della Serie C (cassaforte) non è nel piano gratuito: servirà il piano a pagamento almeno per un mese prima del verdetto.


## 2026-10-12 — Fase 3 Modello

| # | Decisione | Perché |
|---|-----------|--------|
| D49 | Un solo Dixon-Coles per A, B e C insieme, ristimato ogni 7 giorni sulle partite degli ultimi 3 anni pesate nel tempo; ridge in "partite equivalenti"; codice in `app/forecast/` (funzioni pure, niente DB) | Promosse e retrocesse collegano le categorie; la ristima settimanale è il walk-forward realistico. |
| D50 | Taratura sul 2016/17-2021/22 (A e B), conferma sul 2022/23-2024/25 mai visto (A, B, C); cassaforte dal 2025/26 bloccata nel codice (`open-vault`); un fattore passa la prova del nove se migliora la log loss a coppie di oltre 2 errori standard | Evita di "imparare a memoria" il periodo su cui ci si giudica (principi 3 e 5). |
| D51 | Elo come punto di partenza del ridge (pendenza stimata dal modello), ξ = 0,002/giorno, ridge = 8 | Prova del nove superata: taratura −0,0026 ± 0,0010, conferma −0,0107 ± 0,0016 (Serie C −0,015/−0,018, Serie B −0,007, Serie A neutro); prevede anche le neopromosse senza storia. |
| D52 | CLV del backtest: giocate con valore ≥ 5% alla quota **bet365 di apertura** (bookmaker presente in Italia), misurate contro la chiusura di riferimento D48; si confronta sempre con "giocare a caso" sulle stesse quote | Il CLV da solo include il margine del bookmaker (~5,5%): conta la differenza rispetto al caso. |

**Primo verdetto del backtest (2022/23-2024/25, Serie A e B, 2026-10-12):** log loss modello 1,030 contro mercato di chiusura 1,008; CLV delle giocate di valore −5,6% contro −5,5% giocando a caso; più alta la soglia, peggiore il CLV. Il modello base non batte i mercati di A e B: il valore va cercato con fattori nuovi (prova del nove) e dove il mercato è più debole (Serie C, che però non ha quote storiche per misurare il CLV).
| D53 | Strategia approvata da Giuse: in A e B la base è la **probabilità di mercato senza margine** (Pinnacle/Betfair), Archie la corregge solo con informazioni che il mercato prezza in ritardo (formazioni, notizie, fattori Serie C), ognuna con prova del nove **contro il mercato**; priorità alla **quota migliore** tra i bookmaker italiani (radar) | Misurato sul 2022/23-2024/25: giocare alla quota migliore vale ~5 punti di CLV (margine 5,8% → 1,1%), il modello mescolato alle quote di apertura le peggiora anche al 10%. Nelle multiple il margine si moltiplica. Dixon-Coles + Elo restano per Serie C, mercati senza quote e statistiche. |
| D54 | L'investimento finale saranno dati di campionati minori (anche meglio della Serie C), ad applicativo finito | Decisione di Giuse: lì il mercato è più debole; prima si costruisce e si misura tutto il resto. |
| D55 | Tutto resta sul PC di Giuse, uso solo personale; niente server finché l'app non è provata | Decisione di Giuse. Archie si aggiorna mentre il PC è acceso e, all'apertura o prima di proporre multiple, riscarica i dati scaduti. Server (VPS) da rivalutare più avanti. |
| D56 | Prova del nove **contro il mercato** (`python -m app.cli factor-test`): base = apertura Pinnacle senza margine ricalibrata stagione per stagione (regressione logistica multinomiale), fattore promosso solo se migliora la log loss oltre 2 errori standard | Applica D53. Risultati 2013/14-2024/25, 9.351 partite di A e B: riposo +0,0003 ± 0,0003, motivazione +0,0001 ± 0,0002, modello Dixon-Coles + Elo −0,0002 ± 0,0001: **nessuno passa**, l'apertura Pinnacle li contiene già. La ricalibrazione da sola migliora l'apertura grezza (−0,0013 ± 0,0006) ma con CLV negativo: si usa solo come base dei test. |
| D57 | **Il radar è il motore di Archie in A e B**: probabilità giusta = Pinnacle senza margine, valore = probabilità × quota del bookmaker − 1 | Misurato sullo stesso periodo: alla quota bet365 di apertura con valore ≥ 2% → CLV +3,15% ± 0,45% (493 giocate, 10 stagioni su 12 positive); ≥ 5% → +5,6% (11/12). Alla quota migliore del mercato ≥ 2% → CLV +4,1% ± 0,2% su 4.308 giocate, 12/12 stagioni positive. Da verificare in Fase 4 sui bookmaker italiani (OddsPapi) e con i limiti dei conti. |
| D58 | **Criteri del verdetto, fissati prima di aprire la cassaforte** (stagione 2025/26, `python -m app.cli verdict`): 1) modello calibrato, errore medio 1/X/2 ≤ 3%; 2) modello a non più di 0,03 di log loss dal mercato di chiusura; 3) radar: CLV delle giocate con valore ≥ 2% alla quota bet365 di apertura (probabilità giusta Pinnacle di apertura, altrimenti Betfair Exchange) positivo oltre 2 errori standard. Se 3 passa, il radar esce dalla prova; il modello resta "in prova" se 1 o 2 non passano. Il 2026/27 resta alla simulazione dal vivo (Fase 4) | Criteri scritti prima di guardare, così non si possono aggiustare dopo (principi 2 e 3). La cassaforte la apre solo Giuse. |

**Verdetto sulla cassaforte 2025/26 (lanciato da Giuse, 2026-10-12), Serie A e B, 760 partite:**
1. Calibrazione 2,9% (≤ 3%) → SUPERATO
2. Distanza dal mercato di chiusura +0,0261 (≤ 0,03) → SUPERATO (modello 1,0139 contro mercato 0,9879)
3. Radar bet365 valore ≥ 2%: CLV +2,38% ± 3,12% su 45 giocate → NON superato (campione troppo piccolo: Pinnacle sparisce a metà stagione)

| # | Decisione | Perché |
|---|-----------|--------|
| D59 | Esito del verdetto applicato senza ritocchi: il **modello esce dalla prova** (le sue probabilità restano accompagnate dalla nota "il mercato è più preciso in A e B"); il **radar resta in prova**. Nuova verifica del radar fissata ora, prima di vedere i dati: simulazione dal vivo in Fase 4 sui bookmaker italiani, si giudica quando ha **almeno 300 giocate** con valore ≥ 2%, stesso criterio (CLV medio positivo oltre 2 errori standard) | Non si spostano i criteri dopo aver visto i risultati (principi 2-3). 45 giocate non bastano per giudicare in nessun senso: l'errore standard (3,1%) è più grande del CLV atteso (~3%). La cassaforte ora è aperta: il 2025/26 non va più usato per tarare. |


## 2026-10-12 — Fase 4 Quote e valore

| # | Decisione | Perché |
|---|-----------|--------|
| D60 | Radar dal vivo già attivo con le quote di football-data (bet365 come bookmaker giocabile, Pinnacle/Betfair Exchange come probabilità giusta). Tabella `radar_signals` per partita: la **prima** rilevazione con valore ≥ 2% prima del calcio d'inizio è la giocata simulata (quota bloccata), poi CLV con la chiusura D48. Bookmaker giocabili in `PLAYABLE_BOOKMAKERS` (`app/forecast/radar.py`): la "quota migliore di mercato" di football-data non conta perché include bookmaker non italiani | La simulazione di D59 parte subito invece di aspettare OddsPapi; prendere la prima quota (e non la migliore vista) evita di scegliere col senno di poi. |
| D61 | Fonte quote italiane: **OddsPapi piano gratuito** come primo passo (250 richieste/mese, storico gratis e non conteggiato, nessuna carta). Prima verifica tramite API: quali bookmaker italiani ci sono davvero (sul sito non sono elencati). Piani a pagamento: prezzo non pubblico (su misura). Piano B: odds-api.io (15 bookmaker IT confermati, ma niente Pinnacle, chiavi gratuite sospese, da 59 €/mese per 2 bookmaker) | Verificato sui siti ufficiali il 2026-10-12. Con 250 richieste: ~1 lettura al giorno di A e B per bookmaker; la chiusura per il CLV si prende dallo storico gratuito. |

**Verifica OddsPapi (2026-10-12, endpoint `/v4/account`):** piano free attivo, 250 richieste/mese, 348 bookmaker inclusi: Pinnacle, Betfair Exchange, sisal.it, snai.it, eurobet.it, goldbet.it, lottomatica.it, bet365.it, betflag.it, planetwin365.it, betsson.it, leovegas.it, pokerstars.it, admiralbet.it, 888sport.it, netbet.it, quigioco.it, eplay24.it, betfair.it. D61 confermata: niente piano B per ora.
| D62 | Uso di OddsPapi nel piano gratuito: **1 richiesta a giro** (`/odds-by-tournaments`, Serie A+B, Pinnacle, cache 5 ore → ~4 al giorno, ~125 al mese) per elenco partite e quota Pinnacle; **quote italiane dallo storico gratuito** (9 bookmaker, 3 per chiamata, 5,5 s di pausa) per le partite dei prossimi 7 giorni già nel nostro calendario; **chiusura Pinnacle** = ultimo prezzo prima del calcio d'inizio, sempre dallo storico. Riserva di 20 richieste al mese mai usata in automatico. OddsPapi non crea partite: si aggancia a quelle di football-data/API-Football (stesso campionato, stesse squadre, ±48 ore) | Verificato dal vivo: la documentazione sbaglia (un solo bookmaker per chiamata, non 3), lo storico non consuma richieste. Così bastano le 250 richieste gratuite e torna Pinnacle in chiusura (in football-data manca dal 2026/27). Niente bookmaker a pagamento (20-30 €/bookmaker secondo Giuse) finché il radar non supera il verdetto delle 300 giocate. |
| D63 | Il radar gioca solo sui **bookmaker italiani** di OddsPapi (Sisal, Snai, Eurobet, Goldbet, Lottomatica, BetFlag, bet365.it, Planetwin365, Betsson); bet365 di football-data resta solo come ripiego per le partite senza quote italiane. A parità di bookmaker, le quote OddsPapi (più fresche) vincono su quelle di football-data | La "quota migliore" deve essere davvero giocabile da Giuse. |
| D64 | **Campionati maggiori europei anticipati dalla Fase 8** (opzione A scelta da Giuse): Premier League, LaLiga, Bundesliga e Ligue 1 da football-data (storico e quote dal 2005/06, calendario) e OddsPapi (quote italiane + Pinnacle) per radar, partite, pagina partita, laboratorio; dashboard con tendina dei paesi. Squadre registrate per paese. Il **modello di Archie resta solo italiano** (`MODEL_COUNTRY`): i modelli esteri e le coppe europee restano in Fase 8 | Il radar non ha bisogno del modello e con 6 campionati arriva molto prima alle 300 giocate (D59). Costo quasi nullo: stessa fonte e stesso formato della Serie A. Le coppe richiedono un calendario da OddsPapi o API-Football a pagamento: si valutano a fine Fase 4 insieme all'idea in IDEE. |
| D65 | OddsPapi con 6 campionati: massimo 5 campionati per richiesta (non documentato) → elenco partite **una volta al giorno** (2 richieste, ~62 al mese); quota Pinnacle presa dallo **storico gratuito** insieme ai 9 italiani (4 chiamate per partita), l'elenco del giorno la completa solo dove manca; quote attuali per le partite dei **prossimi 4 giorni** (giro gratuito sotto i 15 minuti nel weekend) | Resta nel piano gratuito con ampio margine e la quota Pinnacle è fresca a ogni giro. |
| D66 | **Il radar gioca solo su Sisal ed Eurobet**, i bookmaker dove Giuse ha un conto (impostabili in `backend/.env` con `RADAR_BOOKMAKERS`); riferimento Pinnacle (Betfair Exchange di football-data dove manca). Niente più ripiego su bet365. Sostituisce D63 | Proposta di Giuse ("meglio mirato che dispersivo"), corretta nel verso: gli sharp servono a stimare la probabilità, i bookmaker italiani a giocare. Un segnale su un bookmaker senza conto non è giocabile. Con 3 bookmaker basta 1 chiamata gratuita per partita (prima 4): orizzonte di nuovo a 7 giorni. Più conti su piattaforme diverse restano utili più avanti (limiti ai vincenti). |
| D67 | **Fase 4 rimessa a fuoco sui pronostici** (richiesta di Giuse: "mi interessano buoni pronostici, gioco sul mio bookmaker"). Nuova pagina **Pronostici**: per ogni partita la stima migliore disponibile (Pinnacle senza margine → Betfair Exchange → media di mercato senza margine → modello di Archie dove il mercato manca, es. Serie C), esito più probabile, e accanto le quote di **Sisal ed Eurobet alla pari** con un'etichetta: "valore" (≥ +2%), "nella norma", "paga poco" (sotto −5%). Il radar diventa una scheda della stessa pagina, **"Occasioni"**. Tolto "Dove conviene giocarla" (pagina partita e schedina) e la regola 8 | Il principio 1 resta: un pronostico giusto giocato a una quota troppo bassa fa perdere nel lungo periodo, quindi il valore resta come etichetta e filtro, non come funzione separata. "Mercato prima, modello dove il mercato manca" applica D53. |
| D68 | **Multipla del giorno**: una per bookmaker (Sisal, Eurobet: una schedina si gioca su un solo bookmaker), orizzonte Oggi / Settimana. Gambe da 1X2, doppia chance, Under/Over 2.5 e Goal/NoGoal: una per partita, probabilità ≥ 65%, quota totale 3–5, 4 partite. Prima si cerca quella **con valore** (ogni gamba ≥ 0%, regola 7); se non c'è, la più facile con quote **nella norma** (≥ −5%), dichiarata "senza valore" con la perdita attesa in vista; mai gambe che pagano poco o sospette (> 15%). Vince la probabilità di vincere più alta, a parità il valore atteso. Mostra quota, vincita con 10 €, "1 volta su N", probabilità di arrivare vivi all'ultima, valore atteso. Aggiunti da OddsPapi i mercati doppia chance (101902) e Goal/NoGoal (104); la probabilità della doppia chance si ricava sempre dall'1X2 | La specifica chiedeva "nessuna gamba con valore negativo": con i margini reali capiterà di rado, quindi la regola resta il primo tentativo e il ripiego è dichiarato apertamente (principio 1: niente illusioni). Se non c'è nemmeno quella, Archie dice di non giocare. |
| D69 | **Generatore "Archie, fammi una multipla"** (scheda della pagina Pronostici, link dalla dashboard): tre profili (regola 7) — più tranquilla (gambe ≥ 70%, quota 2–3,5, massima probabilità), equilibrata (= multipla del giorno), più coraggiosa (gambe ≥ 45%, quota 5–15, massimo valore atteso); 2–6 partite, filtri per mercati e campionati, importo; stesse regole di valore di D68. Frontend con **lazy loading** delle pagine (avvio da 502 a 370 kB) | Un solo calcolo per multipla del giorno e generatore: la multipla del giorno è il profilo equilibrato con 4 partite. La ricerca resta sotto il secondo anche con 6 partite (limite di combinazioni adattivo). |
| D70 | **Quote fuori linea**: quota di Sisal o Eurobet di oggi con valore ≥ 8% (qualsiasi mercato); sopra il 15% "sospetta" (regola 4: probabile errore palese, rischio annullamento ADM). **Io contro Archie** giudica le tue selezioni chiuse con le probabilità della fotografia salvata alla giocata (mercato senza margine, poi modello): fiuto = vinte − attese, significativo solo oltre 2 errori standard e con almeno 30 selezioni | Niente senno di poi: si usa solo ciò che Archie sapeva allora. Stesso criterio statistico del verdetto del radar. |

**Fase 4 conclusa il 2026-10-15.** Valutazione delle idee: calendario da OddsPapi approvabile come primo passo della Fase 5 (costo zero, dati già scaricati); risultati da OddsPapi scartati (`/scores` a partita, non gratuito). Resta aperta per Giuse la scelta della fonte a pagamento per risultati e live (API-Football).
