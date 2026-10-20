"""Simulazione storica dei Pronostici, delle Occasioni e della Multipla del giorno (D86).

Per ogni partita passata si rifà quello che Archie fa dal vivo, con le sole informazioni disponibili prima del
calcio d'inizio: probabilità giusta = Pinnacle d'apertura senza margine (Shin), quota giocabile = bet365 d'apertura.
Poi si confronta con quello che è successo: chiusura di Pinnacle (CLV) e risultato.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from app.forecast.multiple import Leg, Profile, build_multiple

Prices = dict[str, dict[str, float]]  # mercato → esito → quota o probabilità


@dataclass(frozen=True)
class SimMatch:
    match_id: int
    season: str
    league: str
    day: date  # giorno italiano della partita
    kickoff: datetime
    home_goals: int
    away_goals: int
    fair_open: Prices  # probabilità giuste all'apertura
    fair_close: Prices  # probabilità giuste alla chiusura
    book: Prices  # quote giocabili all'apertura (bet365)


def won(m: SimMatch, market: str, selection: str) -> bool:
    goals = m.home_goals + m.away_goals
    if market == "1X2":
        result = "1" if m.home_goals > m.away_goals else "2" if m.home_goals < m.away_goals else "X"
        return selection == result
    if market == "OU2.5":
        return (goals > 2.5) == (selection == "over")
    raise ValueError(market)


# --- Statistiche con errori standard per partita -------------------------------------------------------------

@dataclass(frozen=True)
class Estimate:
    mean: float
    std_error: float
    n: int  # osservazioni
    clusters: int  # partite

    @property
    def t(self) -> float:
        return self.mean / self.std_error if self.std_error > 0 else 0.0

    @property
    def significant(self) -> bool:
        """Positivo oltre 2 errori standard."""
        return self.mean > 2 * self.std_error


def clustered_mean(values: Sequence[float], clusters: Sequence[int]) -> Estimate:
    """Media con errore standard robusto ai gruppi: più giocate della stessa partita non sono indipendenti."""
    n = len(values)
    mean = sum(values) / n
    groups: dict[int, float] = defaultdict(float)
    for v, c in zip(values, clusters):
        groups[c] += v - mean
    g = len(groups)
    if g < 2:
        return Estimate(mean, float("inf"), n, g)
    var = g / (g - 1) * sum(s * s for s in groups.values()) / n**2
    return Estimate(mean, math.sqrt(var), n, g)


# --- (1) Calibrazione dei Pronostici --------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationBin:
    low: float
    high: float
    n: int
    predicted: float  # probabilità media prevista
    observed: float  # frequenza vera
    std_error: float  # errore standard della frequenza attesa

    @property
    def off_by(self) -> float:
        return self.observed - self.predicted


def calibration(matches: Iterable[SimMatch], market: str, edges: Sequence[float] = (0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0001)) -> list[CalibrationBin]:
    """Per fasce di probabilità: quanto esce davvero un esito dato al 30%, al 50%, ..."""
    rows = [(p, won(m, market, sel)) for m in matches for sel, p in m.fair_open.get(market, {}).items()]
    out = []
    for low, high in zip(edges, edges[1:]):
        inside = [(p, w) for p, w in rows if low <= p < high]
        if not inside:
            continue
        n = len(inside)
        predicted = sum(p for p, _ in inside) / n
        observed = sum(w for _, w in inside) / n
        se = math.sqrt(sum(p * (1 - p) for p, _ in inside)) / n
        out.append(CalibrationBin(low, min(high, 1.0), n, predicted, observed, se))
    return out


@dataclass(frozen=True)
class FavoriteHits:
    n: int
    expected: float  # pronostici secchi attesi giusti (somma delle probabilità)
    observed: int
    std_error: float

    @property
    def ratio(self) -> float:
        return self.observed / self.expected


def favorite_hits(matches: Iterable[SimMatch], market: str) -> FavoriteHits:
    """Il pronostico secco (l'esito più probabile) esce quanto previsto?"""
    picks = []
    for m in matches:
        probs = m.fair_open.get(market)
        if probs:
            sel, p = max(probs.items(), key=lambda kv: kv[1])
            picks.append((p, won(m, market, sel)))
    expected = sum(p for p, _ in picks)
    return FavoriteHits(len(picks), expected, sum(w for _, w in picks), math.sqrt(sum(p * (1 - p) for p, _ in picks)))


# --- (2) Occasioni ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    """Regola delle Occasioni: valore minimo = max(floor, factor × √(quota − 1)), quota non oltre cap."""

    name: str
    factor: float = 0.02
    floor: float = 0.015
    cap: float | None = 4.0
    flat: float | None = None  # soglia fissa (vecchia D57): ignora factor e floor

    def required(self, price: float) -> float:
        if self.flat is not None:
            return self.flat
        return max(self.floor, self.factor * math.sqrt(max(price - 1.0, 0.0)))

    def qualifies(self, price: float, value: float) -> bool:
        return (self.cap is None or price <= self.cap) and value >= self.required(price)


RULES = (
    Rule("D72 (attuale)"),
    Rule("2% fisso, senza tetto (D57)", cap=None, flat=0.02),
    Rule("D72 con 3%", factor=0.03),
    Rule("D72 con tetto a 3", cap=3.0),
)


@dataclass(frozen=True)
class Play:
    match_id: int
    season: str
    league: str
    market: str
    selection: str
    price: float
    value: float
    clv: float
    won: bool

    @property
    def profit(self) -> float:
        return self.price - 1.0 if self.won else -1.0


def occasions(matches: Iterable[SimMatch], rule: Rule) -> list[Play]:
    """Le giocate che la regola avrebbe fatto alla quota d'apertura, con CLV e risultato."""
    plays = []
    for m in matches:
        for market, prices in m.book.items():
            fair, close = m.fair_open.get(market), m.fair_close.get(market)
            if not fair or not close:
                continue
            for sel, price in prices.items():
                if sel not in fair or sel not in close:
                    continue
                value = fair[sel] * price - 1.0
                if rule.qualifies(price, value):
                    plays.append(Play(m.match_id, m.season, m.league, market, sel, price, value, close[sel] * price - 1.0, won(m, market, sel)))
    return plays


@dataclass(frozen=True)
class PlaySummary:
    clv: Estimate
    roi: Estimate


def summarize_plays(plays: Sequence[Play]) -> PlaySummary | None:
    if not plays:
        return None
    ids = [p.match_id for p in plays]
    return PlaySummary(clustered_mean([p.clv for p in plays], ids), clustered_mean([p.profit for p in plays], ids))


def group_plays(plays: Iterable[Play], key: Callable[[Play], str]) -> dict[str, list[Play]]:
    out: dict[str, list[Play]] = defaultdict(list)
    for p in plays:
        out[key(p)].append(p)
    return dict(out)


PRICE_BANDS = ((1.0, 1.6), (1.6, 2.2), (2.2, 3.0), (3.0, 4.0), (4.0, 1000.0))


def price_band(price: float) -> str:
    for low, high in PRICE_BANDS:
        if low <= price < high:
            return f"{low:.1f}–{high:.1f}" if high < 1000 else f"oltre {low:.1f}"
    return "?"


# --- (3) Multipla del giorno ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class SimMultiple:
    day: date
    season: str
    legs: int
    price: float
    probability: float
    won: bool
    with_value: bool


def daily_multiples(matches: Sequence[SimMatch], profile: Profile, n: int) -> list[SimMultiple]:
    """Ogni giorno con partite: la multipla che Archie avrebbe proposto quel mattino."""
    by_day: dict[date, list[SimMatch]] = defaultdict(list)
    for m in matches:
        by_day[m.day].append(m)
    out = []
    for day in sorted(by_day):
        day_matches = {m.match_id: m for m in by_day[day]}
        legs = [
            Leg(m.match_id, m.kickoff, market, sel, m.fair_open[market][sel], price)
            for m in day_matches.values()
            for market, prices in m.book.items()
            if market in m.fair_open
            for sel, price in prices.items()
            if sel in m.fair_open[market]
        ]
        best = build_multiple(legs, n, profile)
        if best is None:
            continue
        hit = all(won(day_matches[leg.match_id], leg.market, leg.selection) for leg in best.legs)
        season = next(iter(day_matches.values())).season
        out.append(SimMultiple(day, season, n, best.price, best.win_probability, hit, best.with_value))
    return out


@dataclass(frozen=True)
class MultipleSummary:
    n: int
    expected_wins: float
    wins: int
    std_error: float  # delle vincite attese
    roi: float

    @property
    def within_two_se(self) -> bool:
        return abs(self.wins - self.expected_wins) <= 2 * self.std_error


def summarize_multiples(ms: Sequence[SimMultiple]) -> MultipleSummary | None:
    if not ms:
        return None
    expected = sum(m.probability for m in ms)
    se = math.sqrt(sum(m.probability * (1 - m.probability) for m in ms))
    roi = sum((m.price - 1.0) if m.won else -1.0 for m in ms) / len(ms)
    return MultipleSummary(len(ms), expected, sum(m.won for m in ms), se, roi)
