"""Simulatore partita (D115): le 10.000 simulazioni tornano con le probabilità esatte."""

import numpy as np
import pytest

from app.forecast.live import outcome_probabilities, remaining_share
from app.forecast.simulator import goal_minutes, simulate, state_share


def test_monte_carlo_matches_the_exact_probabilities():
    sim = simulate((1.6, 1.1), n=200_000, seed=1)
    exact = outcome_probabilities(1.6, 1.1)
    assert sim.p_home == pytest.approx(exact["1"], abs=0.005)
    assert sim.p_draw == pytest.approx(exact["X"], abs=0.005)
    assert sim.p_home + sim.p_draw + sim.p_away == pytest.approx(1.0)
    assert sim.avg_goals == pytest.approx((1.6, 1.1), abs=0.01)


def test_what_if_starts_from_minute_and_score():
    sim = simulate((1.6, 1.1), minute=70, score=(1, 0), n=100_000, seed=2)
    share = remaining_share("2H", 70)
    exact = outcome_probabilities(1.6 * share, 1.1 * share, 1, 0)
    assert sim.p_home == pytest.approx(exact["1"], abs=0.006)
    assert sim.remaining == pytest.approx((1.6 * share, 1.1 * share))
    assert all(e.minute > 70 for e in sim.sample)
    assert state_share(0) == 1.0 and state_share(90) == pytest.approx(remaining_share("2H", 90))


def test_goal_minutes_respect_the_halves():
    rng = np.random.default_rng(3)
    minutes = goal_minutes(rng, 20_000, 0)
    first = sum(m <= 45 for m in minutes) / len(minutes)
    assert first == pytest.approx(0.45, abs=0.01)
    assert all(1 <= m <= 90 for m in minutes)
    assert all(m > 60 for m in goal_minutes(rng, 50, 60))
