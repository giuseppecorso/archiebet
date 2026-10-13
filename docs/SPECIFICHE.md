# ArchieBet — Specifiche del progetto

Documento di riferimento con tutte le decisioni prese. Le istruzioni del progetto rimandano qui per i dettagli.
Schermate di riferimento: artifact "ArchieBet – Schermate" (Dashboard, Pagina partita, Le mie schedine, Le mie statistiche, Gioca). Lo stile è approvato; i dati nelle schermate sono di esempio.

## 1. Cos'è
App web che fa da esperto personale di pronostici sul calcio. Non indovina chi vince: stima le probabilità, le confronta con le quote, trova quelle sbagliate, costruisce multiple sensate e oneste, segue le giocate live e fa imparare dall'esperienza sia l'utente sia il modello.
Per ora gira solo sul PC di Giuse, per uso privato. Il codice nasce però già pronto a diventare multi-utente (vedi sezione 14).
Nome: ArchieBet. Motto: "Give me the odds, I'll move the world." Testi dell'app in italiano.

## 2. Stile grafico
Sportsbook USA, tabellone da stadio a LED: fondo nero, cifre a punti luminosi (font Doto) solo per i numeri, titoli in Bebas Neue, testi in Barlow.
Colori con significato fisso: verde = valore/vinta, rosso = persa/valore negativo, ambra = live, in corso, quote e orari. Il colore non è mai l'unico segnale (sempre anche testo o icona).

## 3. Sezioni dell'app
1. Partite (dashboard)
   - Menu campionati per paese con tendina (Italia, Inghilterra, Spagna, Germania, Francia, Coppe europee) e filtri attivi.
   - Barra notizie che scorre (titoli + link a fonti, mai articoli copiati).
   - In cima: "Multipla del giorno" (la più facile e sensata) + generatore "Archie, fammi una multipla".
   - Elenco partite: schede Tutte / Live / Prossime / Risultati, raggruppate per campionato, quote 1X2, etichette di valore e "Hai 1 giocata".
   - Riquadro "Quote fuori linea oggi".
   - ArchieTV: solo contenuti legali e gratuiti (highlights dai canali YouTube ufficiali delle leghe, link ai lettori ufficiali di canali gratuiti come Sportitalia e Rai Sport). Seconda scheda: termometro live.
   - La mia schedina: selezioni, quota, importo, vincita, analisi di Archie, tasti "L'ho giocata" e "Gioca simulata", barra budget.
   - Chiedi ad Archie.
2. Pagina partita
   - Intestazione: loghi, ultimi 5 risultati, stadio di casa sullo sfondo, orario, meteo.
   - Probabilità 1/X/2 di Archie, statistiche a confronto, tutti i mercati (probabilità, quota giusta, quota migliore e bookmaker, valore, aggiungi alla schedina).
   - "Cosa ha considerato Archie": ogni fattore con stato NEL MODELLO / IN PROVA / SOLO INFO ed effetto.
   - Scheda "Mercato": radar quote fuori mercato e grafico dei movimenti delle quote.
   - Partite gemelle, termometro live, pronostico di Archie e perché, Chiedi ad Archie sul match.
3. Le mie schedine
   - Elenco a destra (aperte, chiuse, reali e simulate), dettaglio a sinistra con risultati live, "Segui live", termometro della speranza, "Archie rivede la schedina" (probabilità, CLV, sfortuna o errore).
   - "Registra una giocata": partite e mercati dalle liste, quote precompilate, si scrive solo l'importo (la quota si corregge solo se diversa).
4. Le mie statistiche
   - Riepilogo (giocato, tornato, saldo, rendimento, vinte, CLV) per settimana / 30 giorni / stagione / sempre; reali e simulate separate.
   - "Tu contro Archie", "Dove vinci e dove perdi" (per numero di partite, mercato, campionato, bookmaker), abitudini, vincite e perdite.
   - "Il tuo stile di gioco" e "Il tuo regolamento personale" scritti da Archie, "Il tuo fiuto, misurato".
5. Gioca (solo crediti finti)
   - Simulatore partita (10.000 simulazioni, partita "dal vivo" sul tabellone, comandi "E se...").
   - Sfida contro Archie (pronostici a giornata, crediti, classifica, amici invitabili).
6. Laboratorio (aggiunto il 2026-10-11, idea di Giuse)
   - Campionati: per campionato e stagione, classifica finale e numeri del campionato (1/X/2 in casa e fuori, media gol, Over 2.5, Goal), confronto tra stagioni e tra gironi.
   - Squadre: storia stagione per stagione (categoria, posizione, punti, gol), tutte le partite, casa/trasferta, scontri diretti.
   - Strategie: il "Laboratorio strategie" della sezione 6.5 (Fase 7).
   - Solo dati e numeri calcolati dal codice; niente pronostici.
7. Impostazioni: limiti di gioco (budget settimanale/mensile), campionati seguiti, bookmaker (Sisal, Eurobet, bet365, Snai, Lottomatica, Goldbet, Betsson, Planetwin365), soglie di valore, squadra del cuore.

## 4. Regole di decisione di Archie
1. Probabilità di partenza (aggiornato con D53/D57, misurato nel backtest della Fase 3): dove c'è un mercato preciso (Serie A e B) la base è la probabilità di Pinnacle (o Betfair Exchange) senza margine; il modello Dixon-Coles + Elo stima la probabilità di ogni risultato esatto, da cui tutti i mercati coerenti, e serve dove il mercato manca o è debole (Serie C, mercati senza quote) e come confronto.
2. Quota giusta = 1 / probabilità. Valore = probabilità × quota − 1. Suggerimento solo sopra soglia (default 5%, configurabile; nel backtest già dal 2% il CLV è positivo).
3. Radar (motore principale in A e B, D57): il valore nasce quando un bookmaker paga più della quota giusta del mercato preciso. Il modello e i fattori correggono la probabilità solo se hanno superato la prova del nove CONTRO il mercato (D56).
4. Valore sopra il 15% = sospetto: invito a controllare notizie e formazioni. Quota palesemente fuori linea = rischio annullamento da parte del bookmaker (regole ADM sugli errori palesi).
5. Prova del nove: un fattore entra nel modello solo se il test walk-forward sul passato dimostra che migliora log loss / Brier.
6. Ricalcolo all'uscita delle formazioni e ai movimenti forti delle quote.
7. Multiple: solo selezioni con valore ≥ 0 (o sopra soglia secondo il livello), max una per partita o correlazione calcolata dalla tabella dei risultati; obiettivo secondo il rischio (prudente = massima probabilità con valore ≥ 0; equilibrato; coraggioso = massimo valore atteso). Mostra sempre "vinci circa 1 volta su N" e la variante prudente. Se non c'è valore: "non giocare" o singole.
8. (Tolta con D67: niente confronto tra bookmaker; si gioca sul proprio bookmaker di riferimento.)
9. Quanto puntare: puntata fissa; Kelly frazionato (es. 1/4) solo dopo il verdetto del modello, sempre dentro i limiti.
10. Campionati con pochi dati: soglia di valore più alta e quote massime.
11. Giudizio su Archie: calibrazione e CLV, mai solo profitto. Stagione 2025/26 in cassaforte per il verdetto. Fino ad allora suggerimenti "in prova".
12. Regolamento personale: prima di "L'ho giocata", Archie avvisa se la schedina viola le regole ricavate dai dati dell'utente.

## 5. Multipla del giorno
- Ogni giorno, con le partite disponibili. Spunta per scegliere l'orizzonte: "solo partite di oggi" oppure "tutte le partite della settimana".
- In dashboard la più facile e sensata: 4 partite (default), ognuna con probabilità ≥ 65%, nessuna con valore negativo, quota obiettivo 3–5.
- Partite distribuite nella giornata; le più sicure giocano per prime, quella con più valore per ultima, per massimizzare la probabilità di arrivare vivi all'ultima partita.
- Mostra: quota, vincita, probabilità di vincere, probabilità di arrivare viva all'ultima partita, valore atteso.
- Varianti più difficili costruibili dal generatore (più tranquilla, più coraggiosa, numero di partite, mercati, campionati, importo).
- Termometro della speranza: probabilità di vincita aggiornata in diretta da risultato e minuto di ogni partita.
- Rispetta il regolamento personale (es. niente squadra del cuore).

## 6. Funzioni distintive (apprendimento)
1. Gioca simulata: schedine non giocate, seguite e chiuse come vere, in un portafoglio separato.
2. Sfortuna o errore?: autopsia dopo ogni partita confrontando la "fotografia" al momento della giocata (probabilità, quote, fattori, notizie) con quanto successo in campo (xG). Vale per giocate reali, simulate e di Archie. Serve a imparare sulle partite, non solo sul giocatore.
3. Il tuo fiuto, misurato: quando l'utente gioca diversamente da Archie si registra; dove l'utente batte il modello, il suo giudizio entra come fattore con peso calcolato.
4. Partite gemelle: partite storiche più simili e come sono finite (terzo controllo).
5. Laboratorio strategie: regola scritta in italiano → filtro → backtest sulle stagioni passate con le quote dell'epoca.
6. Archie si corregge da solo: ricalibrazione periodica per campionato e mercato, visibile in "Cosa conta davvero".
7. Quando giocare: dallo storico delle quote, per campionato e mercato, Archie dice se giocare ora o aspettare (agisce sul CLV).
8. Formazioni previste (più avanti), piano partita per il live con soglie precalcolate (sperimentale, in simulata), mappa mensile del valore.

## 7. Focus Serie C (approfondimento maniacale)
- Obiettivo: diventare più forti del mercato dove il mercato è più debole.
- Dati: calendario, risultati, formazioni, infortuni da API-Football; rating di forza costruito da noi sui risultati (ClubElo non copre la Serie C); storico quote da verificare (football-data.co.uk copre la Serie B, per la C serve lo storico di OddsPapi o altra fonte).
- Fattori da testare con particolare cura: campi sintetici, distanze di trasferta nel girone, squadre B / Under 23 dei club di Serie A e rotazioni, crisi societarie e penalizzazioni, mercato invernale, motivazione playoff/playout, cambi di allenatore.
- Notizie locali (siti dei club e testate locali) lette dall'AI e trasformate in fattori da misurare.
- Cautele: limiti di puntata più bassi; una quota "palesemente sbagliata" può nascondere un'informazione che il bookmaker ha già (assenze, crisi) o movimenti anomali: Archie la segnala come sospetta, non la insegue.

## 8. Fattori considerati
Forma squadra (xG, Elo, punti), forma e importanza dei giocatori, infortuni e squalifiche, acquisti e cessioni, cambio allenatore, stile di gioco e incrocio di stili, meteo (Open-Meteo), campo sintetico (lista manuale), tifo (già nel fattore campo, extra misurati), motivazione (da classifica e calendario), stanchezza (riposo, coppe, viaggi), notizie qualitative (estratte dall'AI). Tutti visibili; nel modello solo se superano la prova del nove.

## 9. Dati e servizi
- football-data.co.uk: storico risultati e quote (incluse chiusure Pinnacle). Gratis.
- Understat: xG top 5 campionati dal 2014/15. Gratis.
- ClubElo: forza club europei fino alla Serie B. Gratis.
- Open-Meteo: meteo storico e previsioni. Gratis per uso non commerciale.
- API-Football: calendario, risultati, formazioni, infortuni, trasferimenti, allenatori, live, Serie C. Gratis per i test, Pro circa 19 $/mese a regime.
- OddsPapi: quote Sisal IT, Eurobet IT, Snai IT, bet365, Pinnacle, Betfair Exchange, storico. Prima il piano gratuito, poi piano su misura (prezzo da verificare). Piano B: odds-api.io.
- YouTube (canali ufficiali delle leghe) per gli highlights.
- Claude API: Haiku per lavori ripetitivi (notizie, autopsie, report), Sonnet per analisi e domande. Tetto di spesa mensile nel codice.
- Niente scraping dei siti dei bookmaker. Niente contenuti pirata.
- Attenzione: quasi tutti questi piani sono per uso personale/non commerciale. Un'app con utenti paganti richiede licenze commerciali (vedi sezione 15).

## 10. Costi mensili stimati (uso personale)
- Fasi 0–4: 0 € (tutto sul PC di Giuse).
- A regime: API-Football ~19 $, quote da verificare (obiettivo < 20 €), AI 5–15 €. Server solo quando si va online.
- Hosting esistente: WordPress su Serverplan (giuseppecorso.it). Adatto solo come indirizzo (sottodominio, es. archie.giuseppecorso.it) o per file statici; il backend Python sempre acceso richiede un VPS. Da verificare nel pannello: SSH, Python App, Cron Jobs. Qualunque cosa pubblicata sul dominio personale va dietro login e con noindex (il dominio è usato anche per la carriera).

## 11. Stack
- Backend: Python 3.12+ (venv), FastAPI, SQLAlchemy + SQLite all'inizio (PostgreSQL quando servono più utenti), APScheduler, pandas, numpy, scipy, scikit-learn; LightGBM come sfidante.
- Frontend: Angular, aggiornamenti live con SSE.
- Sviluppo e uso su Windows (PC di Giuse); deploy con Docker solo quando si va online.

## 12. Principi non negoziabili
1. Valore, non pronostici.
2. Calibrazione e CLV per giudicare; ROI secondario.
3. Niente dati dal futuro; validazione walk-forward; cassaforte 2025/26.
4. I numeri li calcola il codice, mai l'AI.
5. Fattori nel modello solo se provati.
6. Uso privato: niente pagine pubbliche con pronostici, quote o link ai bookmaker (divieto di pubblicità anche indiretta del gioco in Italia). Eventuale monetizzazione futura solo dopo parere legale.
7. Limiti di gioco impostabili; nessuna funzione premia quanto si gioca, solo quanto si prevede bene.
8. Nessun modello per scommesse live, tranne il piano partita sperimentale in simulata.

## 13. Fasi (ognuna finisce solo quando il criterio è soddisfatto)
- Fase 0 – Setup: controllo Python, Node.js, Git sul PC; repo GitHub privato; scheletro backend e frontend in stile approvato, già con le basi di scalabilità (sezione 14); docs/STATO.md, docs/DECISIONI.md, docs/IDEE.md. Fatto: l'app si apre con il menu delle sezioni.
- Fase 1 – Partite: dati Serie A, B e C (storico e calendario), elenco partite con filtri, pagina partita con statistiche vere.
- Fase 1.5 – Laboratorio (base): schede Campionati e Squadre sui dati già presenti. Fatto: si studiano classifica e numeri di ogni campionato/stagione e la storia di ogni squadra.
- Fase 2 – Giocate: registrazione giocate reali e simulate, chiusura automatica, statistiche di gioco, limiti, fotografia al momento della giocata.
- Fase 3 – Modello: Dixon-Coles + rating di forza (anche per la Serie C), mercati, backtest walk-forward, prova del nove dei fattori, verdetto sulla cassaforte. Suggerimenti "in prova" fino al verdetto.
- Fase 4 – Pronostici e valore (rivista con D67): test OddsPapi, quote automatiche, **Pronostici** (la stima migliore per ogni partita, con le quote di Sisal ed Eurobet ed etichetta di valore), Occasioni sul tuo bookmaker (radar), quote fuori linea, Multipla del giorno, generatore, Io contro Archie. Parte il mese di simulazione (giudicato su CLV e calibrazione).
- Fase 5 – Live: risultati in diretta, termometro della speranza, segui live.
- Fase 6 – AI e Gioca: Chiedi ad Archie, autopsie "sfortuna o errore", notizie (anche locali Serie C), regolamento personale, simulatore, sfida contro Archie.
- Fase 7 – Apprendimento: fiuto misurato, autocorrezione, quando giocare, partite gemelle, laboratorio strategie, mappa del valore.
- Fase 8 – Coppe europee e altri campionati; formazioni previste; piano partita live.
- Soldi veri solo se backtest e simulazione mostrano CLV positivo.

## 14. Basi per la scalabilità (da fare subito, costo zero)
1. Ogni dato personale (giocate, schedine, statistiche, impostazioni, limiti, regolamento) è legato a un user_id, anche se per ora l'utente è uno solo. Login semplice già presente.
2. Separazione netta tra calcoli per partita (modello, mercati, radar, contenuti AI per partita) e dati per utente. I calcoli per partita si fanno una volta e si salvano; ogni utente li legge.
3. Un solo modulo per l'AI (gateway): sceglie il modello (Haiku per domande semplici, Sonnet per quelle complesse), usa il prompt caching sui dati comuni, salva le risposte alle domande frequenti, applica quote per utente e un tetto di spesa globale con avvisi.
4. Un solo modulo per ogni fonte dati (adapter), con cache: cambiare fornitore o piano non tocca il resto del codice.
5. Database dietro SQLAlchemy, così il passaggio da SQLite a PostgreSQL è una configurazione.
6. Configurazione da file .env (chiavi, limiti, piani), nessun valore fisso nel codice.
7. Registro dei consumi: chiamate API e costi AI per giorno e per utente, visibili in una pagina di amministrazione.
8. Stima di riferimento: 1.000 utenti × 30 domande/mese ≈ 130 $ di AI per le domande + ~25 $ per i contenuti per partita, cioè 15–20 centesimi a utente.

## 15. Prima di investire: i cancelli
Nessun investimento, e soprattutto nessun prestito, prima di aver superato questi cancelli, in ordine:
1. Il modello supera il verdetto sulla cassaforte e mostra CLV positivo per almeno 3 mesi di simulazione e uso reale.
2. Giuse usa ArchieBet ogni settimana per almeno 3 mesi.
3. 20–50 tester gratuiti (amici) lo usano e tornano ogni settimana.
4. Parere legale scritto sul modello di business (divieto di pubblicità del gioco, servizi di pronostici, GDPR, pagamenti) e forma fiscale (partita IVA o società).
5. Preventivi scritti delle licenze commerciali per dati e quote.
6. Prova che qualcuno paga: lista d'attesa o pre-vendite prima di spendere.
7. Business plan con punto di pareggio.
Poi si investe a gradini: prima un piccolo budget proprio, prestiti solo per cifre che Giuse può rimborsare con lo stipendio anche se il progetto fallisce.
