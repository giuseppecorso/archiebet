"""Calcoli delle giocate: ogni valore atteso è calcolato a mano."""

from decimal import Decimal as D

import pytest

from app.betting.calc import (
    LOST,
    OPEN,
    VOID,
    WON,
    bet_status,
    clv,
    fair_closing_odds,
    fair_odds,
    potential_payout,
    selection_outcome,
    settled_payout,
    total_odds,
)


@pytest.mark.parametrize(
    ("market", "pick", "score", "expected"),
    [
        ("1X2", "1", (2, 1), WON),
        ("1X2", "X", (2, 1), LOST),
        ("1X2", "X", (0, 0), WON),
        ("1X2", "2", (0, 3), WON),
        ("DC", "1X", (1, 1), WON),
        ("DC", "1X", (0, 1), LOST),
        ("DC", "X2", (0, 1), WON),
        ("DC", "12", (1, 1), LOST),
        ("DC", "12", (3, 2), WON),
        ("OU2.5", "over", (2, 1), WON),  # 3 gol
        ("OU2.5", "over", (1, 1), LOST),  # 2 gol
        ("OU2.5", "under", (1, 1), WON),
        ("OU2.5", "under", (0, 3), LOST),
        ("GG", "yes", (1, 1), WON),
        ("GG", "yes", (2, 0), LOST),
        ("GG", "no", (2, 0), WON),
        ("GG", "no", (0, 0), WON),
    ],
)
def test_selection_outcome(market, pick, score, expected):
    assert selection_outcome(market, pick, *score) == expected


def test_invalid_pick():
    with pytest.raises(ValueError):
        selection_outcome("1X2", "over", 1, 0)


def test_total_odds_and_payout():
    assert total_odds([D("1.85"), D("2.10"), D("1.50")]) == D("5.8275")  # 1,85 × 2,10 × 1,50
    assert potential_payout(D("10"), D("5.8275")) == D("58.28")  # arrotondato al centesimo
    with pytest.raises(ValueError):
        total_odds([D("1.00")])


def test_bet_status():
    assert bet_status([WON, WON]) == WON
    assert bet_status([WON, OPEN]) == OPEN
    assert bet_status([OPEN, LOST]) == LOST  # una persa chiude subito la schedina
    assert bet_status([WON, VOID]) == WON
    assert bet_status([VOID, VOID]) == VOID


def test_settled_payout():
    stake = D("10")
    assert settled_payout(stake, [(WON, D("2.00")), (WON, D("1.50"))]) == D("30.00")
    assert settled_payout(stake, [(WON, D("2.00")), (VOID, D("1.50"))]) == D("20.00")  # annullata = quota 1
    assert settled_payout(stake, [(VOID, D("2.00"))]) == D("10.00")  # rimborso
    assert settled_payout(stake, [(WON, D("2.00")), (LOST, D("1.50"))]) == D("0")
    with pytest.raises(ValueError):
        settled_payout(stake, [(OPEN, D("2.00"))])


def test_fair_odds_remove_margin():
    # 2.00 / 3.50 / 4.00 → probabilità 0.5 + 0.2857 + 0.25 = 1.0357 (margine 3,57%)
    fair = fair_odds({"1": D("2.00"), "X": D("3.50"), "2": D("4.00")})
    assert sum(1 / v for v in fair.values()) == pytest.approx(1)
    assert float(fair["1"]) == pytest.approx(2.0714, abs=1e-4)  # 2.00 × 1.0357


def test_fair_closing_for_double_chance():
    closing = {"1": D("2.00"), "X": D("3.50"), "2": D("4.00")}
    fair = fair_odds(closing)
    expected = 1 / (1 / fair["1"] + 1 / fair["X"])
    assert fair_closing_odds("DC", "1X", closing, None) == expected
    assert fair_closing_odds("GG", "yes", closing, None) is None  # niente quote per il Goal
    assert fair_closing_odds("OU2.5", "over", None, {"over": D("1.90"), "under": D("1.90")}) == D(2)


def test_clv():
    assert clv(D("2.10"), D("2.00")) == D("0.0500")  # presa a 2,10, giusta a 2,00: +5%
    assert clv(D("1.90"), D("2.00")) == D("-0.0500")
    assert clv(D("1.90"), None) is None
