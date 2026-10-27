"""Coppe europee (D146): un solo modello dei gol per tutti i campionati, collegati dalle partite di coppa.

Un modello per campionato non sa dire quanto vale la Serie A rispetto alla Scozia: i due campionati non si
incontrano mai. Le partite europee sono il ponte. Un unico Dixon-Coles su tutte le partite di campionato e di coppa
mette attacchi e difese di tutte le squadre sulla stessa scala.
"""

import math
from bisect import bisect_left
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.forecast.dixon_coles import DixonColesFit, fit_dixon_coles, score_matrix, time_decay_weights
from app.forecast.history_sim import Estimate, clustered_mean

XI = 0.002  # come il modello dei campionati
RIDGE = 8.0
WINDOW_DAYS = 3 * 365
MIN_LEAGUE_GAMES = 10  # partite di campionato minime di ciascuna squadra per studiare una partita di coppa
TUNING = (2023, 2024)
CONFIRMATION = (2025,)
MARKETS = ("1X2", "OU2.5", "GG", "TGH0.5", "TGA0.5")


def league_ids() -> list[int]:
    """Campionati del modello delle coppe (id di API-Football), gli stessi della prova D146."""
    from app.adapters.api_football import EAST_NORTH, MORE_TOP
    from app.forecast.study_backtest import COUNTRIES

    return [*(lg for leagues in COUNTRIES.values() for lg in leagues), *EAST_NORTH, *MORE_TOP]


@dataclass(frozen=True)
class R:
    """Una partita finita (risultato ai 90 minuti)."""

    id: int
    date: datetime
    season: int
    home: int
    away: int
    hg: int
    ag: int
    cup: bool
    final: bool = False  # finale di coppa: campo neutro


def league_games(games: Sequence[R], when: datetime) -> Counter:
    """Partite di campionato di ogni squadra negli ultimi 3 anni prima di `when`."""
    out: Counter = Counter()
    for g in games:
        if not g.cup and when - timedelta(days=WINDOW_DAYS) <= g.date < when:
            out[g.home] += 1
            out[g.away] += 1
    return out


def joint_fit(games: Sequence[R], when: datetime, with_cups: bool = True) -> DixonColesFit | None:
    """Il modello di tutti i campionati insieme con le sole partite prima di `when`; con le coppe se `with_cups`.
    Le finali (campo neutro) non entrano: il fattore campo lì non c'è."""
    train = [g for g in games if when - timedelta(days=WINDOW_DAYS) <= g.date < when and (with_cups or not g.cup) and not g.final]
    if not train:
        return None
    return fit_dixon_coles(
        [g.home for g in train], [g.away for g in train], [g.hg for g in train], [g.ag for g in train],
        weights=time_decay_weights([g.date for g in train], when, XI), ridge=RIDGE,
    )  # fmt: skip


def probabilities(lam: float, mu: float, rho: float) -> dict[str, dict[str, float]]:
    m = score_matrix(lam, mu, rho)
    n = m.shape[0]
    p1 = sum(m[i, j] for i in range(n) for j in range(n) if i > j)
    px = sum(m[i, i] for i in range(n))
    over = sum(m[i, j] for i in range(n) for j in range(n) if i + j > 2)
    gg = 1 - m[0, :].sum() - m[:, 0].sum() + m[0, 0]
    h0, a0 = m[0, :].sum(), m[:, 0].sum()
    return {
        "1X2": {"1": p1, "X": px, "2": 1 - p1 - px},
        "OU2.5": {"over": over, "under": 1 - over},
        "GG": {"yes": gg, "no": 1 - gg},
        "TGH0.5": {"over": 1 - h0, "under": h0},
        "TGA0.5": {"over": 1 - a0, "under": a0},
    }


def outcome(market: str, g: R) -> str:
    if market == "1X2":
        return "1" if g.hg > g.ag else "X" if g.hg == g.ag else "2"
    if market == "OU2.5":
        return "over" if g.hg + g.ag > 2 else "under"
    if market == "GG":
        return "yes" if g.hg and g.ag else "no"
    goals = g.hg if market == "TGH0.5" else g.ag
    return "over" if goals else "under"


def match_loss(fit: DixonColesFit, g: R) -> float:
    probs = probabilities(*fit.expected_goals(g.home, g.away), fit.rho)
    return -sum(math.log(max(probs[mk][outcome(mk, g)], 1e-9)) for mk in MARKETS)


@dataclass(frozen=True)
class Row:
    season: int
    match_id: int
    unlinked: float  # log loss del modello A (campionati scollegati)
    linked: float  # log loss del modello B (collegati dalle coppe)


def cup_test(games: Sequence[R], seasons: Sequence[int], log=print) -> list[Row]:
    """Walk-forward settimanale sulle partite di coppa delle stagioni indicate (D146)."""
    games = sorted(games, key=lambda g: g.date)
    targets = [g for g in games if g.cup and not g.final and g.season in set(seasons)]
    rows = []
    if not targets:
        return rows
    week = targets[0].date.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=targets[0].date.weekday())
    dates = [g.date for g in targets]
    while week <= targets[-1].date:
        todo = targets[bisect_left(dates, week) : bisect_left(dates, week + timedelta(days=7))]
        counts = league_games(games, week) if todo else Counter()
        todo = [g for g in todo if counts[g.home] >= MIN_LEAGUE_GAMES and counts[g.away] >= MIN_LEAGUE_GAMES]
        if todo:
            a, b = joint_fit(games, week, with_cups=False), joint_fit(games, week, with_cups=True)
            for g in todo:
                if a and b and a.has_team(g.home) and a.has_team(g.away):
                    rows.append(Row(g.season, g.id, match_loss(a, g), match_loss(b, g)))
            log(f"{week:%Y-%m-%d}: {len(todo)} partite di coppa")
        week += timedelta(days=7)
    return rows


def improvement(rows: Sequence[Row], seasons: Sequence[int]) -> Estimate | None:
    """Quanto il modello collegato abbassa la log loss (positivo = meglio), partita per partita."""
    chosen = [r for r in rows if r.season in set(seasons)]
    if len(chosen) < 2:
        return None
    return clustered_mean([r.unlinked - r.linked for r in chosen], [r.match_id for r in chosen])


def passed(tuning: Estimate | None, confirmation: Estimate | None) -> bool:
    return bool(tuning and confirmation and tuning.mean > 2 * tuning.std_error and confirmation.mean > 2 * confirmation.std_error)


def from_fixtures(fixtures, cup: bool) -> list[R]:
    """Partite finite di un elenco di API-Football (assegnate a tavolino escluse); in una coppa l'ultima è la finale."""
    done = [f for f in fixtures if f.status == "finished" and f.status_short not in ("AWD", "WO") and f.home_goals is not None]
    last = max((f.kickoff_at for f in done), default=None)
    return [R(f.id, f.kickoff_at, f.season, f.home.id, f.away.id, f.home_goals, f.away_goals, cup, cup and f.kickoff_at == last) for f in done]
