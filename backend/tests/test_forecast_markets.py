"""Mercati dalla matrice dei risultati: valori attesi calcolati a mano su una matrice piccola."""

import numpy as np
import pytest

from app.forecast.dixon_coles import score_matrix
from app.forecast.markets import fair_price, markets, outcome_1x2, value

# Righe = gol casa (0..2), colonne = gol fuori (0..2)
TOY = np.array(
    [
        [0.10, 0.08, 0.02],  # 0-0, 0-1, 0-2
        [0.20, 0.15, 0.05],  # 1-0, 1-1, 1-2
        [0.20, 0.12, 0.08],  # 2-0, 2-1, 2-2
    ]
)


def test_1x2_by_hand():
    assert outcome_1x2(TOY) == pytest.approx({"1": 0.20 + 0.20 + 0.12, "X": 0.10 + 0.15 + 0.08, "2": 0.08 + 0.02 + 0.05})


def test_all_markets_by_hand():
    mk = markets(TOY)
    assert mk["DC"] == pytest.approx({"1X": 0.85, "X2": 0.48, "12": 0.67})
    # Under 2.5 = risultati con al massimo 2 gol: 0-0, 0-1, 0-2, 1-0, 1-1, 2-0
    assert mk["OU2.5"]["under"] == pytest.approx(0.10 + 0.08 + 0.02 + 0.20 + 0.15 + 0.20)
    assert mk["OU0.5"]["under"] == pytest.approx(0.10)
    assert mk["OU4.5"]["over"] == pytest.approx(0.0, abs=1e-12)
    # NoGoal = almeno una squadra a zero: prima riga + prima colonna − 0-0 contato due volte
    assert mk["GG"]["no"] == pytest.approx(0.10 + 0.08 + 0.02 + 0.20 + 0.20)


def test_markets_are_consistent_on_a_model_matrix():
    mk = markets(score_matrix(1.6, 1.1, -0.08))
    for name, probs in mk.items():
        if name != "DC":
            assert sum(probs.values()) == pytest.approx(1.0), name
    assert mk["DC"]["1X"] == pytest.approx(1 - mk["1X2"]["2"])
    # Le linee Over sono in ordine decrescente
    overs = [mk[f"OU{x}"]["over"] for x in (0.5, 1.5, 2.5, 3.5, 4.5)]
    assert overs == sorted(overs, reverse=True)


def test_fair_price_and_value():
    assert fair_price(0.5) == pytest.approx(2.0)
    assert fair_price(0.0) is None
    assert value(0.5, 2.2) == pytest.approx(0.10)
    assert value(0.25, 3.6) == pytest.approx(-0.10)
