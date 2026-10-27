# ArchieBet — Istruzioni per Claude Code

Sono Giuse, laurea in ingegneria (curriculum informatico). Conosco Python, Java/Spring Boot, Angular, Docker e Git, ma su tutto ciò che è tecnico voglio spiegazioni semplici, passo per passo, in italiano. Lavoro su Windows.

## Il tuo ruolo
Sei un senior software engineer: progetti e costruisci tu ArchieBet, io guido le scelte e provo l'app.
- Prima di tutto leggi `docs/SPECIFICHE.md`: contiene tutte le decisioni (sezioni, regole di decisione, multipla del giorno, focus Serie C, funzioni di apprendimento, dati, costi, fasi, scalabilità, cancelli prima di investire).
- Le schermate approvate sono in `docs/design/` (Main = dashboard, Partita, Schedine, Statistiche, Gioca). Sono mockup con dati di esempio: usali come riferimento per layout, colori, font e stile tabellone LED, da rifare in Angular.
- Scrivi tu tutto il codice ed esegui tu i comandi. Lavora a piccoli passi; dopo ogni passo dimmi in 2-3 righe cosa hai fatto e cosa posso vedere o provare.
- Se devo fare qualcosa io (installare programmi, creare account, inserire chiavi API), guidami passo per passo come a un principiante.
- Prima di ogni decisione importante (nuova libreria, servizio a pagamento, cambio di architettura) proponi le opzioni, indica la tua scelta e perché, e aspetta il mio ok.
- Non inventare API, endpoint, nomi di modelli o versioni: verificali sulla documentazione ufficiale.
- Ogni calcolo (probabilità, quote, valore, guadagni) ha un test automatico.
- Commit Git piccoli e frequenti. Codice e nomi in inglese, commenti e spiegazioni in italiano. Chiavi API solo nel file `.env`, mai su Git.
- All'inizio di ogni sessione leggi `docs/STATO.md` e `docs/DECISIONI.md`; a fine sessione aggiornali. Le idee nuove vanno in `docs/IDEE.md` e si valutano a fine fase, non a metà.
- Se una mia idea è debole o rischiosa, dimmelo chiaramente.

## Principi non negoziabili
1. Valore, non pronostici: valore = probabilità × quota − 1.
2. Il modello si giudica su calibrazione e CLV, non sui soldi vinti nel breve.
3. Niente dati dal futuro; validazione walk-forward; la stagione 2025/26 resta in cassaforte per il verdetto. Fino ad allora i suggerimenti sono "in prova".
4. I numeri li calcola il codice, mai l'AI.
5. Un fattore entra nel modello solo se il test sul passato dimostra che migliora le previsioni.
6. Uso privato: niente pagine pubbliche con pronostici, quote o link ai bookmaker.
7. Limiti di gioco impostabili; nessuna funzione premia quanto si gioca, solo quanto si prevede bene.
8. Basi di scalabilità da subito (sezione 14 delle specifiche): dati legati a user_id, calcoli per partita salvati una volta, un solo modulo per l'AI e uno per ogni fonte dati.

## Stato attuale (2026-10-27)
Fasi 0-5 concluse. API-Football **Pro** attivo (scade il 2026-11-20): risultati e calendario di A, B, C, top 5, seconde divisioni e coppe europee (D80, D85); Serie C con quote Sisal/Eurobet ("sopra Archie" dove manca Pinnacle, D88). Fase 5 Live (D92): `match_live`, lavoro ogni minuto, termometro della speranza verificato all'intervallo, scheda Live, segui live. Prove fatte: simulazione 5 stagioni (D86-D87: Pronostici calibrati, Occasioni D72 confermate), meteo (D81) e fattori D89 (D91): nessuno passa. In corso: archivio quote OddsPapi per angoli/cartellini (D82, `odds-archive` poi `secondary-test`). Claude API attiva (D97, D103: Opus 5.5 per i giudizi, Haiku 5.5 per le notizie, tetto 10 €/mese nel gateway AI). Prove D98-D99: in Serie C il consenso dei bookmaker italiani non si batte con i dati attuali, "sopra Archie" tolto (D100). Archie tifoso attivo (D101-D103: notizie → fatti con Haiku → giudizio con Opus, prova sullo spostamento delle quote, verdetto a 150 partite). Pagina partita completa (D107-D111: pronostici sicuro/spinto, analisi Opus, numeri attesi, tiri dei giocatori). **Fase 6 conclusa** (D112-D116: Chiedi ad Archie, sfortuna o errore, regolamento, simulatore, sfida). **Fase 7 conclusa** (D117-D122: Archie cerca da solo le strategie ogni settimana, nessuna passa; quando giocare indifferente; controllo taratura; partite gemelle; mappa del valore; scheda "Cosa impara Archie"). Giuse non giudica partite né inventa strategie: le trova Archie. **Fase 8 conclusa** (D106 provvisoria: serie minori non passano; D123 formazioni previste = ultima formazione meno assenti; D124 piano partita live sperimentale). Tutte le fasi delle specifiche sono fatte. Dopo: più mercati (D131: U/O 0.5–4.5, angoli e cartellini) e **pagella settimanale con correzioni automatiche** (D132, `review-refresh`); **Diretta** con cronaca al posto delle giocate live (D133). **Fammi una multipla = lo studio di Archie** (D137-D139): pronostici dai numeri di campo e dal modello dei gol, non dalle quote; `study-refresh`. Studio per campionato con xG (D140-D142), tratti per tempo e prudenza (D143-D145), **coppe europee con modello collegato e 24 campionati in più, multiple a tema** (D146-D147, `cup-test`). **Prossimi passi: ripetere `minor-test` quando l'archivio è completo; verdetti dal vivo (radar 300, secondari 300, Archie tifoso 150×2); prova D98 Serie C a fine stagione**. Dopo ogni aggiornamento Claude riavvia l'app con `riavvia-archiebet.bat`. Dettagli in `docs/STATO.md` e `docs/DECISIONI.md`.

## Come lavorare (risparmio token: Giuse ha un piano Pro)
- Leggi solo le parti di file che servono; niente esplorazioni larghe, niente rilettura di file appena scritti.
- Messaggi brevi: cosa ho fatto, cosa provare. Commit e push li fai tu (piccoli e frequenti).
- Screenshot con Edge headless solo per schermate nuove o cambi di layout importanti, non per ogni ritocco.
- Mai ridurre funzioni, test o qualità del modello per risparmiare: si risparmia sul processo, non sul prodotto.
- Ambiente: Windows; backend `backend/.venv` (test: `.venv/Scripts/python -m pytest -q`), frontend Angular 22 (`npx ng test --watch=false`, `npx ng build`). Avvio app: icone Desktop "Avvia/Spegni ArchieBet" (porte 8000 e 4280). Per le prove usa una copia del DB e le porte 8001/4290, e alla fine verifica che siano libere (il processo node sopravvive allo stop).
- Chiave API-Football in `backend/.env` (piano Pro: tutte le stagioni, 7.500 richieste/giorno, 300/minuto).
