"""Numeri di campionato: valori attesi calcolati a mano."""

from datetime import UTC, datetime, timedelta

from app.stats.league_stats import league_summary
from app.stats.team_stats import Result

T0 = datetime(2024, 9, 1, tzinfo=UTC)


def game(i: int, hg: int, ag: int) -> Result:
    return Result(match_id=i, kickoff_at=T0 + timedelta(days=i), home_id=100 + i, away_id=200 + i, home_goals=hg, away_goals=ag)


def test_league_summary():
    # 2-1 (1, over, goal), 0-0 (X, 0-0), 1-3 (2, over, goal), 1-0 (1)
    s = league_summary([game(0, 2, 1), game(1, 0, 0), game(2, 1, 3), game(3, 1, 0)])
    assert s.matches == 4
    assert (s.home_win, s.draw, s.away_win) == (0.5, 0.25, 0.25)
    assert s.goals_per_match == 2.0  # (3+0+4+1)/4
    assert (s.home_goals, s.away_goals) == (1.0, 1.0)  # casa 4/4, fuori 4/4
    assert s.over_2_5 == 0.5
    assert s.both_scored == 0.5
    assert s.nil_nil == 0.25
    assert s.home_points_per_game == 1.75  # (3+1+0+3)/4
    assert s.away_points_per_game == 1.0  # (0+1+3+0)/4


def test_league_summary_shares_add_up():
    s = league_summary([game(i, i % 3, (i * 2) % 3) for i in range(30)])
    assert abs(s.home_win + s.draw + s.away_win - 1) < 0.002


def test_empty_league():
    s = league_summary([])
    assert s.matches == 0 and s.home_win is None and s.goals_per_match is None
