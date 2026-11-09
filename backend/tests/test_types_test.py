"""D178: presi contro attesi per tipo e fascia, con l'errore standard per partita."""

import math
from datetime import UTC, datetime

import pytest

from app.forecast import study_backtest as bt
from app.forecast import types_test as tt


def game(gid: int, hg: int, ag: int) -> bt.G:
    return bt.G(gid, datetime(2024, 3, 2, 15, tzinfo=UTC), 135, 2023, 1, 2, hg, ag, 0, 0, None, None)


def pick(market: str, selection: str, p: float, price: float | None = None) -> dict:
    return {"market": market, "selection": selection, "p_archie": p, "prices": {"sisal": price} if price else {}}


def test_band_label_edges():
    assert tt.band_label(1.39) is None
    assert tt.band_label(1.40) == "1.40-1.50"
    assert tt.band_label(1.50) == "1.50-1.80"
    assert tt.band_label(2.9999) == "2.20-3.00"
    assert tt.band_label(3.0) is None


def test_rows_use_real_price_or_fair_minus_margin():
    studies = [{"id": 1, "picks": [pick("1X2", "1", 0.5, 2.0), pick("OU2.5", "over", 0.6), pick("OU1.5", "over", 0.9)]}]
    out = tt.rows(studies, [game(1, 2, 1)])
    # 1X2 a quota vera 2,00; Over 2.5 a 0,94/0,6 = 1,57; Over 1.5 a 1,04: fuori dalle fasce
    assert [(r["market"], r["band"], r["won"], r["real_price"]) for r in out] == [("1X2", "1.80-2.20", True, 2.0), ("OU2.5", "1.50-1.80", True, None)]


def test_rows_skip_matches_without_result():
    assert tt.rows([{"id": 9, "picks": [pick("1X2", "1", 0.5, 2.0)]}], [game(1, 1, 0)]) == []


def test_cell_counts_and_cluster_standard_error():
    data = [
        {"match_id": 1, "family": "a", "p": 0.5, "won": True, "real_price": 2.0},
        {"match_id": 1, "family": "a", "p": 0.5, "won": True, "real_price": None},
        {"match_id": 2, "family": "a", "p": 0.5, "won": False, "real_price": 2.0},
        {"match_id": 3, "family": "a", "p": 0.5, "won": False, "real_price": 2.0},
    ]
    c = tt.cells(data, lambda r: r["family"])["a"]
    assert (c.n, c.matches, c.won, c.expected, c.real_n) == (4, 3, 2, 2.0, 3)
    assert c.gap == 0.0 and c.z == 0.0
    # contributi per partita: +1, −0,5, −0,5 → media 0, somma dei quadrati 1,5, errore standard √(3/2 × 1,5) = 1,5
    assert tt._cluster_se([1.0, -0.5, -0.5]) == pytest.approx(1.5)
    # quota vera: +1, −1, −1 → rendimento −1/3; errore standard √(3/2 × 8/3) / 3 = 2/3
    assert c.real_roi == pytest.approx(-1 / 3)
    assert c.real_se == pytest.approx(2 / 3)


def test_correlated_picks_do_not_inflate_certainty():
    """Dieci pronostici uguali nella stessa partita valgono quanto uno: lo z non cresce."""
    one = [{"match_id": m, "family": "a", "p": 0.7, "won": m % 2 == 0, "real_price": None} for m in range(40)]
    ten = [r for r in one for _ in range(10)]
    z1, z10 = tt.cells(one, lambda r: r["family"])["a"].z, tt.cells(ten, lambda r: r["family"])["a"].z
    assert z10 == pytest.approx(z1)
    assert math.isfinite(z1) and z1 < -2


def cell(z: float, gap: float) -> tt.Cell:
    return tt.Cell("x", 100, 100, 0, 0.0, gap, z, 0, None, None)


def test_is_wrong_needs_both_seasons_and_both_thresholds():
    assert tt.is_wrong(cell(-2.5, -0.03), cell(-2.1, -0.02))
    assert not tt.is_wrong(cell(-2.5, -0.03), cell(-1.9, -0.03))  # la conferma non arriva a 2 errori standard
    assert not tt.is_wrong(cell(-2.5, -0.03), cell(-3.0, -0.01))  # scarto troppo piccolo per contare
    assert not tt.is_wrong(cell(2.5, 0.03), cell(2.5, 0.03))  # troppo prudente non è "sbagliata"
    assert not tt.is_wrong(cell(-2.5, -0.03), None)
