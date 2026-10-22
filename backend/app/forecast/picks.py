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
from app.forecast.radar_markets import DNB, is_secondary, is_team_goals, parse_secondary, parse_team_goals, selections

MARKET_SOURCES = ("pinnacle", "betfair_ex", "market_avg")  # dal più preciso al meno preciso
MODEL_SOURCE = "archie"
# Dove manca Pinnacle (Serie C): media delle probabilità senza margine dei bookmaker italiani, più precisa del
# modello di Archie nella prova D95. Almeno 2 bookmaker per fare una media.
CONSENSUS_SOURCE = "consenso"
CONSENSUS_MIN_BOOKMAKERS = 2
ESTIMATE_ONLY = (MODEL_SOURCE, CONSENSUS_SOURCE)  # stime senza riferimento sharp: niente "valore" (nelle multiple il consenso sì, D130)
LOW_PRICE = -0.05  # sotto questo valore il bookmaker "paga poco" (margine più alto del solito)
GOAL_MARKETS = ("OU0.5", "OU1.5", "OU2.5", "OU3.5", "OU4.5", "GG")
PICK_MARKETS = ("1X2", "DC", DNB, *GOAL_MARKETS)  # OU1.5 e OU3.5 dal D130, OU0.5 e OU4.5 dal D131, Draw No Bet dal D135
SECONDARY_SHARP = ("pinnacle",)
SECONDARY_RANGE = (0.12, 0.88)  # angoli e cartellini: solo linee "giocabili", non Over 5.5 angoli a 1,02 (D131)


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
    corrected: bool = False  # probabilità corrette dalla taratura che Archie ha imparato (D132)


CONSENSUS_VALUE = "sopra la media"  # la quota batte la media dei bookmaker italiani: un'indicazione, non valore (D96)


def price_verdict(v: float, price: float, source: str = "pinnacle") -> str:
    """Etichetta di una quota rispetto alla probabilità giusta: "valore" con la stessa regola delle Occasioni (D72).

    Contro la media dei bookmaker italiani la quota alta si chiama "sopra la media" (indicazione, D96). Contro il solo
    modello di Archie non si segnala mai: in Serie C quelle quote hanno avuto CLV −6/−7% (D99), il mercato va contro.
    """
    if qualifies(price, v):
        if source == MODEL_SOURCE:
            return "nella norma"
        return CONSENSUS_VALUE if source == CONSENSUS_SOURCE else "valore"
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


def market_family(market: str) -> str:
    """"esito" (1X2, doppia chance, Draw No Bet), "gol" (Under/Over, Gol/No gol), "gol squadra", "angoli" o "cartellini"."""
    if (parsed := parse_secondary(market)) is not None:
        return parsed[0]
    if is_team_goals(market):
        return "gol squadra"
    return "esito" if market in ("1X2", "DC", DNB) else "gol"


def team_goals_markets(book: BookOdds) -> list[str]:
    """Gol di una squadra quotati (D135), in ordine: casa poi ospite, per linea."""
    found = {m for markets in book.values() for m in markets if is_team_goals(m)}
    return sorted(found, key=lambda m: (parse_team_goals(m)[0] != "casa", parse_team_goals(m)[1]))


def draw_no_bet(p1x2: dict[str, float]) -> dict[str, float]:
    """Draw No Bet: col pareggio si riprende la puntata, quindi conta solo 1 contro 2."""
    played = p1x2["1"] + p1x2["2"]
    return {"1": p1x2["1"] / played, "2": p1x2["2"] / played}


def secondary_markets(book: BookOdds) -> list[str]:
    """Angoli e cartellini presenti nelle quote, in ordine: famiglia, totale/casa/ospite, linea."""
    found = {m for markets in book.values() for m in markets if is_secondary(m)}
    order = {"angoli": 0, "cartellini": 1, "totale": 0, "casa": 1, "ospite": 2}
    return sorted(found, key=lambda m: (order[parse_secondary(m)[0]], order[parse_secondary(m)[1]], parse_secondary(m)[2]))


def best_probabilities(book: BookOdds, model: dict[str, Any] | None, secondary: bool = False) -> dict[str, tuple[str, dict[str, float]]]:
    """Mercato → (fonte, probabilità). La doppia chance segue la fonte dell'1X2.

    Con secondary=True anche angoli e cartellini (D131): Pinnacle senza margine, altrimenti il consenso di Sisal ed
    Eurobet; mai il modello. Solo le linee con probabilità tra 12% e 88%.
    """
    out: dict[str, tuple[str, dict[str, float]]] = {}
    if secondary:
        for market in secondary_markets(book):
            ref = fair_reference(book, market, SECONDARY_SHARP) or (
                (CONSENSUS_SOURCE, c) if (c := italian_consensus(book, market)) is not None else None
            )
            if ref is not None and SECONDARY_RANGE[0] <= ref[1]["over"] <= SECONDARY_RANGE[1]:
                out[market] = ref
    for market in ("1X2", *GOAL_MARKETS):
        ref = fair_reference(book, market, MARKET_SOURCES)
        if ref is not None:
            out[market] = ref
        elif (consensus := italian_consensus(book, market)) is not None:
            out[market] = (CONSENSUS_SOURCE, consensus)
        elif model and market in model:
            out[market] = (MODEL_SOURCE, {k: float(v) for k, v in model[market].items()})
    for market in team_goals_markets(book):  # gol di una squadra (D135): in tutti i campionati, si chiudono col risultato
        ref = fair_reference(book, market, SECONDARY_SHARP) or (
            (CONSENSUS_SOURCE, c) if (c := italian_consensus(book, market)) is not None else None
        )
        if ref is not None and SECONDARY_RANGE[0] <= ref[1]["over"] <= SECONDARY_RANGE[1]:
            out[market] = ref
    if "1X2" in out:
        source, p = out["1X2"]
        out["DC"] = (source, double_chance(p))
        out[DNB] = (source, draw_no_bet(p))
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


def match_picks(book: BookOdds, model: dict[str, Any] | None, bookmakers: Sequence[str], secondary: bool = False) -> list[MarketPick]:
    """Tutti i mercati di una partita con la loro fonte, probabilità e quote dei bookmaker di Giuse
    (angoli e cartellini solo con secondary=True: campionati dove si possono chiudere, D131)."""
    probs = best_probabilities(book, model, secondary)
    order = [*PICK_MARKETS, *(m for m in probs if is_team_goals(m)), *(m for m in probs if is_secondary(m))]
    return [
        MarketPick(market, source, p, offers_for(book, market, p, bookmakers, source))
        for market in order
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
