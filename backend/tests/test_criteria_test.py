import math
from datetime import UTC, datetime, timedelta

import pytest

from app.forecast import study_backtest as bt
from app.forecast.criteria_test import Row, Weights, factors, fit, motivation_flags, row_loss
from app.forecast.player_weight import LineupChange

T0 = datetime(2024, 8, 1, tzinfo=UTC)


def g(i, day, home, away, hg, ag, league=135, season=2024):
    return bt.G(i, T0 + timedelta(days=day), league, season, home, away, hg, ag, 0, 0, None, None)


def row(game, lineup=(None, None), motivated=(0, 0), bad=None):
    hits = bt.field_hits([], [])
    p = bt.Prepared(game, (1.4, 1.1, 0.0), (1.4, 1.1, 0.0), None, (0.45, 0.45), hits, (False, False), (False, False), (0.0, 0.0))
    return Row(p, 1.4, 1.1, 0.0, lineup, motivated, bad)


def test_factors_combine_every_criterion():
    r = row(g(1, 0, 1, 2, 1, 0), (LineupChange(-0.2, -0.1, (), ()), None), (1, 0), 1)
    fh, fa = factors(r, Weights(a=0.5, b=1.0, c=0.4, m=0.03, w=-0.04))
    assert fh == pytest.approx(math.exp(0.5 * -0.2 + 1.0 * -0.1 + 0.03 - 0.04))
    assert fa == pytest.approx(math.exp(-0.4 * -0.1 - 0.04))  # l'avversaria più debole fa segnare di più
    assert factors(r, Weights()) == (1.0, 1.0)


def test_motivation_uses_only_games_already_played():
    games = [g(i, i, 1 + i % 6, 1 + (i + 1) % 6, 1, 0) for i in range(60)]
    flags = motivation_flags(games)
    assert flags[0] == (0, 0)  # alla prima giornata non c'è classifica
    assert set(flags) == {x.id for x in games}


def test_fit_moves_weight_in_the_direction_of_the_data():
    # quando l'attacco dei titolari cala la squadra di casa non segna: il peso stimato deve essere positivo
    rows = []
    for i in range(80):
        weak = i % 2 == 0
        game = g(i, i, 1, 2, 0 if weak else 3, 1)
        rows.append(row(game, (LineupChange(-0.5 if weak else 0.0, 0.0, (), ()), None)))
    x = fit(rows, ("a",))
    assert x.a > 0.5
    assert sum(row_loss(r, x) for r in rows) < sum(row_loss(r, Weights()) for r in rows)


def test_bands_split_outcomes_by_fair_odds():
    from app.forecast.criteria_test import bands

    found = bands([row(g(i, i, 1, 2, i % 3, 1)) for i in range(30)])
    assert [b.name.split()[0] for b in found] == ["bassa", "media", "alta"]
    assert sum(b.n for b in found) == 30 * sum(len(v) for v in bt.quick_probs(1.4, 1.1, 0.0, 0.45, 0.45).values())
    assert all(0 <= b.observed <= 1 and 0 < b.predicted < 1 for b in found)


def test_recalibration_sharpens_and_keeps_sums():
    from app.forecast.criteria_test import recalibrate

    out = recalibrate({"OU2.5": {"over": 0.7, "under": 0.3}}, 2.0)["OU2.5"]
    assert out["over"] == pytest.approx(0.49 / 0.58) and sum(out.values()) == pytest.approx(1.0)
    assert recalibrate({"m": {"a": 0.6, "b": 0.4}}, 1.0) == {"m": {"a": 0.6, "b": 0.4}}
