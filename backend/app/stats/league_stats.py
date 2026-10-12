"""Numeri di un campionato (Laboratorio). Funzioni pure su partite finite: i numeri li calcola il codice."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.stats.team_stats import Result


@dataclass(frozen=True)
class LeagueSummary:
    matches: int
    home_win: float | None  # quota di partite finite 1 (0-1)
    draw: float | None
    away_win: float | None
    goals_per_match: float | None
    home_goals: float | None  # media gol della squadra di casa
    away_goals: float | None
    over_2_5: float | None
    both_scored: float | None
    nil_nil: float | None  # quota di 0-0
    home_points_per_game: float | None
    away_points_per_game: float | None


def _share(count: int, total: int) -> float | None:
    return round(count / total, 3) if total else None


def _avg(total: float, n: int) -> float | None:
    return round(total / n, 2) if n else None


def league_summary(results: Sequence[Result]) -> LeagueSummary:
    n = len(results)
    home_wins = sum(r.home_goals > r.away_goals for r in results)
    draws = sum(r.home_goals == r.away_goals for r in results)
    away_wins = n - home_wins - draws
    return LeagueSummary(
        matches=n,
        home_win=_share(home_wins, n),
        draw=_share(draws, n),
        away_win=_share(away_wins, n),
        goals_per_match=_avg(sum(r.home_goals + r.away_goals for r in results), n),
        home_goals=_avg(sum(r.home_goals for r in results), n),
        away_goals=_avg(sum(r.away_goals for r in results), n),
        over_2_5=_share(sum(r.home_goals + r.away_goals >= 3 for r in results), n),
        both_scored=_share(sum(r.home_goals > 0 and r.away_goals > 0 for r in results), n),
        nil_nil=_share(sum(r.home_goals == 0 and r.away_goals == 0 for r in results), n),
        home_points_per_game=_avg(3 * home_wins + draws, n),
        away_points_per_game=_avg(3 * away_wins + draws, n),
    )
