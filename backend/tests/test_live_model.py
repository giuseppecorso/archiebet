"""Termometro della speranza (D92): Poisson dei gol che restano, gol attesi dal mercato, schedina."""

import math

import pytest

from app.forecast.live import (
    LegState,
    bet_probability,
    fit_rates,
    leg_probability,
    outcome_probabilities,
    remaining_share,
    selection_probability,
)


def test_outcomes_sum_to_one_and_match_poisson():
    o = outcome_probabilities(1.5, 1.0)
    assert o["1"] + o["X"] + o["2"] == pytest.approx(1.0, abs=1e-9)
    assert o["X"] == pytest.approx(sum(math.exp(-2.5) * 1.5**k * 1.0**k / math.factorial(k) ** 2 for k in range(12)), abs=1e-6)
    # gol già segnati: a partita finita (nessun gol che resta) l'esito è certo
    done = outcome_probabilities(0.0, 0.0, 2, 1)
    assert (done["1"], done["over"], done["yes"]) == (1.0, 1.0, 1.0)


def test_fit_rates_reproduces_market_probabilities():
    target = outcome_probabilities(1.6, 0.9)
    lh, la = fit_rates(target["1"], target["2"], target["over"])
    assert (lh, la) == (pytest.approx(1.6, abs=0.01), pytest.approx(0.9, abs=0.01))


def test_remaining_share_through_the_match():
    assert remaining_share("NS", None) == 1.0
    assert remaining_share("1H", 0) == pytest.approx(1.0)
    assert remaining_share("HT", 45) == pytest.approx(0.55)
    assert remaining_share("2H", 67) == pytest.approx(0.55 * 23 / 45)
    assert remaining_share("2H", 93) == pytest.approx(0.55 * 3 / 45)  # recupero
    assert remaining_share("FT", 90) == 0.0
    assert remaining_share("ET", 105) == 0.0  # i supplementari non contano


def test_selection_probability_for_each_market():
    probs = {"1": 0.5, "X": 0.3, "2": 0.2, "over": 0.6, "yes": 0.55}
    assert selection_probability("DC", "1X", probs) == pytest.approx(0.8)
    assert selection_probability("DC", "12", probs) == pytest.approx(0.7)
    assert selection_probability("OU2.5", "under", probs) == pytest.approx(0.4)
    assert selection_probability("GG", "no", probs) == pytest.approx(0.45)


def test_leg_and_bet_probability():
    rates = (1.5, 1.1)
    before = LegState("1X2", "1", rates, "NS", None, 0, 0)
    leading = LegState("1X2", "1", rates, "2H", 80, 1, 0)
    assert leg_probability(leading) > leg_probability(before)  # in vantaggio a 10 minuti dalla fine
    won = LegState("OU2.5", "over", rates, "FT", 90, 2, 2, settled=True)
    lost = LegState("GG", "yes", rates, "FT", 90, 1, 0, settled=False)
    assert bet_probability([leading, won]) == pytest.approx(leg_probability(leading))
    assert bet_probability([leading, lost]) == 0.0
    assert bet_probability([LegState("1X2", "1", None, "NS", None, 0, 0)]) is None  # senza quote non si stima
