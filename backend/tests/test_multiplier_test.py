"""Prova D176: moltiplicatore da 6 a 10, con valori calcolati a mano."""

import pytest

from app.forecast import multiplier_test as mt


def row(match_id: int, price: float, sharp: float, day: str = "2024-10-05", selection: str = "1") -> dict:
    return {"match_id": match_id, "when": f"{day}T18:00:00+00:00", "market": "1X2", "selection": selection, "price": price, "sharp": sharp}


def test_a_slip_stays_inside_the_multiplier():
    rows = [row(1, 2.0, 0.5), row(2, 2.1, 0.5), row(3, 1.9, 0.5), row(4, 2.0, 0.48)]
    slip = mt.best_slip(rows, 3, "vicine")
    assert slip is not None and 6 <= (slip[0]["price"] * slip[1]["price"] * slip[2]["price"]) <= 10


def test_each_match_appears_once():
    rows = [row(1, 2.9, 0.34), row(1, 2.8, 0.35, selection="X"), row(2, 2.8, 0.35)]
    slip = mt.best_slip(rows, 2, "vicine")
    assert slip is not None and {r["match_id"] for r in slip} == {1, 2}


def test_no_slip_when_the_product_cannot_reach_six():
    assert mt.best_slip([row(1, 2.0, 0.5), row(2, 2.0, 0.5)], 2, "vicine") is None  # le quote sono fuori dalla fascia di 2 partite


def test_value_picks_the_best_price_against_pinnacle():
    rows = [row(1, 2.0, 0.5), row(2, 2.0, 0.53), row(3, 2.0, 0.54), row(4, 2.0, 0.5)]
    slip = mt.best_slip(rows, 3, "valore")
    assert slip is None or {r["match_id"] for r in slip} >= {2, 3}
    rows = [row(1, 2.1, 0.5), row(2, 2.1, 0.53), row(3, 2.1, 0.54), row(4, 2.1, 0.5)]
    assert {r["match_id"] for r in mt.best_slip(rows, 3, "valore")} >= {2, 3}


def test_a_single_at_eight_is_allowed():
    assert mt.best_slip([row(1, 8.0, 0.12)], 1, "vicine")[0]["match_id"] == 1
    assert mt.best_slip([row(1, 5.5, 0.17)], 1, "vicine") is None


def test_the_selection_never_reads_a_result():
    rows = [{**row(1, 8.0, 0.12)}]
    assert "won" not in mt.best_slip(rows, 1, "vicine")[0]


def test_payoff_multiplies_when_every_leg_wins():
    slip = [row(1, 2.0, 0.5), row(2, 4.0, 0.25)]
    wins = {(1, "1X2", "1"): True, (2, "1X2", "1"): True}
    assert mt.payoff(slip, wins) == pytest.approx(7.0)
    assert mt.payoff(slip, {**wins, (2, "1X2", "1"): False}) == -1.0


def test_payoff_is_none_without_a_result():
    assert mt.payoff([row(1, 2.0, 0.5)], {}) is None


def test_summary_counts_the_margin_paid():
    slips = {"a": [row(1, 8.0, 0.11)], "b": [row(2, 8.0, 0.11)]}
    line = mt.summarize(slips, {(1, "1X2", "1"): True, (2, "1X2", "1"): False})
    assert (line.n, line.won, line.expected, line.avg_multiplier) == (2, 1, 0.2, 8.0)
    assert line.fair_return == pytest.approx(8 * 0.11 - 1)
    assert line.roi == pytest.approx((7 - 1) / 2)


def test_paired_difference_uses_only_shared_days():
    a = {"d1": [row(1, 8.0, 0.1)], "d2": [row(2, 8.0, 0.1)]}
    b = {"d1": [row(3, 8.0, 0.1)], "d3": [row(4, 8.0, 0.1)]}
    results = {(1, "1X2", "1"): True, (2, "1X2", "1"): True, (3, "1X2", "1"): False, (4, "1X2", "1"): False}
    m, se, days = mt.paired_difference(a, b, results)
    assert (days, m, se) == (1, None, None)
