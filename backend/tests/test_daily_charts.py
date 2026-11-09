"""Grafici della bacheca e utile con il margine (D173): schedine costruite a mano, valori calcolati a mano."""

from types import SimpleNamespace

import pytest

from app.forecast.daily import board_charts, net_prices, stats


def leg(status: str, p: float, price: float) -> dict:
    return {"status": status, "p": p, "price": price}


def slip(kind: str, period: str, status: str, *legs: dict) -> SimpleNamespace:
    return SimpleNamespace(kind=kind, period=period, status=status, legs=list(legs), total_odds=2.0, win_probability=0.5)


SLIPS = [
    slip("giorno", "2026-10-30", "won", leg("won", 0.5, 2.0)),  # quota giusta (1/0,5): col margine 1,88
    slip("giorno", "2026-11-01", "lost", leg("lost", 0.6, 1.9)),  # quota vera: -1
    slip("clv", "2026-11-01", "done", leg("won", 0.4, 3.0), leg("lost", 0.4, 3.0)),  # singole: +2 e -1
    slip("giorno", "2026-11-02", "open", leg("open", 0.5, 2.0)),  # aperta: fuori dai grafici
]


def test_only_a_fair_price_loses_the_margin():
    assert [x["price"] for x in net_prices([leg("won", 0.5, 2.0), leg("won", 0.5, 2.2)], 0.06)] == pytest.approx([1.88, 2.2])


def test_a_fair_price_never_drops_below_one():
    assert net_prices([leg("won", 0.98, 1.02)], 0.06)[0]["price"] == 1.0


def test_stats_use_the_margin_only_when_asked():
    assert stats(SLIPS)["giorno"].profit == pytest.approx(1.0 - 1.0)
    assert stats(SLIPS, 0.06)["giorno"].profit == pytest.approx(0.88 - 1.0)


def test_the_balance_is_cumulative_and_leaves_open_slips_out():
    days = board_charts(SLIPS, 0.06).days
    assert [d.day for d in days] == ["2026-10-30", "2026-11-01"]
    assert [d.profit for d in days] == pytest.approx([0.88, 0.0])  # -1 della persa, +2 -1 delle singole
    assert [d.cum_profit for d in days] == pytest.approx([0.88, 0.88])
    assert (days[1].bets, days[1].won) == (1, 0)  # le singole non sono né vinte né perse


def test_months_count_won_and_lost_slips():
    assert [(m.month, m.won, m.lost) for m in board_charts(SLIPS).months] == [("2026-10", 1, 0), ("2026-11", 0, 1)]


def test_bands_compare_hits_with_archies_probabilities():
    charts = board_charts(SLIPS)
    clv = next(b for b in charts.by_kind if b.label == "CLV")
    assert (clv.selections, clv.won, clv.hit_rate, clv.expected_rate) == (2, 1, 0.5, 0.4)
    low = next(b for b in charts.by_odds if b.label == "1,40 – 2,00")  # 1,90 persa
    assert (low.selections, low.won) == (1, 0)
    mid = next(b for b in charts.by_odds if b.label == "2,00 – 3,00")  # 2,00 vinta
    assert (mid.selections, mid.won) == (1, 1)
    assert next(b for b in charts.by_odds if b.label == "3,00 – 5,00").selections == 2
