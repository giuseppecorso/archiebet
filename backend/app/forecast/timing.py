"""Quando giocare: subito o aspettare? (Fase 7, D119)

Dalla storia delle quote (archivio OddsPapi): per ogni momento prima del calcio d'inizio, il CLV che si sarebbe
preso giocando lì da Sisal o Eurobet, contro la probabilità giusta di chiusura (Pinnacle senza margine, o il
consenso italiano dove Pinnacle non c'è). Un consiglio si dà solo se regge in entrambe le metà dell'archivio.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.forecast.demargin import proportional, shin
from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.history_sim import RULES as _RULES
from app.forecast.secondary_test import Series, at, closing

D72 = _RULES[0]
PLAYABLE = ("sisal", "eurobet")
SELECTIONS = {"1X2": ("1", "X", "2"), "OU2.5": ("over", "under")}
FIRST = "alla prima quota"
HORIZONS: tuple[tuple[str, timedelta | None], ...] = (
    (FIRST, None),
    ("72 ore prima", timedelta(hours=72)),
    ("48 ore prima", timedelta(hours=48)),
    ("24 ore prima", timedelta(hours=24)),
    ("12 ore prima", timedelta(hours=12)),
    ("6 ore prima", timedelta(hours=6)),
    ("2 ore prima", timedelta(hours=2)),
    ("30 minuti prima", timedelta(minutes=30)),
)
LAST = HORIZONS[-1][0]
OCCASION_HORIZONS = ("48 ore prima", "24 ore prima", "6 ore prima")

PLAY_EARLY = "gioca prima"
WAIT = "aspetta l'ultimo momento"
INDIFFERENT = "è indifferente"


@dataclass(frozen=True)
class Book:
    """Storia delle quote di una partita: bookmaker → mercato → esito → serie."""

    fixture_id: str
    group: str
    kickoff: datetime
    prices: Mapping[str, Mapping[str, Mapping[str, Series]]]

    def first_time(self) -> datetime | None:
        times = [s[0][0] for bm in PLAYABLE for m in self.prices.get(bm, {}).values() for s in m.values() if s]
        return min(times) if times else None

    def price(self, bookmaker: str, market: str, selection: str, moment: datetime | None) -> float | None:
        series = self.prices.get(bookmaker, {}).get(market, {}).get(selection, [])
        return closing(series, self.kickoff) if moment is None else at(series, moment)

    def fair(self, market: str, moment: datetime | None, reference: str) -> dict[str, float] | None:
        """Probabilità giuste al momento (None = chiusura): Pinnacle con Shin, oppure consenso italiano proporzionale."""
        sels = SELECTIONS[market]
        if reference == "pinnacle":
            prices = [self.price("pinnacle", market, s, moment) for s in sels]
            if not all(p and p > 1 for p in prices):
                return None
            return dict(zip(sels, shin(prices)))
        books = []
        for bm in self.prices:
            prices = [self.price(bm, market, s, moment) for s in sels]
            if all(p and p > 1 for p in prices):
                books.append(proportional(prices))
        if len(books) < 2:
            return None
        return {s: sum(b[i] for b in books) / len(books) for i, s in enumerate(sels)}


def moment_of(book: Book, horizon: timedelta | None) -> datetime | None:
    if horizon is None:
        return book.first_time()
    return book.kickoff - horizon


@dataclass(frozen=True)
class Obs:
    """Un esito di un bookmaker in una partita: CLV a ogni momento (None se la quota non c'era)."""

    fixture_id: str
    group: str
    kickoff: datetime
    price: Mapping[str, float | None]
    clv: Mapping[str, float | None]
    value: Mapping[str, float | None]  # valore contro la probabilità giusta allo stesso momento


def observations(books: Iterable[Book], reference: Callable[[Book], str]) -> list[Obs]:
    out = []
    for b in books:
        ref = reference(b)
        for market, sels in SELECTIONS.items():
            close = b.fair(market, None, ref)
            if close is None:
                continue
            fair_at = {label: b.fair(market, moment_of(b, h), ref) for label, h in HORIZONS}
            for bm in PLAYABLE:
                for s in sels:
                    price, clv, value = {}, {}, {}
                    for label, h in HORIZONS:
                        p = b.price(bm, market, s, moment_of(b, h))
                        price[label] = p
                        clv[label] = p * close[s] - 1 if p and p > 1 else None
                        f = fair_at[label]
                        value[label] = p * f[s] - 1 if p and p > 1 and f else None
                    if clv[LAST] is not None:
                        out.append(Obs(b.fixture_id, b.group, b.kickoff, price, clv, value))
    return out


@dataclass(frozen=True)
class HorizonResult:
    label: str
    clv: Estimate
    vs_last: Estimate  # CLV a questo momento meno CLV a 30 minuti, appaiato


def _ids(obs: Sequence[Obs]) -> list[int]:
    index: dict[str, int] = {}
    return [index.setdefault(o.fixture_id, len(index)) for o in obs]


def by_horizon(obs: Sequence[Obs]) -> list[HorizonResult]:
    out = []
    for label, _ in HORIZONS:
        pairs = [o for o in obs if o.clv[label] is not None]
        if len(pairs) < 2:
            continue
        ids = _ids(pairs)
        out.append(HorizonResult(label, clustered_mean([o.clv[label] for o in pairs], ids),
                                 clustered_mean([o.clv[label] - o.clv[LAST] for o in pairs], ids)))  # fmt: skip
    return out


def halves(obs: Sequence[Obs]) -> tuple[list[Obs], list[Obs]]:
    times = sorted(o.kickoff for o in obs)
    mid = times[len(times) // 2]
    return [o for o in obs if o.kickoff < mid], [o for o in obs if o.kickoff >= mid]


def _beats(e: Estimate) -> bool:
    return e.mean > 2 * e.std_error


@dataclass(frozen=True)
class Advice:
    verdict: str
    best: str | None  # momento consigliato se "gioca prima"
    results: list[HorizonResult]


def advise(obs: Sequence[Obs]) -> Advice:
    """Regola D119: un consiglio solo se regge in entrambe le metà dell'archivio."""
    results = by_horizon(obs)
    early = [r for r in results if r.label != LAST]
    if not early:
        return Advice(INDIFFERENT, None, results)
    first, second = halves(obs)
    h1, h2 = {r.label: r for r in by_horizon(first)}, {r.label: r for r in by_horizon(second)}
    best = max(early, key=lambda r: r.clv.mean)
    if best.label in h1 and best.label in h2 and _beats(h1[best.label].vs_last) and _beats(h2[best.label].vs_last):
        return Advice(PLAY_EARLY, best.label, results)
    later_wins = all(r.label in h1 and r.label in h2 and _beats(_neg(h1[r.label].vs_last)) and _beats(_neg(h2[r.label].vs_last)) for r in early)
    return Advice(WAIT if later_wins else INDIFFERENT, None, results)


def _neg(e: Estimate) -> Estimate:
    return Estimate(-e.mean, e.std_error, e.n, e.clusters)


@dataclass(frozen=True)
class OccasionTiming:
    horizon: str
    n: int
    now: Estimate  # CLV giocando subito
    gain: Estimate  # subito meno 30 minuti
    still_value: float  # quota che a 30 minuti ha ancora valore D72 (contro Pinnacle a 30 minuti)
    play_now: bool  # regola D119 in entrambe le metà


def occasion_timing(obs: Sequence[Obs], horizon: str) -> OccasionTiming | None:
    """Occasioni D72 viste a un certo momento: meglio giocarle subito o a 30 minuti?"""
    sel = [o for o in obs if o.clv.get(horizon) is not None and _qualifies(o, horizon)]
    if len(sel) < 2:
        return None
    ids = _ids(sel)
    now = clustered_mean([o.clv[horizon] for o in sel], ids)
    gain = clustered_mean([o.clv[horizon] - o.clv[LAST] for o in sel], ids)
    still = sum(1 for o in sel if _qualifies(o, LAST)) / len(sel)
    first, second = halves(sel)
    ok = all(len(h) >= 2 and _beats(clustered_mean([o.clv[horizon] - o.clv[LAST] for o in h], _ids(h))) for h in (first, second))
    return OccasionTiming(horizon, len(sel), now, gain, still, ok)


def _qualifies(o: Obs, horizon: str) -> bool:
    """Valore D72 al momento indicato (soglia che cresce con la quota, tetto a 4)."""
    price, value = o.price.get(horizon), o.value.get(horizon)
    return price is not None and value is not None and D72.qualifies(price, value)
