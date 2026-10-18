"""Metodi per togliere il margine: somma 1, ordine conservato, più margine tolto agli sfavoriti."""

import math

import pytest

from app.forecast.demargin import additive, compare_methods, odds_ratio, power, proportional, shin

ODDS = (1.40, 4.50, 8.50)  # favorita, pareggio, sfavorita: implicite 0,7143 + 0,2222 + 0,1176 = 1,0541


@pytest.mark.parametrize("method", [proportional, additive, power, shin, odds_ratio])
def test_probabilities_sum_to_one_and_keep_order(method):
    p = method(ODDS)
    assert sum(p) == pytest.approx(1.0)
    assert p[0] > p[1] > p[2]


def test_proportional_divides_by_total():
    total = 1 / 1.40 + 1 / 4.50 + 1 / 8.50
    assert proportional(ODDS)[2] == pytest.approx((1 / 8.50) / total)


@pytest.mark.parametrize("method", [power, shin, odds_ratio])
def test_longshot_loses_more_margin(method):
    """Favourite-longshot bias: rispetto al proporzionale, la sfavorita scende e la favorita sale."""
    prop, p = proportional(ODDS), method(ODDS)
    assert p[2] < prop[2]
    assert p[0] > prop[0]


def test_power_exponent_makes_sum_one():
    p = power((1.9, 1.9))
    assert p == pytest.approx((0.5, 0.5))  # mercato simmetrico: tutti i metodi danno 50/50
    assert shin((1.9, 1.9)) == pytest.approx((0.5, 0.5))


def test_no_margin_means_nothing_to_remove():
    fair = (2.0, 4.0, 4.0)  # implicite che sommano esattamente 1
    assert power(fair) == pytest.approx((0.5, 0.25, 0.25))
    assert shin(fair) == pytest.approx((0.5, 0.25, 0.25))


def test_additive_removes_the_same_amount():
    cut = (1 / 1.40 + 1 / 4.50 + 1 / 8.50 - 1) / 3
    assert additive(ODDS) == pytest.approx((1 / 1.40 - cut, 1 / 4.50 - cut, 1 / 8.50 - cut))
    # 0,990 + 0,083 + 0,0125 = 1,086: taglio 0,029 a testa, lo sfavorito (0,0125) andrebbe sotto zero → ripiego
    assert additive((1.01, 12.0, 80.0)) == pytest.approx(proportional((1.01, 12.0, 80.0)))


def test_odds_ratio_is_constant():
    p = odds_ratio(ODDS)
    ratios = [((1 / o) / (1 - 1 / o)) / (q / (1 - q)) for o, q in zip(ODDS, p)]
    assert ratios == pytest.approx([ratios[0]] * 3)


def test_compare_methods_paired_log_loss():
    rows = [((1.40, 4.50, 8.50), 0), ((1.40, 4.50, 8.50), 2), ((2.0, 3.4, 4.0), 1)]
    scores = {s.name: s for s in compare_methods(rows)}
    prop = scores["proporzionale"]
    expected = -sum(math.log(proportional(prices)[o]) for prices, o in rows) / 3
    assert prop.log_loss == pytest.approx(expected)
    assert prop.diff_vs_proportional == 0 and not prop.passes
    shin_s = scores["shin"]
    assert shin_s.diff_vs_proportional == pytest.approx(shin_s.log_loss - prop.log_loss)
    # Quote > 4: 4,50 e 8,50 nelle prime due partite = 4 esiti, uscito uno (l'8,50) → frequenza 1/4
    assert prop.longshot_observed == pytest.approx(0.25)
    p = proportional((1.40, 4.50, 8.50))
    assert prop.longshot_predicted == pytest.approx((p[1] + p[2]) / 2)
