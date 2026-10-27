"""Dove sbaglia il bookmaker? (D144) Lo studio contro le quote medie prima della partita, campionato per campionato.

Per ogni partita: probabilità del modello dei gol del campionato (walk-forward settimanale) e probabilità della quota
media senza margine (football-data, prima della partita). Quando lo studio dà almeno 5 punti in più, si misura se
l'esito esce più spesso di quanto diceva la quota: "eccesso" = uscito (1/0) − probabilità della quota.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from app.forecast.dixon_coles import score_matrix
from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.model import ModelConfig, fit_at

GAP = 0.05  # lo studio deve dare almeno 5 punti in più della quota
TUNING = ("2023/24", "2024/25")
CONFIRMATION = ("2025/26",)
T_TUNING, T_CONFIRMATION = 3.0, 2.0  # 20 gruppi: soglia più severa in taratura
SELECTIONS = {"1X2": ("1", "X", "2"), "OU2.5": ("over", "under")}

_I, _J = np.meshgrid(np.arange(11), np.arange(11), indexing="ij")


def study_probs(lam: float, mu: float, rho: float) -> dict[str, dict[str, float]]:
    m = score_matrix(lam, mu, rho, 10)
    m = m / m.sum()
    p1, px = float(m[_I > _J].sum()), float(m[_I == _J].sum())
    over = float(m[(_I + _J) > 2.5].sum())
    return {"1X2": {"1": p1, "X": px, "2": 1 - p1 - px}, "OU2.5": {"over": over, "under": 1 - over}}


def fair(prices: dict[str, float]) -> dict[str, float]:
    """Probabilità senza margine, metodo proporzionale."""
    implied = {k: 1 / v for k, v in prices.items()}
    total = sum(implied.values())
    return {k: v / total for k, v in implied.items()}


def won(market: str, sel: str, hg: int, ag: int) -> bool:
    if market == "1X2":
        return sel == ("1" if hg > ag else "X" if hg == ag else "2")
    return (hg + ag > 2.5) == (sel == "over")


@dataclass(frozen=True)
class Case:
    """Un disaccordo: lo studio crede nell'esito più della quota."""

    match_id: int
    league: str
    season: str
    market: str
    selection: str
    p_study: float
    p_market: float
    price: float
    hit: bool

    @property
    def excess(self) -> float:
        return float(self.hit) - self.p_market


def disagreements(match_id: int, league: str, season: str, study: dict, odds: dict, hg: int, ag: int, gap: float = GAP) -> list[Case]:
    out = []
    for market, sels in SELECTIONS.items():
        prices = odds.get(market)
        if not prices or set(prices) != set(sels):
            continue
        market_p = fair(prices)
        for sel in sels:
            if study[market][sel] - market_p[sel] >= gap:
                out.append(Case(match_id, league, season, market, sel, study[market][sel], market_p[sel], prices[sel], won(market, sel, hg, ag)))
    return out


@dataclass
class Segment:
    league: str
    market: str
    tuning: Estimate | None
    confirmation: Estimate | None

    @property
    def passed(self) -> bool:
        t, c = self.tuning, self.confirmation
        return bool(t and c and t.mean > T_TUNING * t.std_error and c.mean > T_CONFIRMATION * c.std_error)


def _estimate(cases: Sequence[Case]) -> Estimate | None:
    return clustered_mean([c.excess for c in cases], [c.match_id for c in cases]) if len(cases) >= 2 else None


def segments(cases: Sequence[Case]) -> list[Segment]:
    groups: dict[tuple[str, str], list[Case]] = defaultdict(list)
    for c in cases:
        groups[(c.league, c.market)].append(c)
    return [Segment(league, market, _estimate([c for c in cs if c.season in TUNING]), _estimate([c for c in cs if c.season in CONFIRMATION]))
            for (league, market), cs in sorted(groups.items())]  # fmt: skip


def collect(games_by_league: dict[str, Sequence], odds: dict[int, dict], seasons: Iterable[str], log: Callable[[str], None] = print) -> list[Case]:
    """games_by_league: partite (Game, in ordine) di ogni campionato; odds: partita → mercato → esito → quota media."""
    seasons = set(seasons)
    config = ModelConfig(elo_prior=False)
    out = []
    for league, games in games_by_league.items():
        kickoffs = [g.kickoff_at for g in games]
        targets = [g for g in games if g.season in seasons]
        if not targets:
            continue
        week = targets[0].kickoff_at.replace(hour=0, minute=0, second=0, microsecond=0)
        while week <= targets[-1].kickoff_at:
            todo = [g for g in targets if week <= g.kickoff_at < week + timedelta(days=7)]
            if todo:
                fit = fit_at(games, kickoffs, week, config)
                for g in todo:
                    if fit is None or not (fit.has_team(g.home_id) and fit.has_team(g.away_id)) or g.match_id not in odds:
                        continue
                    study = study_probs(*fit.expected_goals(g.home_id, g.away_id), fit.rho)
                    out += disagreements(g.match_id, league, g.season, study, odds[g.match_id], g.home_goals, g.away_goals)
            week += timedelta(days=7)
        log(f"{league}: {sum(1 for c in out if c.league == league)} disaccordi")
    return out
