"""Giocate di valore del modello nel backtest e loro CLV (principio 2: il giudice è il CLV, non il profitto).

Per ogni partita prevista: se una quota offerta (es. bet365 qualche giorno prima) ha valore
probabilità × quota − 1 ≥ soglia, è una "giocata di valore". Il suo CLV è quota presa / quota giusta
di chiusura − 1, con la chiusura di riferimento di D48 (Pinnacle, altrimenti Betfair Exchange).
CLV medio positivo = il modello vede prima del mercato dove andranno le quote.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.forecast.backtest import Prediction
from app.forecast.data import Odds
from app.forecast.markets import value

SUSPICIOUS_VALUE = 0.15  # regola di decisione 4: sopra il 15% il valore è "sospetto"


@dataclass(frozen=True)
class ValueBet:
    match_id: int
    competition_id: int
    market: str
    selection: str
    probability: float
    price: float
    value: float
    clv: float  # quota presa × probabilità giusta di chiusura − 1
    won: bool


def _probabilities(p: Prediction) -> dict[str, dict[str, float]]:
    return {
        "1X2": dict(zip(("1", "X", "2"), p.p_1x2)),
        "OU2.5": {"over": p.p_over25, "under": 1.0 - p.p_over25},
    }


def _won(p: Prediction, market: str, selection: str) -> bool:
    if market == "1X2":
        return ("1", "X", "2")[p.outcome] == selection
    return (p.total_goals >= 3) == (selection == "over")


def value_bets(preds: Sequence[Prediction], offered: Odds, closing_fair: Odds, threshold: float = 0.05) -> list[ValueBet]:
    """Tutte le giocate con valore ≥ soglia che hanno anche la chiusura di riferimento per misurare il CLV."""
    bets = []
    for p in preds:
        for market, probs in _probabilities(p).items():
            prices = offered.get(p.match_id, {}).get(market)
            fair = closing_fair.get(p.match_id, {}).get(market)
            if not prices or not fair:
                continue
            for selection, prob in probs.items():
                v = value(prob, prices[selection])
                if v >= threshold:
                    bets.append(
                        ValueBet(p.match_id, p.competition_id, market, selection, prob, prices[selection], v,
                                 prices[selection] * fair[selection] - 1.0, _won(p, market, selection))
                    )
    return bets


@dataclass(frozen=True)
class ClvSummary:
    n: int
    mean_clv: float
    clv_std_error: float
    share_positive: float  # quota di giocate con CLV > 0
    roi: float  # guadagno per euro puntato a puntata fissa: si mostra, ma non è il giudice


def summarize(bets: Sequence[ValueBet]) -> ClvSummary | None:
    if not bets:
        return None
    clv = np.array([b.clv for b in bets])
    profit = np.array([b.price - 1.0 if b.won else -1.0 for b in bets])
    se = float(clv.std(ddof=1) / np.sqrt(len(clv))) if len(clv) > 1 else float("inf")
    return ClvSummary(len(bets), float(clv.mean()), se, float((clv > 0).mean()), float(profit.mean()))
