"""Occasioni confermate dallo studio? (D152)

Un'occasione (regola D72) è una quota che paga più di quanto vale l'esito secondo Pinnacle. Qui si chiede se rendono
di più (CLV) quelle in cui anche lo studio di Archie crede nell'esito almeno quanto Pinnacle ("confermate") rispetto
a quelle in cui lo studio ci crede meno ("contraddette").
"""

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from app.forecast.bookmaker_test import study_probs
from app.forecast.history_sim import Estimate, Play, Rule, SimMatch, clustered_mean, occasions
from app.forecast.model import ModelConfig, fit_at

CONFIRMATION = "2025/26"  # stagione di conferma; quelle prima sono la taratura


@dataclass(frozen=True)
class Checked:
    play: Play
    p_study: float  # probabilità dello studio per l'esito
    p_fair: float  # probabilità di Pinnacle d'apertura senza margine

    @property
    def confirmed(self) -> bool:
        return self.p_study >= self.p_fair


def study_by_match(games_by_league: dict[str, Sequence], sims: Sequence[SimMatch], log: Callable[[str], None] = print) -> dict[int, dict]:
    """Probabilità dello studio per ogni partita simulata: modello dei gol del campionato ristimato ogni settimana
    con le sole partite precedenti (walk-forward, come D144)."""
    config = ModelConfig(elo_prior=False)
    out: dict[int, dict] = {}
    for league, games in games_by_league.items():
        targets = sorted((m for m in sims if m.league == league), key=lambda m: m.kickoff)
        if not targets:
            continue
        kickoffs = [g.kickoff_at for g in games]
        by_id = {g.match_id: g for g in games}
        week = targets[0].kickoff.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=targets[0].kickoff.weekday())
        i = 0
        while i < len(targets):
            todo = []
            while i < len(targets) and targets[i].kickoff < week + timedelta(days=7):
                todo.append(targets[i])
                i += 1
            if todo:
                fit = fit_at(games, kickoffs, week, config)
                for m in todo:
                    g = by_id.get(m.match_id)
                    if fit is not None and g is not None and fit.has_team(g.home_id) and fit.has_team(g.away_id):
                        out[m.match_id] = study_probs(*fit.expected_goals(g.home_id, g.away_id), fit.rho)
            week += timedelta(days=7)
        log(f"{league}: {sum(1 for m in targets if m.match_id in out)} partite studiate su {len(targets)}")
    return out


def check(sims: Iterable[SimMatch], study: dict[int, dict], rule: Rule = Rule("D72")) -> list[Checked]:
    """Le Occasioni D72 con la probabilità dello studio accanto (solo dove lo studio c'è)."""
    fair = {m.match_id: m.fair_open for m in sims}
    sims = list(sims)
    out = []
    for p in occasions(sims, rule):
        s = study.get(p.match_id)
        if s is not None and p.market in s:
            out.append(Checked(p, s[p.market][p.selection], fair[p.match_id][p.market][p.selection]))
    return out


@dataclass(frozen=True)
class Comparison:
    confirmed: Estimate | None
    contradicted: Estimate | None

    @property
    def difference(self) -> float | None:
        if not (self.confirmed and self.contradicted):
            return None
        return self.confirmed.mean - self.contradicted.mean

    @property
    def std_error(self) -> float | None:
        if not (self.confirmed and self.contradicted):
            return None
        return math.sqrt(self.confirmed.std_error**2 + self.contradicted.std_error**2)

    @property
    def passed(self) -> bool:
        d, se, c = self.difference, self.std_error, self.confirmed
        return bool(d is not None and se and d > 2 * se and c and c.mean > 2 * c.std_error)


def _clv(rows: Sequence[Checked]) -> Estimate | None:
    return clustered_mean([r.play.clv for r in rows], [r.play.match_id for r in rows]) if len(rows) >= 2 else None


def compare(rows: Iterable[Checked]) -> Comparison:
    rows = list(rows)
    return Comparison(_clv([r for r in rows if r.confirmed]), _clv([r for r in rows if not r.confirmed]))


def roi(rows: Sequence[Checked]) -> Estimate | None:
    return clustered_mean([r.play.profit for r in rows], [r.play.match_id for r in rows]) if len(rows) >= 2 else None


def split(rows: Iterable[Checked]) -> tuple[list[Checked], list[Checked]]:
    """(taratura, conferma)"""
    rows = list(rows)
    return [r for r in rows if r.play.season < CONFIRMATION], [r for r in rows if r.play.season == CONFIRMATION]
