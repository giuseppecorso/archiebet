"""Prova dello studio sul passato (D140): calcoli veloci uguali allo studio, stanchezza, assenti, media con il campo."""

from datetime import datetime, timedelta

import pytest

from app.forecast import study, study_backtest as bt

DAY = datetime(2025, 3, 10, 20, 0)


def g(**kw) -> bt.G:
    base = dict(id=1, date=DAY, league=135, season=2024, home=1, away=2, hg=2, ag=1, hh=1, ha=0, xh=1.8, xa=0.9)
    base.update(kw)
    return bt.G(**base)


def test_quick_probs_equal_the_study():
    fast = bt.quick_probs(1.6, 1.1, -0.06, 0.45, 0.43)
    slow = study.model_probabilities(1.6, 1.1, -0.06, 0.45, 0.43)
    for market in bt.EVAL_MARKETS:
        for sel, p in fast[market].items():
            assert p == pytest.approx(slow[market][sel], abs=1e-9), (market, sel)


def test_match_loss_rewards_the_right_side():
    good = bt.quick_probs(2.5, 0.4, 0.0, 0.5, 0.5)  # casa favorita
    bad = bt.quick_probs(0.4, 2.5, 0.0, 0.5, 0.5)
    game = g(hg=3, ag=0, hh=2, ha=0)
    assert bt.match_loss(good, game) < bt.match_loss(bad, game)


def test_rest_flags_short_rest_and_european_away():
    calendar = {1: [(DAY - timedelta(days=3), True)], 2: [(DAY - timedelta(days=7), False)]}
    assert bt.rest_flags(g(), 1, calendar) == (True, True)  # 3 giorni prima, trasferta europea
    assert bt.rest_flags(g(), 2, calendar) == (False, False)
    assert bt.rest_flags(g(), 9, calendar) == (False, False)  # nessuna partita nota


def test_missing_share_counts_absent_contributors():
    past = [g(id=10, date=DAY - timedelta(days=7), contributions=({11: 4, 12: 2, 13: 0}, {})),
            g(id=11, date=DAY - timedelta(days=14), contributions=({11: 2}, {}))]  # fmt: skip
    today = g(starters=((12, 13, 14), ()))
    assert bt.missing_share(past, 1, today) == pytest.approx(6 / 8)  # il giocatore 11 (6 su 8) non è titolare
    assert bt.missing_share(past[:1], 1, g(starters=((11,), ()))) == pytest.approx(2 / 6)
    assert bt.missing_share([], 1, today) == 0.0  # troppo pochi gol per dirlo


def test_with_field_mixes_and_renormalizes():
    probs = {"OU2.5": {"over": 0.5, "under": 0.5}}
    mixed = bt.with_field(probs, {("OU2.5", "over"): (15, 20), ("OU2.5", "under"): (5, 20)}, 20)
    assert mixed["OU2.5"]["over"] == pytest.approx(0.625 / (0.625 + 0.375))
    assert sum(mixed["OU2.5"].values()) == pytest.approx(1)


def test_loss_applies_variants():
    p = bt.Prepared(g(), (1.5, 1.0, -0.05), (1.6, 1.0, -0.05), (1.9, 0.8), (0.45, 0.45),
                    {(m, s): (0, 0) for m in bt.EVAL_MARKETS for s in study.MARKETS[m].selections},
                    (True, False), (False, False), (0.3, 0.0))  # fmt: skip
    base = bt.loss(p, bt.Config())
    assert bt.loss(p, bt.Config(per_league=True)) != base
    assert bt.loss(p, bt.Config(xg_weight=0.5)) != base
    assert bt.loss(p, bt.Config(beta_short=-0.1)) != base
    assert bt.loss(p, bt.Config(gamma=-0.5)) != base
