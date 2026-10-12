"""Rating Elo: ogni valore atteso è calcolato a mano."""

from datetime import datetime, timedelta

import pytest

from app.forecast.data import Game
from app.forecast.elo import EloParams, expected_home, goal_multiplier, run_elo

T0 = datetime(2023, 8, 20)
E_EVEN = 1 / (1 + 10 ** (-60 / 400))  # 0,585499: rating pari, 60 punti di fattore campo


def game(day, season, tier, home, away, hg, ag):
    return Game(0, tier, T0 + timedelta(days=day), season, tier, home, away, hg, ag)


def test_expected_home_by_hand():
    assert expected_home(1500, 1500, 60) == pytest.approx(0.585499, abs=1e-6)
    assert expected_home(1500, 1500, 0) == pytest.approx(0.5)
    assert expected_home(1600, 1500, 0) == pytest.approx(1 / (1 + 10 ** (-0.25)))


@pytest.mark.parametrize(("diff", "g"), [(0, 1.0), (1, 1.0), (-1, 1.0), (2, 1.5), (3, 1.75), (-4, 15 / 8)])
def test_goal_multiplier(diff, g):
    assert goal_multiplier(diff) == pytest.approx(g)


def test_single_game_update_by_hand():
    res = run_elo([game(0, "2023/24", 1, 1, 2, 2, 0)])
    delta = 20 * 1.5 * (1 - E_EVEN)  # 12,435
    assert res.pre_match == [(1500, 1500)]
    assert res.ratings[1] == pytest.approx(1500 + delta)
    assert res.ratings[2] == pytest.approx(1500 - delta)


def test_draw_moves_rating_towards_the_away_side():
    res = run_elo([game(0, "2023/24", 1, 1, 2, 1, 1)])
    assert res.ratings[1] == pytest.approx(1500 + 20 * (0.5 - E_EVEN))
    assert res.ratings[1] + res.ratings[2] == pytest.approx(3000)  # a somma zero


def test_pre_match_rating_never_includes_the_match_itself():
    games = [game(0, "2023/24", 1, 1, 2, 3, 0), game(7, "2023/24", 1, 2, 1, 0, 0)]
    res = run_elo(games)
    after_first = run_elo(games[:1]).ratings
    assert res.pre_match[1] == (pytest.approx(after_first[2]), pytest.approx(after_first[1]))


def test_newcomer_starts_below_last_season_average():
    games = [
        game(0, "2023/24", 2, 1, 2, 2, 0),
        game(300, "2024/25", 2, 3, 1, 0, 0),  # la squadra 3 non si è mai vista
    ]
    res = run_elo(games)
    assert res.pre_match[1][0] == pytest.approx(1350 - 50)  # media B 2023/24 = 1350 (somma zero)


def test_promoted_team_keeps_its_rating():
    games = [
        game(0, "2023/24", 2, 1, 2, 2, 0),
        game(300, "2024/25", 1, 1, 9, 0, 0),  # la 1 vince la B e sale in A
    ]
    first = run_elo(games[:1]).ratings[1]
    res = run_elo(games)
    assert res.pre_match[1][0] == pytest.approx(first)
    assert res.pre_match[1][1] == pytest.approx(1500)  # la A non ha stagioni chiuse: valore base


def test_season_regression_towards_tier_average():
    games = [game(0, "2023/24", 1, 1, 2, 4, 0), game(300, "2024/25", 1, 1, 2, 0, 0)]
    end = run_elo(games[:1]).ratings[1]
    res = run_elo(games, EloParams(season_regression=0.5))
    assert res.pre_match[1][0] == pytest.approx(end + 0.5 * (1500 - end))


def test_unsorted_games_are_rejected():
    with pytest.raises(ValueError, match="ordine"):
        run_elo([game(5, "2023/24", 1, 1, 2, 0, 0), game(0, "2023/24", 1, 2, 1, 0, 0)])
