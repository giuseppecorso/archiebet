"""Archie cerca da solo le strategie (Fase 7, D117-D118).

Le strategie le definisce il codice, non l'utente: campionato × esito × fascia di quota × momento della stagione ×
filtro (sempre / solo con valore D72). Ogni strategia si misura col CLV alla quota bet365 d'apertura contro la
chiusura di Pinnacle senza margine. Con tante prove qualcuna sembra buona per caso: per questo una soglia severa in
taratura e la conferma su stagioni separate (pre-registrate in D118).

Ogni strategia gioca un solo esito, quindi al massimo una giocata per partita: l'errore standard semplice è già
quello "per partita". Così ogni strategia si calcola sommando celle precalcolate, senza riscorrere le giocate.
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.forecast.history_sim import PRICE_BANDS, RULES, Estimate, SimMatch, won

SELECTIONS = (("1X2", "1"), ("1X2", "X"), ("1X2", "2"), ("OU2.5", "over"), ("OU2.5", "under"))
EARLY = "prime 5 giornate"
LATE = "ultime 6 giornate"
WHOLE = "tutta la stagione"
MOMENTS = (WHOLE, EARLY, LATE)
EARLY_GAMES = 5
LATE_GAMES = 6
ALWAYS = "sempre"
WITH_VALUE = "con valore D72"
FILTERS = (ALWAYS, WITH_VALUE)
ALL_LEAGUES = "tutti"

# Soglie pre-registrate (D118)
MIN_PLAYS = 200
MIN_CLV = 0.01
T_SCREEN = 3.0
T_CONFIRM = 2.0

D72 = RULES[0]
SELECTION_LABELS = {"1": "1 (casa)", "X": "X (pareggio)", "2": "2 (trasferta)", "over": "Over 2.5", "under": "Under 2.5"}


@dataclass(frozen=True)
class Strategy:
    league: str  # codice campionato o "tutti"
    market: str
    selection: str
    band: tuple[float, float]  # fascia di quota bet365 [da, a)
    moment: str
    filter: str

    @property
    def name(self) -> str:
        low, high = self.band
        band = f"quota {low:.1f}–{high:.1f}" if high < 1000 else f"quota oltre {low:.1f}"
        league = "tutti i campionati" if self.league == ALL_LEAGUES else self.league
        return f"{SELECTION_LABELS[self.selection]}, {band}, {league}, {self.moment}, {self.filter}"


def all_strategies(leagues: Sequence[str]) -> list[Strategy]:
    return [
        Strategy(league, market, sel, band, moment, flt)
        for league in (*leagues, ALL_LEAGUES)
        for market, sel in SELECTIONS
        for band in PRICE_BANDS
        for moment in MOMENTS
        for flt in FILTERS
    ]


# --- Momento della stagione --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Fixture:
    match_id: int
    league: str
    season: str
    kickoff: datetime
    home_id: int
    away_id: int


def season_moments(fixtures: Iterable[Fixture]) -> dict[int, str | None]:
    """Per ogni partita: "prime 5 giornate" se è tra le prime 5 di entrambe le squadre, "ultime 6 giornate" se è tra
    le ultime 6 di entrambe, altrimenti None. Il calendario intero è noto prima (anche per la stagione in corso)."""
    by_season: dict[tuple[str, str], list[Fixture]] = defaultdict(list)
    for f in fixtures:
        by_season[(f.league, f.season)].append(f)
    out: dict[int, str | None] = {}
    for games in by_season.values():
        games.sort(key=lambda f: (f.kickoff, f.match_id))
        total: dict[int, int] = defaultdict(int)
        for f in games:
            total[f.home_id] += 1
            total[f.away_id] += 1
        played: dict[int, int] = defaultdict(int)
        for f in games:
            idx = {t: played[t] for t in (f.home_id, f.away_id)}  # partite già giocate prima di questa
            if max(idx.values()) < EARLY_GAMES:
                out[f.match_id] = EARLY
            elif max(total[t] - idx[t] for t in idx) <= LATE_GAMES:
                out[f.match_id] = LATE
            else:
                out[f.match_id] = None
            for t in idx:
                played[t] += 1
    return out


# --- Giocate e celle ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Bet:
    match_id: int
    season: str
    league: str
    market: str
    selection: str
    price: float
    value: float  # rispetto a Pinnacle d'apertura
    clv: float  # rispetto a Pinnacle di chiusura
    won: bool
    moment: str | None

    @property
    def profit(self) -> float:
        return self.price - 1.0 if self.won else -1.0

    @property
    def has_value(self) -> bool:
        """Soglia di valore D72 senza il tetto di quota: le fasce di quota sono già una dimensione della ricerca."""
        return self.value >= D72.required(self.price)


def bets(matches: Iterable[SimMatch], moments: Mapping[int, str | None]) -> list[Bet]:
    """Ogni esito di ogni partita con quota bet365 e Pinnacle d'apertura e chiusura."""
    out = []
    for m in matches:
        for market, sel in SELECTIONS:
            price = m.book.get(market, {}).get(sel)
            p_open = m.fair_open.get(market, {}).get(sel)
            p_close = m.fair_close.get(market, {}).get(sel)
            if not price or p_open is None or p_close is None:
                continue
            out.append(Bet(m.match_id, m.season, m.league, market, sel, price, p_open * price - 1.0, p_close * price - 1.0,
                           won(m, market, sel), moments.get(m.match_id)))  # fmt: skip
    return out


@dataclass
class Acc:
    """Somme sufficienti per media ed errore standard di CLV e rendimento."""

    n: int = 0
    clv: float = 0.0
    clv2: float = 0.0
    profit: float = 0.0
    profit2: float = 0.0

    def add(self, bet: Bet) -> None:
        self.n += 1
        self.clv += bet.clv
        self.clv2 += bet.clv * bet.clv
        self.profit += bet.profit
        self.profit2 += bet.profit * bet.profit

    def merge(self, other: "Acc") -> None:
        self.n += other.n
        self.clv += other.clv
        self.clv2 += other.clv2
        self.profit += other.profit
        self.profit2 += other.profit2

    @staticmethod
    def _estimate(n: int, s: float, s2: float) -> Estimate:
        mean = s / n
        if n < 2:
            return Estimate(mean, math.inf, n, n)
        var = max(s2 - n * mean * mean, 0.0) / (n - 1)
        return Estimate(mean, math.sqrt(var / n), n, n)

    def clv_estimate(self) -> Estimate:
        return self._estimate(self.n, self.clv, self.clv2)

    def roi_estimate(self) -> Estimate:
        return self._estimate(self.n, self.profit, self.profit2)


def _band_of(price: float) -> tuple[float, float] | None:
    return next((b for b in PRICE_BANDS if b[0] <= price < b[1]), None)


CellKey = tuple[str, str, str, tuple[float, float], str | None, bool]  # campionato, mercato, esito, fascia, momento, valore


def cells(items: Iterable[Bet]) -> dict[CellKey, Acc]:
    out: dict[CellKey, Acc] = defaultdict(Acc)
    for b in items:
        band = _band_of(b.price)
        if band is not None:
            out[(b.league, b.market, b.selection, band, b.moment, b.has_value)].add(b)
    return dict(out)


def evaluate(strategy: Strategy, table: Mapping[CellKey, Acc]) -> Acc:
    """Somma delle celle che la strategia gioca."""
    total = Acc()
    for (league, market, sel, band, moment, value), acc in table.items():
        if (
            (strategy.league in (ALL_LEAGUES, league))
            and (market, sel) == (strategy.market, strategy.selection)
            and band == strategy.band
            and (strategy.moment == WHOLE or moment == strategy.moment)
            and (strategy.filter == ALWAYS or value)
        ):
            total.merge(acc)
    return total


# --- Ricerca ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Result:
    strategy: Strategy
    tuning_n: int
    tuning_clv: Estimate | None
    tuning_roi: Estimate | None
    confirm_n: int
    confirm_clv: Estimate | None
    confirm_roi: Estimate | None
    candidate: bool = field(default=False)
    passed: bool = field(default=False)


def is_candidate(n: int, clv: Estimate | None) -> bool:
    return clv is not None and n >= MIN_PLAYS and clv.mean >= MIN_CLV and clv.t >= T_SCREEN


def is_confirmed(clv: Estimate | None) -> bool:
    return clv is not None and clv.n >= 2 and clv.t > T_CONFIRM


def search(strategies: Sequence[Strategy], tuning: Sequence[Bet], confirm: Sequence[Bet]) -> list[Result]:
    """Taratura → candidate (soglia severa) → conferma su stagioni separate (D118)."""
    t_table, c_table = cells(tuning), cells(confirm)
    out = []
    for s in strategies:
        t, c = evaluate(s, t_table), evaluate(s, c_table)
        t_clv = t.clv_estimate() if t.n else None
        c_clv = c.clv_estimate() if c.n else None
        candidate = is_candidate(t.n, t_clv)
        out.append(Result(s, t.n, t_clv, t.roi_estimate() if t.n else None, c.n, c_clv, c.roi_estimate() if c.n else None,
                          candidate, candidate and is_confirmed(c_clv)))  # fmt: skip
    return out


# --- Dal vivo -----------------------------------------------------------------------------------------------


def matching(strategies: Sequence[Strategy], league: str, market: str, selection: str, price: float, value: float,
             moment: str | None) -> Strategy | None:  # fmt: skip
    """La prima strategia confermata che giocherebbe questo esito, alla quota e al valore di adesso."""
    band = _band_of(price)
    for s in strategies:
        if (
            s.league in (ALL_LEAGUES, league)
            and (s.market, s.selection) == (market, selection)
            and s.band == band
            and (s.moment == WHOLE or s.moment == moment)
            and (s.filter == ALWAYS or value >= D72.required(price))
        ):
            return s
    return None
