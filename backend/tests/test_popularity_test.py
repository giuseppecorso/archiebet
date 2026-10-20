"""Tifo dei bookmaker: la regressione ritrova uno sconto vero sulle popolari e non lo inventa dove non c'è."""

import numpy as np
import pytest

from app.forecast.popularity_test import ValueRow, regress, value_rows


def synthetic(shade: float, n=8000, seed=2):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        p = rng.uniform(0.2, 0.7)
        popular = i % 5 == 0
        against = i % 5 == 1
        value = -0.05 + 0.02 * np.log(p / (1 - p)) + (shade if popular else 0) - (shade if against else 0) + rng.normal(0, 0.03)
        rows.append(ValueRow("2020/21", p, value, popular, against))
    return rows


def test_finds_a_real_shade():
    r = regress(synthetic(shade=-0.02))  # le popolari pagano il 2% in meno, le avversarie il 2% in più
    assert r.popular.estimate == pytest.approx(-0.02, abs=0.004)
    assert r.against_popular.estimate == pytest.approx(0.02, abs=0.004)
    assert r.confirmed


def test_no_shade_no_confirmation():
    r = regress(synthetic(shade=0.0))
    assert abs(r.popular.estimate) < 2.5 * r.popular.std_error
    assert not r.confirmed


def test_value_rows_flags():
    rows = value_rows("2024/25", "Inter", "Lecce", (0.70, 0.18, 0.12), (1.40, 5.0, 9.0))
    home, away = rows
    assert (home.popular, home.against_popular, away.popular, away.against_popular) == (True, False, False, True)
    assert home.value == pytest.approx(0.70 * 1.40 - 1)
    both = value_rows("2024/25", "Inter", "Juventus", (0.4, 0.3, 0.3), (2.5, 3.3, 3.3))
    assert not any(r.against_popular for r in both)  # popolare contro popolare: nessuna "avversaria"
