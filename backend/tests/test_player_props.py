"""Tiri dei giocatori (D110)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.forecast.player_props import PlayerGame, build_player_rows, parse_players, prob_at_least, row_log_loss


def test_parse_players_counts_null_as_zero():
    body = {"response": [
        {"team": {"id": 1}, "players": [{"player": {"id": 10, "name": "Bomber"}, "statistics": [{"games": {"minutes": 90, "position": "F"}, "shots": {"total": 4, "on": 2}}]},
                                        {"player": {"id": 11, "name": "Riserva"}, "statistics": [{"games": {"minutes": None, "position": "M"}, "shots": {"total": None, "on": None}}]}]},
        {"team": {"id": 2}, "players": []},
    ]}  # fmt: skip
    rows = parse_players(body, 99, 135, 2025, datetime(2025, 9, 1, tzinfo=UTC), home_team=1)
    assert [(r.player, r.home, r.opponent, r.minutes, r.shots) for r in rows] == [(10, True, 2, 90, 4), (11, True, 2, 0, 0)]


def season_games():
    out, t = [], datetime(2025, 8, 20, tzinfo=UTC)
    for i in range(8):
        home, away = (1, 2) if i % 2 == 0 else (2, 1)
        for team, opp in ((home, away), (away, home)):
            shots = 3 if team == 1 else 1  # il centravanti della squadra 1 tira tanto
            out.append(PlayerGame(i, 135, 2025, t, team, opp, team == home, 100 + team, f"P{team}", "F", 90, shots, shots // 2))
        t += timedelta(days=7)
    return out


def test_rows_start_after_three_appearances_and_follow_the_player():
    rows = build_player_rows(season_games(), m=360)
    assert {r.fixture_id for r in rows} == {3, 4, 5, 6, 7}  # dalla quarta presenza
    bomber = [r for r in rows if r.player == 101]
    other = [r for r in rows if r.player == 102]
    assert all(b.mean_shots > o.mean_shots for b, o in zip(bomber, other))
    assert bomber[0].naive_shots == pytest.approx(3.0)


def test_probabilities_and_log_loss():
    assert prob_at_least(1, 1.0, None) == pytest.approx(1 - 2.718281828 ** -1)
    assert prob_at_least(2, 2.0, 5.0) < prob_at_least(1, 2.0, 5.0)
    row = build_player_rows(season_games(), m=360)[0]
    assert row_log_loss(row, 10.0, 10.0) > 0 and row_log_loss(row, None, None, naive=True) > 0


def test_outlook_for_an_upcoming_match():
    from app.forecast.player_props import outlook

    gs = season_games()
    nxt = gs[-1].kickoff + timedelta(days=7)
    out = outlook(gs, 999, 135, 2025, nxt, home=1, away=2)
    assert [o.player for o in out] == [101, 102]  # prima chi tira di più
    assert out[0].p_shot > out[0].p_two and 0 < out[0].p_on < 1
