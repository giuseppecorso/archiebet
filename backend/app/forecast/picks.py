"""Pronostici (D67): per ogni partita la stima di probabilità migliore disponibile e le quote dei bookmaker di Giuse.

Regola (D53): prima il mercato, il modello solo dove il mercato manca.
- Fonte per ogni mercato, in ordine: Pinnacle senza margine, Betfair Exchange, media dei bookmaker senza margine,
  modello di Archie (solo campionati italiani, es. Serie C senza quote).
- Accanto a ogni esito, la quota di Sisal ed Eurobet con un'etichetta di valore (principio 1): un pronostico giusto
  giocato a una quota troppo bassa fa perdere nel lungo periodo.
Funzioni pure, niente database.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.forecast.markets import value
from app.forecast.radar import RADAR_THRESHOLD, BookOdds, fair_reference

MARKET_SOURCES = ("pinnacle", "betfair_ex", "market_avg")  # dal più preciso al meno preciso
MODEL_SOURCE = "archie"
LOW_PRICE = -0.05  # sotto questo valore il bookmaker "paga poco" (margine più alto del solito)
PICK_MARKETS = ("1X2", "DC", "OU2.5", "GG")


@dataclass(frozen=True)
class Offer:
    bookmaker: str
    price: float
    value: float
    verdict: str  # "valore" | "nella norma" | "paga poco"


@dataclass(frozen=True)
class MarketPick:
    market: str
    source: str  # da dove viene la probabilità
    probabilities: dict[str, float]
    offers: dict[str, list[Offer]]  # esito → quote dei bookmaker di Giuse


def price_verdict(v: float, threshold: float = RADAR_THRESHOLD) -> str:
    """Etichetta di una quota rispetto alla probabilità giusta."""
    if v >= threshold:
        return "valore"
    return "nella norma" if v >= LOW_PRICE else "paga poco"


def double_chance(p1x2: dict[str, float]) -> dict[str, float]:
    return {"1X": p1x2["1"] + p1x2["X"], "X2": p1x2["X"] + p1x2["2"], "12": p1x2["1"] + p1x2["2"]}


def best_probabilities(book: BookOdds, model: dict[str, Any] | None) -> dict[str, tuple[str, dict[str, float]]]:
    """Mercato → (fonte, probabilità). La doppia chance segue la fonte dell'1X2."""
    out: dict[str, tuple[str, dict[str, float]]] = {}
    for market in ("1X2", "OU2.5", "GG"):
        ref = fair_reference(book, market, MARKET_SOURCES)
        if ref is not None:
            out[market] = ref
        elif model and market in model:
            out[market] = (MODEL_SOURCE, {k: float(v) for k, v in model[market].items()})
    if "1X2" in out:
        source, p = out["1X2"]
        out["DC"] = (source, double_chance(p))
    return out


def offers_for(book: BookOdds, market: str, probabilities: dict[str, float], bookmakers: Sequence[str]) -> dict[str, list[Offer]]:
    """Quote dei bookmaker di Giuse per ogni esito, con valore ed etichetta (solo dove la quota c'è)."""
    out: dict[str, list[Offer]] = {}
    for selection, p in probabilities.items():
        for bm in bookmakers:
            price = book.get(bm, {}).get(market, {}).get(selection)
            if price and price > 1:
                v = value(p, price)
                out.setdefault(selection, []).append(Offer(bm, price, v, price_verdict(v)))
    return out


def match_picks(book: BookOdds, model: dict[str, Any] | None, bookmakers: Sequence[str]) -> list[MarketPick]:
    """Tutti i mercati di una partita con la loro fonte, probabilità e quote dei bookmaker di Giuse."""
    probs = best_probabilities(book, model)
    return [
        MarketPick(market, source, p, offers_for(book, market, p, bookmakers))
        for market in PICK_MARKETS
        if market in probs
        for source, p in [probs[market]]
    ]


def favorite(picks: Sequence[MarketPick]) -> tuple[str, float] | None:
    """Esito 1X2 più probabile: il "pronostico secco"."""
    one_x_two = next((p for p in picks if p.market == "1X2"), None)
    if one_x_two is None:
        return None
    selection = max(one_x_two.probabilities, key=one_x_two.probabilities.get)
    return selection, one_x_two.probabilities[selection]
