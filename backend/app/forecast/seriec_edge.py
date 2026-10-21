"""Prova D98: battere il consenso dei bookmaker italiani in Serie C.

Consenso = media delle probabilità senza margine (proporzionale) dei bookmaker con il mercato completo.
(T0) il consenso in chiusura è un riferimento migliore di quello in apertura?
(T1-T3) formazioni, combinazione con Archie, calibrazione: correzioni del consenso giudicate con la log loss.
(T4) Occasioni contro il consenso degli altri bookmaker (metodo Kaunitz): CLV contro il consenso in chiusura.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from scipy.optimize import minimize, minimize_scalar

from app.forecast.demargin import proportional
from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.radar import qualifies
from app.forecast.secondary_test import CHECK_EVERY, LOOKBACK, Series, at, closing

SPLIT = datetime(2026, 9, 13, tzinfo=UTC)  # taratura prima, conferma dal 13/09/2026 (metà delle partite)
MIN_BOOKMAKERS = 2
PLAYABLE = ("sisal", "eurobet")
SELECTIONS = {"1X2": ("1", "X", "2"), "OU2.5": ("over", "under"), "GG": ("yes", "no")}

Prices = Mapping[str, Mapping[str, float]]  # bookmaker → esito → quota


@dataclass(frozen=True)
class MatchBook:
    """Storia delle quote di una partita: bookmaker → mercato → esito → serie dei prezzi."""

    match_id: int
    kickoff: datetime
    home_goals: int
    away_goals: int
    prices: Mapping[str, Mapping[str, Mapping[str, Series]]]

    def winner(self, market: str) -> str:
        h, a = self.home_goals, self.away_goals
        if market == "1X2":
            return "1" if h > a else "X" if h == a else "2"
        if market == "OU2.5":
            return "over" if h + a >= 3 else "under"
        return "yes" if h > 0 and a > 0 else "no"

    def snapshot(self, market: str, t: datetime | None = None) -> dict[str, dict[str, float]]:
        """Quote di ogni bookmaker al momento t (None = chiusura), solo se il mercato è completo."""
        out = {}
        for bm, markets in self.prices.items():
            series = markets.get(market, {})
            prices = {s: (closing(series.get(s, []), self.kickoff) if t is None else at(series.get(s, []), t)) for s in SELECTIONS[market]}
            if all(p and p > 1 for p in prices.values()):
                out[bm] = prices
        return out


def consensus(book: Prices, market: str, exclude: Sequence[str] = ()) -> dict[str, float] | None:
    """Media delle probabilità senza margine dei bookmaker (esclusi quelli indicati), almeno MIN_BOOKMAKERS."""
    sels = SELECTIONS[market]
    probs = [proportional([prices[s] for s in sels]) for bm, prices in book.items() if bm not in exclude]
    if len(probs) < MIN_BOOKMAKERS:
        return None
    return {s: sum(p[i] for p in probs) / len(probs) for i, s in enumerate(sels)}


def log_loss(p: float) -> float:
    return -math.log(max(p, 1e-12))


def paired(diffs: Sequence[float], ids: Sequence[int]) -> Estimate:
    """Differenza media di log loss per partita con il suo errore standard (negativo = la correzione è migliore)."""
    return clustered_mean(list(diffs), list(ids))


# --- (T0) apertura contro chiusura -----------------------------------------------------------------------------

def opening_consensus(m: MatchBook, market: str = "1X2") -> dict[str, float] | None:
    """Consenso alla prima rilevazione con almeno 2 bookmaker negli ultimi 7 giorni prima del calcio d'inizio."""
    start = m.kickoff - LOOKBACK
    times = sorted({ts for markets in m.prices.values() for series in markets.get(market, {}).values() for ts, _ in series
                    if start <= ts < m.kickoff})  # fmt: skip
    for t in [start, *times]:
        c = consensus(m.snapshot(market, t), market)
        if c is not None:
            return c
    return None


# --- (T1-T3) correzioni del consenso -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Row:
    """Una partita per le prove T1-T3: consenso in chiusura (1, X, 2), esito (0, 1, 2) e l'informazione in più."""

    match_id: int
    kickoff: datetime
    outcome: int
    consensus: tuple[float, float, float]
    extra: tuple[float, ...]  # T1: (A,); T2: probabilità di Archie (1, X, 2); T3: nessuna


Correction = Callable[[Row, Sequence[float]], tuple[float, ...]]


def _normalize(weights: Sequence[float]) -> tuple[float, ...]:
    total = sum(weights)
    return tuple(w / total for w in weights)


def lineup_correction(row: Row, params: Sequence[float]) -> tuple[float, ...]:
    """T1: p ∝ consenso × exp(β·A·s), s = +1, 0, −1 per 1, X, 2; A = assenti casa − ospite."""
    (beta,), (a,) = params, row.extra
    return _normalize([c * math.exp(beta * a * s) for c, s in zip(row.consensus, (1, 0, -1))])


def pool_correction(row: Row, params: Sequence[float]) -> tuple[float, ...]:
    """T2: p ∝ consenso^(1−w) × Archie^w (combinazione log-lineare di due previsioni)."""
    (w,) = params
    return _normalize([c ** (1 - w) * max(a, 1e-12) ** w for c, a in zip(row.consensus, row.extra)])


def calibration_correction(row: Row, params: Sequence[float]) -> tuple[float, ...]:
    """T3: p ∝ consenso^α × exp(δ) sul pareggio."""
    alpha, delta = params
    return _normalize([c**alpha * (math.exp(delta) if i == 1 else 1.0) for i, c in enumerate(row.consensus)])


@dataclass(frozen=True)
class Spec:
    correction: Correction
    start: tuple[float, ...]
    bounds: tuple[tuple[float, float], ...]


SPECS = {
    "T1 formazioni": Spec(lineup_correction, (0.0,), ((-10.0, 10.0),)),
    "T2 combinazione con Archie": Spec(pool_correction, (0.0,), ((0.0, 1.0),)),
    "T3 calibrazione (pareggi, sfavoriti)": Spec(calibration_correction, (1.0, 0.0), ((0.5, 2.0), (-1.0, 1.0))),
}


def fit(rows: Sequence[Row], spec: Spec) -> tuple[float, ...]:
    """Parametri di massima verosimiglianza (log loss minima) entro i limiti."""
    def nll(params: Sequence[float]) -> float:
        return sum(log_loss(spec.correction(r, params)[r.outcome]) for r in rows)

    if len(spec.start) == 1:
        (low, high), = spec.bounds
        return (float(minimize_scalar(lambda x: nll([x]), bounds=(low, high), method="bounded").x),)
    return tuple(float(x) for x in minimize(nll, spec.start, bounds=spec.bounds, method="L-BFGS-B").x)


def week_of(t: datetime) -> tuple[int, int]:
    year, week, _ = t.isocalendar()
    return year, week


def cross_validated(rows: Sequence[Row], spec: Spec) -> list[tuple[float, ...]]:
    """Previsioni lasciando fuori una settimana alla volta: parametri stimati sulle altre settimane."""
    weeks: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        weeks[week_of(r.kickoff)].append(i)
    out: list[tuple[float, ...]] = [()] * len(rows)
    for idx in weeks.values():
        held = set(idx)
        params = fit([r for i, r in enumerate(rows) if i not in held], spec)
        for i in idx:
            out[i] = spec.correction(rows[i], params)
    return out


def improvement(rows: Sequence[Row], predictions: Sequence[Sequence[float]]) -> Estimate:
    """Log loss della correzione meno quella del consenso, partita per partita."""
    diffs = [log_loss(p[r.outcome]) - log_loss(r.consensus[r.outcome]) for r, p in zip(rows, predictions)]
    return paired(diffs, [r.match_id for r in rows])


def passes(e: Estimate) -> bool:
    return e.mean < -2 * e.std_error


# --- (T4) Occasioni contro il consenso degli altri bookmaker -------------------------------------------------------

@dataclass(frozen=True)
class EdgePlay:
    match_id: int
    kickoff: datetime
    market: str
    selection: str
    bookmaker: str
    price: float
    value: float
    clv: float
    p_close: float
    won: bool


Fair = Callable[["MatchBook", str, Prices, str], Mapping[str, float] | None]  # partita, mercato, quote del momento, bookmaker


def occasions(books: Sequence[MatchBook], fair: Fair, playable: Sequence[str] = PLAYABLE,
              markets: Sequence[str] = tuple(SELECTIONS),
              closing_fair: Callable[["MatchBook", str], Mapping[str, float] | None] | None = None) -> list[EdgePlay]:  # fmt: skip
    """Ogni 6 ore negli ultimi 7 giorni: quota giocabile contro una probabilità giusta, regola D72.

    La prima rilevazione per partita, mercato ed esito è la giocata (a parità di momento la quota più alta);
    CLV contro il consenso in chiusura di tutti i bookmaker (D98 T0: riferimento valido), oppure contro closing_fair.
    """
    plays = []
    for m in books:
        for market in markets:
            sels = SELECTIONS[market]
            close = closing_fair(m, market) if closing_fair else consensus(m.snapshot(market), market)
            if close is None:
                continue
            taken: set[str] = set()
            t = m.kickoff - LOOKBACK
            while t < m.kickoff and len(taken) < len(sels):
                book = m.snapshot(market, t)
                best: dict[str, tuple[float, float, str]] = {}
                for bm in playable:
                    if bm not in book:
                        continue
                    probs = fair(m, market, book, bm)
                    if probs is None:
                        continue
                    for s in sels:
                        price = book[bm][s]
                        value = probs[s] * price - 1
                        if s not in taken and qualifies(price, value) and price > best.get(s, (0.0, 0.0, ""))[0]:
                            best[s] = (price, value, bm)
                for s, (price, value, bm) in best.items():
                    taken.add(s)
                    plays.append(EdgePlay(m.match_id, m.kickoff, market, s, bm, price, value, close[s] * price - 1, close[s], m.winner(market) == s))
                t += CHECK_EVERY
    return plays


def kaunitz_occasions(books: Sequence[MatchBook], playable: Sequence[str] = PLAYABLE) -> list[EdgePlay]:
    """D98 T4: probabilità giusta = consenso degli altri bookmaker (metodo Kaunitz)."""
    return occasions(books, lambda m, market, book, bm: consensus(book, market, exclude=(bm,)), playable)


def model_occasions(books: Sequence[MatchBook], model: Mapping[tuple[int, str], Mapping[str, float]],
                    playable: Sequence[str] = PLAYABLE) -> list[EdgePlay]:  # fmt: skip
    """D99 (b): probabilità giusta = Archie ((partita, mercato) → esito → probabilità), solo 1X2 e Under/Over 2.5."""
    return occasions(books, lambda m, market, book, bm: model.get((m.match_id, market)), playable, ("1X2", "OU2.5"))


def clv_of(plays: Sequence[EdgePlay]) -> Estimate | None:
    if not plays:
        return None
    return clustered_mean([p.clv for p in plays], [p.match_id for p in plays])


def pinnacle_fair(book: Prices, market: str) -> dict[str, float] | None:
    """Probabilità giuste di Pinnacle (Shin) da un'istantanea delle quote, se il mercato è completo."""
    from app.forecast.demargin import shin

    prices = book.get("pinnacle")
    if not prices:
        return None
    sels = SELECTIONS[market]
    return dict(zip(sels, shin([prices[s] for s in sels])))


def pinnacle_occasions(books: Sequence[MatchBook], playable: Sequence[str] = PLAYABLE) -> list[EdgePlay]:
    """D106 (b): regola D72 su Sisal ed Eurobet contro Pinnacle, CLV contro la chiusura di Pinnacle."""
    return occasions(books, lambda m, market, book, bm: pinnacle_fair(book, market), playable,
                     closing_fair=lambda m, market: pinnacle_fair(m.snapshot(market), market))  # fmt: skip
