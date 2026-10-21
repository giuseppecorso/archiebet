"""Modello dei numeri di squadra e prova degli stili (D108)."""

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.forecast.counts import CountGame, Row, build_rows, expected, fit_beta, fit_size, gain, nb_logpmf, nb_over, pre_match_ratios


def test_negative_binomial_is_a_distribution_with_the_right_mean():
    probs = [math.exp(nb_logpmf(y, 10.0, 8.0)) for y in range(200)]
    assert sum(probs) == pytest.approx(1.0)
    assert sum(y * p for y, p in enumerate(probs)) == pytest.approx(10.0)
    assert nb_over(9.5, 10.0, 8.0) == pytest.approx(sum(probs[10:]))


def games(n_seasons=2):
    out, t, mid = [], datetime(2020, 8, 1, tzinfo=UTC), 0
    for s in range(n_seasons):
        for rnd in range(10):
            for h, a in ((1, 2), (3, 4), (2, 3), (4, 1)):
                mid += 1
                corners = (8, 3) if h == 1 else (5, 4)  # la squadra 1 in casa fa tanti angoli
                out.append(CountGame(mid, "X", f"202{s}", t, h, a, {"corners": corners, "shots": (12, 9)}))
                t += timedelta(hours=1)
    return out


def test_ratios_use_only_the_past_and_skip_the_first_season():
    gs = games()
    ratios = pre_match_ratios(gs, "corners", k=4)
    assert all(g.match_id not in ratios for g in gs if g.season == "2020")  # serve solo da partenza
    second = [g for g in gs if g.season == "2021"]
    first = ratios[second[0].match_id]
    assert first.for_home == pytest.approx(1.0)  # nessuna partita giocata: tutto alla media
    late = ratios[second[-4].match_id]  # squadra 1 in casa a fine stagione
    assert late.for_home > 1.2  # ha fatto più angoli della media
    home, away = expected(late)
    assert home > away


def test_style_coefficient_is_found_when_present_and_gain_is_positive():
    rng = np.random.default_rng(1)
    rows = []
    for i in range(4000):
        style = (float(rng.normal(0, 0.3)), float(rng.normal(0, 0.3)))
        base = (5.0, 4.0)
        y = tuple(int(rng.poisson(b * math.exp(0.8 * s))) for b, s in zip(base, style))
        rows.append(Row(i, "S", y, base, style))
    size = fit_size(rows)
    beta = fit_beta(rows, size)
    assert size > 5  # senza lo stile una parte della varianza sembra dispersione in più
    assert beta == pytest.approx(0.8, abs=0.1)
    assert gain(rows, size, beta).mean() > 0


def test_build_rows_pairs_target_and_driver():
    rows = build_rows(games(), "corners", "shots", k=4)
    assert rows and all(len(r.style) == 2 for r in rows)
    assert rows[0].style == (0.0, 0.0)  # a inizio stagione nessuna forza: nessun incastro
