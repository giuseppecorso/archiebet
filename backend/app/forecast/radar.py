"""Radar delle quote (D57): il motore di Archie in Serie A e B.

Probabilità giusta = quota di un bookmaker "sharp" (Pinnacle, altrimenti Betfair Exchange) senza margine.
Per ogni esito si cerca la quota migliore tra i bookmaker su cui Giuse può giocare: se
probabilità giusta × quota − 1 ≥ soglia, è un segnale del radar ("dove giocarla" = quel bookmaker).
Funzioni pure, niente database: il salvataggio e la simulazione dal vivo stanno in radar_service.py.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.forecast.clv import SUSPICIOUS_VALUE, ClvSummary
from app.forecast.data import ODDS_MARKETS, REFERENCE_BOOKMAKERS, fair_probabilities
from app.forecast.markets import value

RADAR_THRESHOLD = 0.02  # valore minimo di un segnale (D57, D59)
LIVE_TARGET = 300  # giocate necessarie per il giudizio dal vivo (D59)

# Bookmaker italiani su cui si gioca davvero (D66): quelli dove Giuse ha un conto. Si cambiano in
# backend/.env con RADAR_BOOKMAKERS; questo è solo il valore predefinito.
PLAYABLE_BOOKMAKERS = ("sisal", "eurobet")

BookOdds = dict[str, dict[str, dict[str, float]]]  # bookmaker → mercato → esito → quota (una partita)


@dataclass(frozen=True)
class RadarSignal:
    market: str
    selection: str
    bookmaker: str  # dove giocarla
    price: float
    fair_probability: float
    fair_source: str  # bookmaker sharp da cui viene la probabilità giusta
    value: float

    @property
    def suspicious(self) -> bool:
        """Regola di decisione 4: un valore così alto di solito è un errore di quota, non un'occasione."""
        return self.value > SUSPICIOUS_VALUE


def _complete(prices: dict[str, float] | None, market: str) -> bool:
    return bool(prices) and set(prices) == set(ODDS_MARKETS[market]) and all(p > 1 for p in prices.values())


def fair_reference(book: BookOdds, market: str, sharp: Sequence[str] = REFERENCE_BOOKMAKERS) -> tuple[str, dict[str, float]] | None:
    """Probabilità giuste del mercato dal primo bookmaker sharp con il mercato completo."""
    for bookmaker in sharp:
        prices = book.get(bookmaker, {}).get(market)
        if _complete(prices, market):
            return bookmaker, dict(zip(prices, fair_probabilities(*prices.values())))
    return None


def scan(
    book: BookOdds,
    threshold: float = RADAR_THRESHOLD,
    playable: Sequence[str] = PLAYABLE_BOOKMAKERS,
    sharp: Sequence[str] = REFERENCE_BOOKMAKERS,
) -> list[RadarSignal]:
    """Segnali di una partita: per ogni esito la quota migliore giocabile, se ha valore ≥ soglia. Ordinati per valore."""
    signals = []
    for market, selections in ODDS_MARKETS.items():
        ref = fair_reference(book, market, sharp)
        if ref is None:
            continue
        source, fair = ref
        for selection in selections:
            offers = [
                (book[bm][market][selection], bm)
                for bm in playable
                if book.get(bm, {}).get(market, {}).get(selection, 0) > 1
            ]
            if not offers:
                continue
            price = max(p for p, _ in offers)
            bookmaker = next(bm for p, bm in offers if p == price)  # a parità, il primo della lista
            v = value(fair[selection], price)
            if v >= threshold:
                signals.append(RadarSignal(market, selection, bookmaker, price, fair[selection], source, v))
    return sorted(signals, key=lambda s: s.value, reverse=True)


def closing_value(price: float, closing_fair_probability: float) -> float:
    """CLV di una giocata: quota presa × probabilità giusta di chiusura − 1 (come nel backtest, D52)."""
    return price * closing_fair_probability - 1.0


def summarize_live(clv: Sequence[float], profit: Sequence[float]) -> ClvSummary | None:
    """Riepilogo della simulazione dal vivo; profit = guadagno per euro (vinta: quota − 1, persa: −1)."""
    if not clv:
        return None
    c = np.array(clv)
    se = float(c.std(ddof=1) / np.sqrt(len(c))) if len(c) > 1 else float("inf")
    roi = float(np.mean(profit)) if len(profit) else 0.0
    return ClvSummary(len(c), float(c.mean()), se, float((c > 0).mean()), roi)


def live_verdict(summary: ClvSummary | None, target: int = LIVE_TARGET) -> str:
    """Criterio di D59, fissato prima di vedere i dati: almeno 300 giocate e CLV medio > 2 errori standard."""
    if summary is None or summary.n < target:
        return "in prova"
    return "superato" if summary.mean_clv > 2 * summary.clv_std_error else "non superato"
