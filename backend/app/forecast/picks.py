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
from app.forecast.demargin import proportional
from app.forecast.radar import SIMULATION_BOOKMAKERS, BookOdds, fair_reference, qualifies
from app.forecast.radar_markets import selections

MARKET_SOURCES = ("pinnacle", "betfair_ex", "market_avg")  # dal più preciso al meno preciso
MODEL_SOURCE = "archie"
# Dove manca Pinnacle (Serie C): media delle probabilità senza margine dei bookmaker italiani, più precisa del
# modello di Archie nella prova D95. Almeno 2 bookmaker per fare una media.
CONSENSUS_SOURCE = "consenso"
CONSENSUS_MIN_BOOKMAKERS = 2
ESTIMATE_ONLY = (MODEL_SOURCE, CONSENSUS_SOURCE)  # stime senza riferimento sharp: niente "valore", niente multiple
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


MODEL_VALUE = "sopra Archie"  # la quota batte solo il modello, non ancora messo alla prova contro i bookmaker (D88)
CONSENSUS_VALUE = "sopra la media"  # la quota batte la media dei bookmaker italiani: un'indicazione, non valore (D96)


def price_verdict(v: float, price: float, source: str = "pinnacle") -> str:
    """Etichetta di una quota rispetto alla probabilità giusta: "valore" con la stessa regola delle Occasioni (D72).

    Se la probabilità viene dal solo modello di Archie (es. Serie C, dove Pinnacle non c'è) la quota alta si chiama
    "sopra Archie": è un'indicazione, non un valore dimostrato.
    """
    if qualifies(price, v):
        return MODEL_VALUE if source == MODEL_SOURCE else CONSENSUS_VALUE if source == CONSENSUS_SOURCE else "valore"
    return "nella norma" if v >= LOW_PRICE else "paga poco"


def italian_consensus(book: BookOdds, market: str) -> dict[str, float] | None:
    """Media delle probabilità senza margine (proporzionale, come nella prova D95) dei bookmaker italiani con il mercato completo."""
    wanted = selections(market)
    probs = []
    for bm in SIMULATION_BOOKMAKERS:
        prices = book.get(bm, {}).get(market)
        if prices and set(prices) == set(wanted) and all(p > 1 for p in prices.values()):
            probs.append(dict(zip(wanted, proportional([prices[s] for s in wanted]))))
    if len(probs) < CONSENSUS_MIN_BOOKMAKERS:
        return None
    return {s: sum(p[s] for p in probs) / len(probs) for s in wanted}


def double_chance(p1x2: dict[str, float]) -> dict[str, float]:
    return {"1X": p1x2["1"] + p1x2["X"], "X2": p1x2["X"] + p1x2["2"], "12": p1x2["1"] + p1x2["2"]}


def best_probabilities(book: BookOdds, model: dict[str, Any] | None) -> dict[str, tuple[str, dict[str, float]]]:
    """Mercato → (fonte, probabilità). La doppia chance segue la fonte dell'1X2."""
    out: dict[str, tuple[str, dict[str, float]]] = {}
    for market in ("1X2", "OU2.5", "GG"):
        ref = fair_reference(book, market, MARKET_SOURCES)
        if ref is not None:
            out[market] = ref
        elif (consensus := italian_consensus(book, market)) is not None:
            out[market] = (CONSENSUS_SOURCE, consensus)
        elif model and market in model:
            out[market] = (MODEL_SOURCE, {k: float(v) for k, v in model[market].items()})
    if "1X2" in out:
        source, p = out["1X2"]
        out["DC"] = (source, double_chance(p))
    return out


def offers_for(
    book: BookOdds, market: str, probabilities: dict[str, float], bookmakers: Sequence[str], source: str = "pinnacle"
) -> dict[str, list[Offer]]:
    """Quote dei bookmaker di Giuse per ogni esito, con valore ed etichetta (solo dove la quota c'è)."""
    out: dict[str, list[Offer]] = {}
    for selection, p in probabilities.items():
        for bm in bookmakers:
            price = book.get(bm, {}).get(market, {}).get(selection)
            if price and price > 1:
                v = value(p, price)
                out.setdefault(selection, []).append(Offer(bm, price, v, price_verdict(v, price, source)))
    return out


def match_picks(book: BookOdds, model: dict[str, Any] | None, bookmakers: Sequence[str]) -> list[MarketPick]:
    """Tutti i mercati di una partita con la loro fonte, probabilità e quote dei bookmaker di Giuse."""
    probs = best_probabilities(book, model)
    return [
        MarketPick(market, source, p, offers_for(book, market, p, bookmakers, source))
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


OFF_LINE = 0.08  # una quota "fuori linea": paga almeno l'8% più del giusto (D70)


@dataclass(frozen=True)
class OffLine:
    market: str
    selection: str
    probability: float
    offer: Offer


def off_line(picks: Sequence[MarketPick], threshold: float = OFF_LINE) -> list[OffLine]:
    """Le quote dei bookmaker di Giuse molto sopra il giusto, dalla più fuori linea."""
    out = [
        OffLine(p.market, selection, p.probabilities[selection], o)
        for p in picks
        for selection, offers in p.offers.items()
        for o in offers
        if o.value >= threshold
    ]
    return sorted(out, key=lambda x: x.offer.value, reverse=True)
