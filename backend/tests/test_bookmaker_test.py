"""Dove sbaglia il bookmaker (D144): disaccordi tra studio e quota, eccesso, gruppi che passano."""

import pytest

from app.forecast import bookmaker_test as bt


def test_fair_and_disagreements():
    odds = {"1X2": {"1": 2.0, "X": 3.4, "2": 4.0}, "OU2.5": {"over": 1.9, "under": 1.9}}
    market = bt.fair(odds["1X2"])
    assert sum(market.values()) == pytest.approx(1)
    study = {"1X2": {"1": market["1"] + 0.06, "X": market["X"] - 0.03, "2": market["2"] - 0.03}, "OU2.5": {"over": 0.52, "under": 0.48}}
    cases = bt.disagreements(1, "ITA-A", "2023/24", study, odds, 2, 0)
    assert [(c.market, c.selection) for c in cases] == [("1X2", "1")]  # solo dove lo studio crede di più di almeno 5 punti
    assert cases[0].hit and cases[0].excess == pytest.approx(1 - market["1"])


def test_segment_needs_both_phases():
    def case(season, hit, i):
        return bt.Case(i, "ITA-A", season, "OU2.5", "over", 0.6, 0.5, 2.0, hit)

    # Taratura: escono 90 su 100 contro il 50% della quota; conferma: 30 su 50
    cases = [case("2023/24", i < 90, i) for i in range(100)] + [case("2025/26", i < 30, 1000 + i) for i in range(50)]
    [seg] = bt.segments(cases)
    assert seg.tuning.mean == pytest.approx(0.40) and seg.confirmation.mean == pytest.approx(0.10)
    assert not seg.passed  # in conferma +10 punti su 50 casi non bastano (errore standard ~7 punti)
    strong = [case("2023/24", i < 90, i) for i in range(100)] + [case("2025/26", i < 45, 1000 + i) for i in range(50)]
    assert bt.segments(strong)[0].passed
