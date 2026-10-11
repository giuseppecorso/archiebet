"""Statistiche di squadra: ogni valore atteso è calcolato a mano nei commenti."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.stats.team_stats import Result, form, head_to_head, standings, summary

A, B, C, D = 1, 2, 3, 4
T0 = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)


def game(i: int, home: int, away: int, hg: int, ag: int, **stats) -> Result:
    return Result(match_id=i, kickoff_at=T0 + timedelta(days=7 * i), home_id=home, away_id=away, home_goals=hg, away_goals=ag, **stats)


# Giornate: 0) A-B 2-0  1) C-A 1-1  2) A-D 0-3  3) B-A 1-2
GAMES = [
    game(0, A, B, 2, 0, home_shots=15, away_shots=5, home_xg=Decimal("1.8"), away_xg=Decimal("0.4")),
    game(1, C, A, 1, 1, home_shots=10, away_shots=8, home_xg=Decimal("1.2"), away_xg=Decimal("0.9")),
    game(2, A, D, 0, 3),
    game(3, B, A, 1, 2, home_shots=9, away_shots=12),
]
AFTER_ALL = T0 + timedelta(days=100)


def test_outcome_and_points():
    g = GAMES[3]  # B-A 1-2
    assert (g.outcome(A), g.points(A)) == ("V", 3)
    assert (g.outcome(B), g.points(B)) == ("P", 0)
    with pytest.raises(ValueError):
        g.outcome(C)


def test_form_most_recent_first():
    assert [o for o, _ in form(GAMES, A, AFTER_ALL)] == ["V", "P", "N", "V"]
    assert [o for o, _ in form(GAMES, A, AFTER_ALL, n=2)] == ["V", "P"]


def test_no_data_from_the_future():
    # Prima della giornata 2 la squadra A ha giocato solo le giornate 0 e 1
    before_round_2 = GAMES[2].kickoff_at
    assert [o for o, _ in form(GAMES, A, before_round_2)] == ["N", "V"]
    assert summary(GAMES, A, before_round_2).played == 2
    # La partita che inizia esattamente a quell'ora non è "prima"
    assert GAMES[2] not in [r for _, r in form(GAMES, A, before_round_2)]


def test_summary_all_games():
    s = summary(GAMES, A, AFTER_ALL)
    assert s.played == 4
    assert s.points_per_game == 1.75  # (3+1+0+3)/4
    assert s.goals_for == 1.25  # (2+1+0+2)/4
    assert s.goals_against == 1.25  # (0+1+3+1)/4
    assert s.shots_for == 11.67  # (15+8+12)/3: la giornata 2 non ha tiri
    assert s.xg_for == 1.35  # (1.8+0.9)/2
    assert s.xg_against == 0.8  # (0.4+1.2)/2
    assert s.clean_sheets == 0.25  # 1 partita su 4
    assert s.over_2_5 == 0.5  # gol totali 2, 2, 3, 3 → 2 partite su 4
    assert s.both_scored == 0.5  # 1-1 e 1-2


def test_summary_by_venue():
    home = summary(GAMES, A, AFTER_ALL, venue="home")  # A-B 2-0, A-D 0-3
    assert (home.played, home.goals_for, home.goals_against) == (2, 1.0, 1.5)
    away = summary(GAMES, A, AFTER_ALL, venue="away")  # C-A 1-1, B-A 1-2
    assert (away.played, away.points_per_game, away.both_scored) == (2, 2.0, 1.0)


def test_summary_without_games():
    s = summary(GAMES, C, T0)
    assert s.played == 0 and s.goals_for is None and s.clean_sheets is None


def test_head_to_head_either_venue():
    h2h = head_to_head(GAMES, B, A, AFTER_ALL)
    assert [r.match_id for r in h2h] == [3, 0]


def test_standings_points_and_goals():
    table = standings(GAMES)
    # A: V N P V = 7 punti, 5-5. D: 1 V = 3 punti. C: 1 N = 1. B: 2 P = 0
    assert [row.team_id for row in table] == [A, D, C, B]
    a = table[0]
    assert (a.played, a.won, a.drawn, a.lost, a.points, a.goals_for, a.goals_against) == (4, 2, 1, 1, 7, 5, 5)
    assert a.form == ["V", "P", "N", "V"]


def test_standings_two_way_tie_broken_by_head_to_head():
    # A: V con B, N con D = 4 punti, diff. +1. B: P con A, V 4-0 con C, N con D = 4 punti, diff. +3.
    # Differenza reti migliore per B, ma A ha vinto lo scontro diretto → A davanti.
    games = [
        game(0, A, B, 1, 0),
        game(1, B, C, 4, 0),
        game(2, A, D, 0, 0),
        game(3, B, D, 0, 0),
    ]
    table = standings(games)
    assert [(row.team_id, row.points) for row in table[:2]] == [(A, 4), (B, 4)]


def test_standings_three_way_tie_uses_mini_league_goal_difference():
    # Ciclo: A-B 1-0, B-C 1-0, C-A 3-0. Tutte a 3 punti anche negli scontri diretti.
    # Differenza reti negli scontri diretti: C +2, B 0, A -2.
    games = [game(0, A, B, 1, 0), game(1, B, C, 1, 0), game(2, C, A, 3, 0)]
    assert [row.team_id for row in standings(games)] == [C, B, A]


def test_standings_mini_league_equal_then_overall_goal_difference():
    # Ciclo 1-0 (avulsa pari), poi tutte battono D: C 5-0, B 2-0, A 1-0 → tutte a 6 punti.
    # Differenza reti generale: C +5, B +2, A +1.
    games = [
        game(0, A, B, 1, 0),
        game(1, B, C, 1, 0),
        game(2, C, A, 1, 0),
        game(3, C, D, 5, 0),
        game(4, B, D, 2, 0),
        game(5, A, D, 1, 0),
    ]
    assert [row.team_id for row in standings(games)] == [C, B, A, D]


def test_standings_before_excludes_later_games():
    table = standings(GAMES, before=GAMES[1].kickoff_at)  # solo A-B 2-0
    assert [(row.team_id, row.points) for row in table] == [(A, 3), (B, 0)]
