"""Prova D82 sui mercati secondari: angoli e cartellini (Over/Under totali e per squadra).

Dall'archivio dello storico OddsPapi (Pinnacle, Sisal, Eurobet) e dai risultati di football-data:
(a) la quota giusta di Pinnacle in chiusura prevede i risultati almeno quanto Sisal ed Eurobet?
(b) con quale regola conta i cartellini ogni bookmaker (cartellini: giallo 1, rosso 1; punti: giallo 1, rosso 2)?
(c) le Occasioni con la regola D72, controllate ogni 6 ore, hanno CLV positivo contro la chiusura di Pinnacle?
"""

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.forecast.demargin import proportional, shin
from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.radar import qualifies

CHECK_EVERY = timedelta(hours=6)  # come il radar
LOOKBACK = timedelta(days=7)

Series = list[tuple[datetime, float | None]]  # prezzo nel tempo (None = quota tolta)


@dataclass(frozen=True)
class Line:
    """Un mercato Over/Under: famiglia ("angoli", "cartellini", ... per squadra), chi (totale, casa, ospite), soglia."""

    family: str  # "angoli" | "cartellini"
    side: str  # "totale" | "casa" | "ospite"
    threshold: float


def line_of(definition: Mapping) -> Line | None:
    """Riconosce i mercati della prova dalla definizione OddsPapi; solo soglie .5 (niente rimborsi)."""
    name, line = definition["marketName"], float(definition.get("handicap") or 0)
    if definition.get("period") != "fulltime" or "Half" in name or "Over Under" not in name or line % 1 != 0.5:
        return None
    family = "angoli" if name.startswith("Corners") else "cartellini" if name.startswith("Bookings") else None
    if family is None:
        return None
    side = "casa" if "Team 1" in name else "ospite" if "Team 2" in name else "totale"
    return Line(family, side, line)


@dataclass(frozen=True)
class Result:
    home_corners: int
    away_corners: int
    home_yellow: int
    away_yellow: int
    home_red: int
    away_red: int

    def count(self, family: str, side: str, rule: str = "cartellini") -> int:
        if family == "angoli":
            home, away = self.home_corners, self.away_corners
        else:
            red = 2 if rule == "punti" else 1
            home, away = self.home_yellow + red * self.home_red, self.away_yellow + red * self.away_red
        return home + away if side == "totale" else home if side == "casa" else away


RULES = ("cartellini", "punti")


def at(series: Series, t: datetime) -> float | None:
    """Prezzo valido al momento t (l'ultimo prima di t), None se non c'è o è stato tolto."""
    price = None
    for ts, p in series:
        if ts > t:
            break
        price = p
    return price


def closing(series: Series, kickoff: datetime) -> float | None:
    """Quota di chiusura: l'ultima attiva prima del calcio d'inizio (al fischio il mercato viene sospeso)."""
    price = None
    for ts, p in series:
        if ts >= kickoff:
            break
        if p is not None:
            price = p
    return price


@dataclass(frozen=True)
class MarketHistory:
    """Over e Under di una linea per una partita, per bookmaker."""

    match_id: int
    kickoff: datetime
    line: Line
    prices: Mapping[str, Mapping[str, Series]]  # bookmaker → "over"/"under" → serie


def over_won(r: Result, line: Line, rule: str = "cartellini") -> bool:
    return r.count(line.family, line.side, rule) > line.threshold


# --- (a) + (b): precisione delle quote di chiusura ------------------------------------------------------------

@dataclass(frozen=True)
class Accuracy:
    bookmaker: str
    rule: str
    n: int
    log_loss: float


def closing_log_loss(histories: Iterable[MarketHistory], results: Mapping[int, Result], bookmakers: Sequence[str],
                     family: str, rule: str, need_all: bool = True) -> list[Accuracy]:
    """Log loss dell'Over (probabilità senza margine alla chiusura) sugli stessi eventi per ogni bookmaker.

    Pinnacle con Shin, gli italiani in proporzione (come nelle altre prove). need_all: solo le linee quotate da tutti.
    """
    losses: dict[str, list[float]] = defaultdict(list)
    for h in histories:
        if h.line.family != family or h.match_id not in results:
            continue
        probs = {}
        for bm in bookmakers:
            o, u = (closing(h.prices.get(bm, {}).get(k, []), h.kickoff) for k in ("over", "under"))
            if o and u and o > 1 and u > 1:
                probs[bm] = (shin if bm == "pinnacle" else proportional)([o, u])[0]
        if need_all and len(probs) < len(bookmakers):
            continue
        won = over_won(results[h.match_id], h.line, rule)
        for bm, p in probs.items():
            p = min(max(p, 1e-6), 1 - 1e-6)
            losses[bm].append(-math.log(p if won else 1 - p))
    return [Accuracy(bm, rule, len(v), sum(v) / len(v)) for bm, v in losses.items() if v]


# --- (c) Occasioni ------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SecondaryPlay:
    match_id: int
    line: Line
    selection: str
    bookmaker: str
    price: float
    value: float
    clv: float
    won: bool


def occasions(histories: Iterable[MarketHistory], results: Mapping[int, Result], playable: Sequence[str],
              rule_of: Callable[[str], str] = lambda bm: "cartellini") -> list[SecondaryPlay]:
    """Regola D72 controllata ogni 6 ore nell'ultima settimana: la prima volta che una quota la supera è la giocata."""
    plays = []
    for h in histories:
        pin = h.prices.get("pinnacle", {})
        if not pin:
            continue
        close_o, close_u = closing(pin.get("over", []), h.kickoff), closing(pin.get("under", []), h.kickoff)
        if not close_o or not close_u:
            continue
        fair_close = dict(zip(("over", "under"), shin([close_o, close_u])))
        taken: set[tuple[str, str]] = set()
        t = h.kickoff - LOOKBACK
        while t < h.kickoff:
            po, pu = at(pin.get("over", []), t), at(pin.get("under", []), t)
            if po and pu:
                fair = dict(zip(("over", "under"), shin([po, pu])))
                for bm in playable:
                    for sel in ("over", "under"):
                        price = at(h.prices.get(bm, {}).get(sel, []), t)
                        if not price or (bm, sel) in taken:
                            continue
                        value = fair[sel] * price - 1
                        if qualifies(price, value):
                            taken.add((bm, sel))
                            won = None
                            if h.match_id in results:
                                over = over_won(results[h.match_id], h.line, rule_of(bm))
                                won = over if sel == "over" else not over
                            plays.append(SecondaryPlay(h.match_id, h.line, sel, bm, price, value, fair_close[sel] * price - 1, bool(won)))
            t += CHECK_EVERY
    return plays


def clv_estimate(plays: Sequence[SecondaryPlay]) -> Estimate | None:
    if not plays:
        return None
    return clustered_mean([p.clv for p in plays], [p.match_id for p in plays])
