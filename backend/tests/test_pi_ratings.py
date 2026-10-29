import math

import pytest

from app.forecast.pi_ratings import CROSS, LEARNING, PiRatings, psi


def test_psi_is_symmetric_and_zero_at_zero():
    assert psi(0.0) == 0.0
    assert psi(3.0) == pytest.approx(9.0) and psi(-3.0) == pytest.approx(-9.0)


def test_update_by_hand():
    r = PiRatings()
    assert r.state(1, 2).expected_diff == 0.0
    r.update(1, 2, 2, 0)  # attese 0, finita 2-0: errore 2
    step = 3 * math.log10(3) * LEARNING
    assert r.home[1] == pytest.approx(step) and r.away[1] == pytest.approx(step * CROSS)
    assert r.away[2] == pytest.approx(-step) and r.home[2] == pytest.approx(-step * CROSS)


def test_a_dominant_team_rises():
    r = PiRatings()
    for _ in range(30):
        r.update(1, 2, 3, 0)
        r.update(2, 1, 0, 2)
    s = r.state(1, 2)
    assert s.expected_diff > 1.0 and s.home_h > 0 > s.away_a
