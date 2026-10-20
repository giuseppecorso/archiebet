"""Ricalibrazione a due esiti: ritrova un fattore vero, ignora uno finto, usa solo le stagioni passate."""

import numpy as np
import pytest

from app.forecast.binary_model import BinaryRow, fit, predict, walk_forward_by_season


def synthetic(n=6000, seed=1):
    rng = np.random.default_rng(seed)
    p_open = rng.uniform(0.35, 0.65, n)
    rain = rng.uniform(0, 1, n)
    noise = rng.normal(0, 1, n)
    logit_true = np.log(p_open / (1 - p_open)) - 0.8 * rain  # la pioggia toglie davvero probabilità all'Over
    y = (rng.uniform(0, 1, n) < 1 / (1 + np.exp(-logit_true))).astype(float)
    return p_open, np.column_stack([rain, noise]), y


def test_fit_recovers_a_real_factor_and_ignores_noise():
    p, x, y = synthetic()
    a, b, beta_rain, beta_noise = fit(p, x, y)
    assert a == pytest.approx(1.0, abs=0.2)
    assert beta_rain == pytest.approx(-0.8, abs=0.2)
    assert abs(beta_noise) < 0.1


def test_without_features_market_stays_the_market():
    p = np.array([0.3, 0.5, 0.7] * 300)
    y = np.array([0, 1, 1, 0, 0, 1, 1, 0, 1] * 100, dtype=float)  # frequenze 0,33 / 0,33 / 0,67 circa
    theta = fit(p, np.zeros((len(p), 0)), y)
    assert predict(theta, np.array([0.5]), np.zeros((1, 0)))[0] == pytest.approx(0.5, abs=0.1)


def test_walk_forward_uses_only_past_seasons():
    rows = [BinaryRow(i, "2020/21" if i < 50 else "2021/22", i % 2, 0.5) for i in range(100)]
    out = walk_forward_by_season(rows, {}, ["2020/21", "2021/22"], n_features=1)
    assert set(out) == set(range(50, 100))  # la prima stagione non ha passato: niente previsioni
